"""Fetching a user-supplied URL from the server, safely (SSRF guard).

Used by intake's "Fetch from a URL" and by the drift monitor. The rules, each with a test in `tests/test_fetcher.py`:

- `http`/`https` only, on ports 80/443, with no userinfo.
- Every hop's host is resolved once and refused if **any** answer is in a denied network (private, loopback,
  link-local incl. 169.254.169.254, CGNAT, multicast, documentation/benchmark ranges, and the IPv6 equivalents;
  IPv4-mapped, NAT64 and 6to4 addresses are unwrapped and checked as IPv4).
- The connection goes to the address that was checked: the request URL carries the IP, the `Host` header and the
  TLS `sni_hostname` extension carry the name (httpcore uses `sni_hostname` as `server_hostname`, so certificate
  verification still checks the real hostname). Nothing re-resolves, so DNS rebinding has no second lookup to win.
- Redirects are followed by hand, at most `MAX_REDIRECTS`, each hop validated from scratch.
- No environment proxies or `.netrc` (`trust_env=False`), no cookies (the jar is cleared before every hop), no
  credentials, a clear User-Agent, `Accept-Encoding: identity` and compressed responses refused (no decompression
  bombs), a 2 MB body cap counted on the bytes read, `text/html` and `text/plain` only, per-phase timeouts plus a
  total deadline.

Static HTML only: there is no JavaScript rendering on the server, so copy injected by client-side scripts isn't seen.

`settings.DRIFT_FETCH_PRIVATE_ORIGINS` (dev only, empty elsewhere) lists exact `host:port` origins exempt from the
address and port rules, so a local stack can fetch its own demo partner pages. Every other rule still applies.
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx2
from django.conf import settings

MAX_REDIRECTS: Final = 5
MAX_BYTES: Final = 2 * 1024 * 1024
TOTAL_DEADLINE: Final = 15.0
TIMEOUT: Final = httpx2.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
USER_AGENT: Final = "ClearPathComplianceBot/1.0 (+drift monitor; compliance review of affiliate placements)"
ALLOWED_CONTENT_TYPES: Final = frozenset({"text/html", "text/plain"})
DEFAULT_PORTS: Final = {"http": 80, "https": 443}
_REDIRECTS: Final = frozenset({301, 302, 303, 307, 308})
_META_CHARSET: Final = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-:.]+)""", re.IGNORECASE)

