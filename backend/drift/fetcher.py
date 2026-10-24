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

`settings.DRIFT_FETCH_PRIVATE_ORIGINS` (dev only, empty elsewhere, and ignored unless DEBUG) lists exact `host:port`
origins whose `/demo-partners/` pages are exempt from the address and port rules, so a local stack can fetch its own
demo pages. Every other rule still applies, on every hop.

A host name that doesn't resolve and one that resolves to a denied address both come back as HOST_NOT_REACHABLE, so
the error can't be used to discover names on the internal resolver. Declared charsets are limited to web text
encodings (some Python codecs are quadratic or not text codecs at all).
"""

import asyncio
import codecs
import ipaddress
import re
import socket
import ssl
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
PRIVATE_ORIGIN_PATH: Final = "/demo-partners/"  # the only path a dev-allowlisted origin is exempt for
_WEB_CODECS: Final = frozenset(
    codecs.lookup(name).name
    for name in (
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
        "ascii",
        "latin-1",
        *(f"iso8859-{n}" for n in (2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16)),
        *(f"cp125{n}" for n in range(9)),
        "koi8-r",
        "koi8-u",
        "mac-roman",
        "shift_jis",
        "cp932",
        "euc_jp",
        "iso2022_jp",
        "gb2312",
        "gbk",
        "gb18030",
        "big5",
        "big5hkscs",
        "euc_kr",
        "cp949",
    )
)
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
        "::/96",  # IPv4-compatible (deprecated), incl. :: and ::1
        "::ffff:0:0/96",  # IPv4-mapped (also unwrapped below)
        "::ffff:0:0:0/96",  # IPv4-translated
        "64:ff9b:1::/48",  # local-use NAT64 (RFC 8215): could front internal IPv4
        "100::/64",
        "2001::/23",  # IETF protocol assignments (incl. Teredo 2001::/32)
        "2001:db8::/32",
        "3fff::/20",  # documentation (RFC 9637)
        "5f00::/16",  # SRv6 SIDs
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
    # What a caller sees for a host *name* that didn't resolve or resolved to a denied address: one answer for both,
    # so the endpoint can't map names that exist only on the internal resolver. FetchError.detail keeps which.
    HOST_NOT_REACHABLE = "host_not_reachable"
    TLS_FAILED = "tls_failed"
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
    FetchFailure.HOST_NOT_REACHABLE: "That address can't be fetched: its name doesn't lead to a public website.",
    FetchFailure.TLS_FAILED: "The site's security certificate didn't check out.",
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
    """A refused or failed fetch. `code` and `message` are safe to show the person who asked; `detail` is the
    underlying cause, for logs (it differs from `code` only for HOST_NOT_REACHABLE). `transient`: could trying
    again later succeed?"""

    def __init__(
        self,
        code: FetchFailure,
        *,
        http_status: int | None = None,
        message: str | None = None,
        detail: FetchFailure | None = None,
    ) -> None:
        self.code = code
        self.detail = detail or code
        self.http_status = http_status
        if message is None:
            message = _MESSAGES[code]
            if http_status is not None:
                message = f"{message} (HTTP {http_status})"
        self.message = message
        cause = f" ({self.detail})" if self.detail is not code else ""
        super().__init__(f"{code}{cause}: {message}")

    @property
    def transient(self) -> bool:
        if self.code is FetchFailure.HTTP_ERROR:
            return self.http_status is not None and (self.http_status >= 500 or self.http_status == 429)  # noqa: PLR2004
        return self.detail in _TRANSIENT


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
        return any(ip in net for net in _DENIED_V6) or ip.is_multicast or ip.is_unspecified or ip.is_reserved
    return any(ip in net for net in _DENIED_V4) or ip.is_multicast or ip.is_unspecified


@dataclass(frozen=True)
class _Target:
    url: httpx2.URL
    scheme: str
    host: str  # ASCII (IDNA) host, no brackets
    port: int
    exempt: bool  # a dev-allowlisted origin's demo page: skips the address and port rules

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
    exempt = f"{host}:{port}" in private_origins and url.path.startswith(PRIVATE_ORIGIN_PATH)
    if port != DEFAULT_PORTS[scheme] and not exempt:
        raise FetchError(FetchFailure.PORT_NOT_ALLOWED)
    return _Target(url=url, scheme=scheme, host=host, port=port, exempt=exempt)


async def _addresses(target: _Target, resolver: Resolver) -> list[str]:
    """The addresses to connect to, all checked. Resolved exactly once per hop. A name that doesn't resolve and a
    name that resolves to a denied address get the same public answer (HOST_NOT_REACHABLE)."""
    if target.is_ip_literal:
        if not target.exempt and is_denied_address(target.host):
            raise FetchError(FetchFailure.ADDRESS_NOT_ALLOWED)
        return [target.host]
    try:
        addresses = await resolver(target.host, target.port)
    except OSError as exc:
        raise FetchError(FetchFailure.HOST_NOT_REACHABLE, detail=FetchFailure.DNS_FAILED) from exc
    if not addresses:
        raise FetchError(FetchFailure.HOST_NOT_REACHABLE, detail=FetchFailure.DNS_FAILED)
    if not target.exempt and any(is_denied_address(a) for a in addresses):
        raise FetchError(FetchFailure.HOST_NOT_REACHABLE, detail=FetchFailure.ADDRESS_NOT_ALLOWED)
    return addresses


def _tls_failure(exc: BaseException) -> bool:
    """A certificate or handshake failure somewhere in the exception chain (httpcore wraps ssl errors)."""
    seen: BaseException | None = exc
    while seen is not None:
        if isinstance(seen, ssl.SSLError):
            return True
        seen = seen.__cause__ or seen.__context__
    return False


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
        except httpx2.ConnectError as exc:
            if _tls_failure(exc):  # the address answered and its certificate is wrong: not worth retrying
                raise FetchError(FetchFailure.TLS_FAILED) from exc
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


def _codec(charset: str | None) -> str:
    """The declared charset if it's a web text encoding, else UTF-8. Not any Python codec: the page picks it, and
    `punycode` is quadratic (a 300 KB body took 12 s, uninterruptible by the deadline), `idna` refuses
    errors="replace", and `unicode_escape` / `utf-7` decode more than text."""
    if charset is None:
        return "utf-8"
    try:
        name = codecs.lookup(charset).name
    except LookupError:
        return "utf-8"
    return name if name in _WEB_CODECS else "utf-8"


def _decode(body: bytes, response: httpx2.Response) -> str:
    charset = response.charset_encoding
    if charset is None and _media_type(response) == "text/html":
        found = _META_CHARSET.search(body[:4096])
        charset = found.group(1).decode("ascii") if found else None
    try:
        return body.decode(_codec(charset), errors="replace")
    except (LookupError, UnicodeError):  # belt and braces: every allowlisted codec takes errors="replace"
        return body.decode("utf-8", errors="replace")


def _client(transport: httpx2.AsyncBaseTransport | None) -> httpx2.AsyncClient:
    """A fresh client and connection pool per hop: pooled TLS connections are keyed by (scheme, IP, port), so a
    redirect to another name on the same IP could reuse a session verified for the first name."""
    return httpx2.AsyncClient(
        transport=transport or httpx2.AsyncHTTPTransport(retries=0, trust_env=False),
        follow_redirects=False,
        trust_env=False,
        timeout=TIMEOUT,
    )


async def _fetch(
    url: str, resolver: Resolver, transport: httpx2.AsyncBaseTransport | None, private_origins: Collection[str]
) -> FetchedPage:
    current: str | httpx2.URL = url
    for _ in range(MAX_REDIRECTS + 1):
        target = _target(current, private_origins)
        addresses = await _addresses(target, resolver)
        async with _client(transport) as client:
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
    if private_origins is None:  # the dev allowlist never applies outside DEBUG, whatever the settings say
        private_origins = settings.DRIFT_FETCH_PRIVATE_ORIGINS if settings.DEBUG else ()
    origins = frozenset(o.lower() for o in private_origins)
    try:
        async with asyncio.timeout(deadline):
            return await _fetch(url, resolver, transport, origins)
    except TimeoutError as exc:
        raise FetchError(FetchFailure.TIMEOUT) from exc