_DENIED_V4: Final = tuple(
    ipaddress.IPv4Network(n)
    for n in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
_DENIED_V6: Final = tuple(
    ipaddress.IPv6Network(n)
    for n in (
        "::/128",
        "::1/128",
        "100::/64",
        "2001::/23",  # IETF protocol assignments (incl. Teredo 2001::/32)
        "2001:db8::/32",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)
_NAT64: Final = ipaddress.IPv6Network("64:ff9b::/96")


class FetchFailure(StrEnum):
    INVALID_URL = "invalid_url"
    SCHEME_NOT_ALLOWED = "scheme_not_allowed"
    PORT_NOT_ALLOWED = "port_not_allowed"
    CREDENTIALS_IN_URL = "credentials_in_url"
    DNS_FAILED = "dns_failed"
    ADDRESS_NOT_ALLOWED = "address_not_allowed"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    CONNECT_FAILED = "connect_failed"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    CONTENT_TYPE_NOT_ALLOWED = "content_type_not_allowed"
    ENCODING_NOT_ALLOWED = "encoding_not_allowed"
    TOO_LARGE = "too_large"


_MESSAGES: Final = {
    FetchFailure.INVALID_URL: "That isn't a web address we can read.",
    FetchFailure.SCHEME_NOT_ALLOWED: "Only http:// and https:// addresses can be fetched.",
    FetchFailure.PORT_NOT_ALLOWED: "Only standard web ports (80 and 443) can be fetched.",
    FetchFailure.CREDENTIALS_IN_URL: "Remove the username and password from the address.",
    FetchFailure.DNS_FAILED: "That site's name didn't resolve. Check the address.",
    FetchFailure.ADDRESS_NOT_ALLOWED: "That address points to a private or internal network, so it can't be fetched.",
    FetchFailure.TOO_MANY_REDIRECTS: "The page redirected too many times.",
    FetchFailure.CONNECT_FAILED: "The site didn't accept a connection.",
    FetchFailure.TIMEOUT: "The site took too long to respond.",
    FetchFailure.HTTP_ERROR: "The site returned an error.",
    FetchFailure.CONTENT_TYPE_NOT_ALLOWED: "That address isn't a web page (only HTML and plain text can be read).",
    FetchFailure.ENCODING_NOT_ALLOWED: "The site sent a compressed response we don't read.",
    FetchFailure.TOO_LARGE: "The page is larger than 2 MB.",
}
_TRANSIENT: Final = frozenset({FetchFailure.DNS_FAILED, FetchFailure.CONNECT_FAILED, FetchFailure.TIMEOUT})


class FetchError(Exception):
    """A refused or failed fetch. `transient` says whether trying again later could succeed."""

    def __init__(self, code: FetchFailure, *, http_status: int | None = None, message: str | None = None) -> None:
        self.code = code
        self.http_status = http_status
        if message is None:
            message = _MESSAGES[code]
            if http_status is not None:
                message = f"{message} (HTTP {http_status})"
        self.message = message
        super().__init__(f"{code}: {message}")

    @property
    def transient(self) -> bool:
        if self.code is FetchFailure.HTTP_ERROR:
            return self.http_status is not None and (self.http_status >= 500 or self.http_status == 429)  # noqa: PLR2004
        return self.code in _TRANSIENT


@dataclass(frozen=True)
class FetchedPage:
    url: str  # as requested
    final_url: str  # after redirects
    status: int
    content_type: str
    text: str


type Resolver = Callable[[str, int], Awaitable[list[str]]]


async def system_resolver(host: str, port: int) -> list[str]:
    """Every address the system resolver returns for `host`, in its preference order."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_denied_address(address: str) -> bool:
    """True unless `address` is a public unicast address. Unparseable input is denied."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            return is_denied_address(str(embedded))
        return any(ip in net for net in _DENIED_V6) or ip.is_multicast or ip.is_unspecified
    return any(ip in net for net in _DENIED_V4) or ip.is_multicast or ip.is_unspecified


@dataclass(frozen=True)
class _Target:
    url: httpx2.URL
    scheme: str
    host: str  # ASCII (IDNA) host, no brackets
    port: int
    origin: str  # "host:port", lower-case: the allowlist key

    @property
    def host_header(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return host if self.port == DEFAULT_PORTS[self.scheme] else f"{host}:{self.port}"

    @property
    def is_ip_literal(self) -> bool:
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            return False
        return True


def _target(raw: str | httpx2.URL, private_origins: Collection[str]) -> _Target:
    try:
        url = httpx2.URL(raw)
    except httpx2.InvalidURL as exc:
        raise FetchError(FetchFailure.INVALID_URL) from exc
    scheme = url.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise FetchError(FetchFailure.SCHEME_NOT_ALLOWED)
    if url.userinfo:
        raise FetchError(FetchFailure.CREDENTIALS_IN_URL)
    host = url.raw_host.decode("ascii").lower()
    if not host:
        raise FetchError(FetchFailure.INVALID_URL)
    port = url.port or DEFAULT_PORTS[scheme]
    origin = f"{host}:{port}"
    if port != DEFAULT_PORTS[scheme] and origin not in private_origins:
        raise FetchError(FetchFailure.PORT_NOT_ALLOWED)
    return _Target(url=url, scheme=scheme, host=host, port=port, origin=origin)


async def _addresses(target: _Target, resolver: Resolver, private_origins: Collection[str]) -> list[str]:
    """The addresses to connect to, all checked. Resolved exactly once per hop."""
    if target.is_ip_literal:
        addresses = [target.host]
    else:
        try:
            addresses = await resolver(target.host, target.port)
        except OSError as exc:
            raise FetchError(FetchFailure.DNS_FAILED) from exc
        if not addresses:
            raise FetchError(FetchFailure.DNS_FAILED)
    if target.origin not in private_origins and any(is_denied_address(a) for a in addresses):
        raise FetchError(FetchFailure.ADDRESS_NOT_ALLOWED)
    return addresses


async def _send(client: httpx2.AsyncClient, target: _Target, addresses: list[str]) -> httpx2.Response:
    """Open the response stream to the first address that connects."""
    headers = {
        "Host": target.host_header,
        "User-Agent": USER_AGENT,
        "Accept": "text/html, text/plain;q=0.9",
        "Accept-Encoding": "identity",
    }
    extensions = {} if target.scheme == "http" or target.is_ip_literal else {"sni_hostname": target.host}
    for address in addresses:
        client.cookies.clear()
        request = client.build_request(
            "GET", target.url.copy_with(host=address.split("%", 1)[0]), headers=headers, extensions=extensions
        )
        try:
            return await client.send(request, stream=True)
        except httpx2.ConnectError:
            continue  # try the next checked address
        except httpx2.TimeoutException as exc:
            raise FetchError(FetchFailure.TIMEOUT) from exc
        except httpx2.TransportError as exc:
            raise FetchError(FetchFailure.CONNECT_FAILED) from exc
    raise FetchError(FetchFailure.CONNECT_FAILED)


def _media_type(response: httpx2.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _check_body_allowed(response: httpx2.Response) -> None:
    if not 200 <= response.status_code < 300:  # noqa: PLR2004
        raise FetchError(FetchFailure.HTTP_ERROR, http_status=response.status_code)
    if _media_type(response) not in ALLOWED_CONTENT_TYPES:
        raise FetchError(FetchFailure.CONTENT_TYPE_NOT_ALLOWED)
    if response.headers.get("content-encoding", "identity").strip().lower() not in {"", "identity"}:
        raise FetchError(FetchFailure.ENCODING_NOT_ALLOWED)
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise FetchError(FetchFailure.TOO_LARGE)


async def _read_capped(response: httpx2.Response) -> bytes:
    body = bytearray()
    try:
        async for chunk in response.aiter_bytes():  # identity only (checked), so these are the wire bytes
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise FetchError(FetchFailure.TOO_LARGE)
    except httpx2.TimeoutException as exc:
        raise FetchError(FetchFailure.TIMEOUT) from exc
    except httpx2.TransportError as exc:
        raise FetchError(FetchFailure.CONNECT_FAILED) from exc
    return bytes(body)


def _decode(body: bytes, response: httpx2.Response) -> str:
    charset = response.charset_encoding
    if charset is None and _media_type(response) == "text/html":
        found = _META_CHARSET.search(body[:4096])
        charset = found.group(1).decode("ascii") if found else None
    try:
        return body.decode(charset or "utf-8", errors="replace")
    except LookupError:  # an unknown charset name
        return body.decode("utf-8", errors="replace")


async def _fetch(
    url: str, resolver: Resolver, transport: httpx2.AsyncBaseTransport | None, private_origins: Collection[str]
) -> FetchedPage:
    async with httpx2.AsyncClient(
        transport=transport or httpx2.AsyncHTTPTransport(retries=0, trust_env=False),
        follow_redirects=False,
        trust_env=False,
        timeout=TIMEOUT,
    ) as client:
        current: str | httpx2.URL = url
        for _ in range(MAX_REDIRECTS + 1):
            target = _target(current, private_origins)
            addresses = await _addresses(target, resolver, private_origins)
            response = await _send(client, target, addresses)
            try:
                if response.status_code in _REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(FetchFailure.HTTP_ERROR, http_status=response.status_code)
                    try:
                        current = target.url.join(location)
                    except httpx2.InvalidURL as exc:
                        raise FetchError(FetchFailure.INVALID_URL) from exc
                    continue
                _check_body_allowed(response)
                body = await _read_capped(response)
                return FetchedPage(
                    url=url,
                    final_url=str(target.url),
                    status=response.status_code,
                    content_type=_media_type(response),
                    text=_decode(body, response),
                )
            finally:
                await response.aclose()
    raise FetchError(FetchFailure.TOO_MANY_REDIRECTS)


async def fetch_page(
    url: str,
    *,
    resolver: Resolver = system_resolver,
    transport: httpx2.AsyncBaseTransport | None = None,
    private_origins: Collection[str] | None = None,
    deadline: float = TOTAL_DEADLINE,
) -> FetchedPage:
    """GET `url` under the rules in the module docstring. Raises `FetchError` for every refusal and failure."""
    origins = frozenset(
        o.lower() for o in (settings.DRIFT_FETCH_PRIVATE_ORIGINS if private_origins is None else private_origins)
    )
    try:
        async with asyncio.timeout(deadline):
            return await _fetch(url, resolver, transport, origins)
    except TimeoutError as exc:
        raise FetchError(FetchFailure.TIMEOUT) from exc
