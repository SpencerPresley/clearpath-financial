"""The SSRF guard. Every refusal has a test, and the pinning test proves the connection goes to the address that
was checked. No test touches the network: the resolver and the transport are injected."""

import asyncio
import ssl
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import httpx2
import pytest
from django.conf import settings

from drift import fetcher
from drift.fetcher import FetchedPage, FetchError, FetchFailure, fetch_page, is_denied_address

PUBLIC = "93.184.215.14"
PUBLIC_V6 = "2606:2800:21f:cb07:6820:80da:af6b:8b2c"
HTML = "<html><head><title>Offer</title></head><body><p>Rates from 7.49% APR.</p></body></html>"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def resolver_for(table: dict[str, list[str]], calls: list[str] | None = None) -> fetcher.Resolver:
    async def resolve(host: str, port: int) -> list[str]:
        if calls is not None:
            calls.append(host)
        if host not in table:
            raise OSError("no such host")
        return table[host]

    return resolve


def html_response(body: str = HTML, **headers: str) -> httpx2.Response:
    return httpx2.Response(200, headers={"content-type": "text/html; charset=utf-8", **headers}, text=body)


def fetch(
    url: str,
    handler: Callable[[httpx2.Request], Any],
    *,
    table: dict[str, list[str]] | None = None,
    private_origins: tuple[str, ...] = (),
    deadline: float = fetcher.TOTAL_DEADLINE,
) -> FetchedPage:
    return run(
        fetch_page(
            url,
            resolver=resolver_for(table if table is not None else {"partner.example": [PUBLIC]}),
            transport=httpx2.MockTransport(handler),
            private_origins=private_origins,
            deadline=deadline,
        )
    )


def refused(url: str, handler: Callable[[httpx2.Request], Any] | None = None, **kwargs: Any) -> FetchError:
    def never(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError(f"no request should be sent, got {request.url}")

    with pytest.raises(FetchError) as caught:
        fetch(url, handler or never, **kwargs)
    return caught.value


# --- the address policy ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",  # noqa: S104  # the point: "this host" must be refused
        "10.0.0.5",
        "100.64.0.1",  # CGNAT
        "127.0.0.1",
        "127.10.0.1",
        "169.254.169.254",  # cloud instance metadata
        "172.16.0.1",
        "172.31.255.255",
        "192.0.0.8",
        "192.0.2.1",
        "192.168.1.1",
        "198.18.0.1",
        "198.51.100.7",
        "203.0.113.9",
        "224.0.0.1",  # multicast
        "239.255.255.250",
        "240.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "fc00::1",
        "fd12:3456::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "100::1",
        "::ffff:127.0.0.1",  # IPv4-mapped
        "::ffff:169.254.169.254",
        "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
        "2002:7f00:1::",  # 6to4 of 127.0.0.1
        "2002:a00:1::",  # 6to4 of 10.0.0.1
        "64:ff9b:1::a9fe:a9fe",  # local-use NAT64 (RFC 8215)
        "::a9fe:a9fe",  # IPv4-compatible
        "::127.0.0.1",
        "::ffff:0:7f00:1",  # IPv4-translated
        "3fff::1",  # documentation (RFC 9637)
        "5f00::1",  # SRv6
    ],
)
def test_denied_addresses(address: str) -> None:
    assert is_denied_address(address)


@pytest.mark.parametrize("address", [PUBLIC, "8.8.8.8", "1.1.1.1", PUBLIC_V6, "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(address: str) -> None:
    assert not is_denied_address(address)


def test_unparseable_address_is_denied() -> None:
    assert is_denied_address("not-an-ip")


# --- URL rules -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["ftp://partner.example/x", "file:///etc/passwd", "gopher://partner.example/"])
def test_only_http_and_https(url: str) -> None:
    assert refused(url).code in {FetchFailure.SCHEME_NOT_ALLOWED, FetchFailure.INVALID_URL}


def test_scheme_rule_names_the_scheme() -> None:
    assert refused("ftp://partner.example/x").code is FetchFailure.SCHEME_NOT_ALLOWED


def test_credentials_in_url_are_refused() -> None:
    assert refused("https://user:pass@partner.example/").code is FetchFailure.CREDENTIALS_IN_URL


@pytest.mark.parametrize(
    "url", ["https://partner.example:8443/", "http://partner.example:6379/", "http://partner.example:22/"]
)
def test_non_default_ports_are_refused(url: str) -> None:
    assert refused(url).code is FetchFailure.PORT_NOT_ALLOWED


def test_explicit_default_port_is_fine() -> None:
    page = fetch("https://partner.example:443/offer", lambda r: html_response())
    assert page.status == 200


def test_garbage_url_is_invalid() -> None:
    assert refused("https://").code is FetchFailure.INVALID_URL


# --- DNS and pinning -------------------------------------------------------------------------------------------


def test_private_resolution_is_refused() -> None:
    error = refused("https://partner.example/", table={"partner.example": ["10.1.2.3"]})
    assert error.code is FetchFailure.HOST_NOT_REACHABLE
    assert error.detail is FetchFailure.ADDRESS_NOT_ALLOWED
    assert not error.transient


def test_unresolvable_and_private_names_look_the_same_to_the_caller() -> None:
    # Otherwise the endpoint maps names that exist only on the internal resolver (*.ec2.internal, RDS endpoints).
    table = {"payments-admin.internal": ["10.0.3.7"]}
    private = refused("http://payments-admin.internal/", table=table)
    missing = refused("http://nothing-here.internal/", table=table)
    assert (private.code, private.message) == (missing.code, missing.message)
    assert (private.detail, missing.detail) == (FetchFailure.ADDRESS_NOT_ALLOWED, FetchFailure.DNS_FAILED)


def test_any_private_address_in_the_answer_refuses_the_host() -> None:
    error = refused("https://partner.example/", table={"partner.example": [PUBLIC, "127.0.0.1"]})
    assert error.detail is FetchFailure.ADDRESS_NOT_ALLOWED


def test_metadata_ip_literal_is_refused() -> None:
    assert refused("http://169.254.169.254/latest/meta-data/").code is FetchFailure.ADDRESS_NOT_ALLOWED


def test_ipv6_loopback_literal_is_refused() -> None:
    assert refused("http://[::1]/").code is FetchFailure.ADDRESS_NOT_ALLOWED


def test_localhost_name_is_refused_through_resolution() -> None:
    error = refused("http://localhost/", table={"localhost": ["127.0.0.1", "::1"]})
    assert error.detail is FetchFailure.ADDRESS_NOT_ALLOWED


def test_dns_failure_is_transient() -> None:
    error = refused("https://nowhere.example/", table={})
    assert error.code is FetchFailure.HOST_NOT_REACHABLE
    assert error.detail is FetchFailure.DNS_FAILED
    assert error.transient


def test_request_is_pinned_to_the_checked_address() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html_response()

    calls: list[str] = []
    page = run(
        fetch_page(
            "https://partner.example/offer?x=1",
            resolver=resolver_for({"partner.example": [PUBLIC]}, calls),
            transport=httpx2.MockTransport(handler),
            private_origins=(),
        )
    )

    (request,) = seen
    assert request.url.host == PUBLIC
    assert request.url.path == "/offer"
    assert request.url.query == b"x=1"
    assert request.headers["host"] == "partner.example"
    assert request.extensions["sni_hostname"] == "partner.example"
    assert calls == ["partner.example"]  # resolved once
    assert page.final_url == "https://partner.example/offer?x=1"


def test_ipv6_answer_is_pinned_in_brackets() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html_response()

    fetch("https://partner.example/", handler, table={"partner.example": [PUBLIC_V6]})

    assert seen[0].url.host == PUBLIC_V6
    assert f"[{PUBLIC_V6}]" in str(seen[0].url)


def test_plain_http_sends_no_sni_extension() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html_response()

    fetch("http://partner.example/", handler)

    assert "sni_hostname" not in seen[0].extensions
    assert seen[0].headers["host"] == "partner.example"


def test_next_address_is_tried_when_one_does_not_connect() -> None:
    hosts: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        hosts.append(request.url.host)
        if request.url.host == PUBLIC_V6:
            raise httpx2.ConnectError("unreachable", request=request)
        return html_response()

    fetch("https://partner.example/", handler, table={"partner.example": [PUBLIC_V6, PUBLIC]})

    assert hosts == [PUBLIC_V6, PUBLIC]


def test_connect_failure_on_every_address_is_transient() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    error = refused("https://partner.example/", handler)
    assert error.code is FetchFailure.CONNECT_FAILED
    assert error.transient


# --- redirects -------------------------------------------------------------------------------------------------


def redirect(location: str, status: int = 302) -> httpx2.Response:
    return httpx2.Response(status, headers={"location": location})


def test_redirect_to_metadata_is_refused() -> None:
    error = refused("https://partner.example/", lambda r: redirect("http://169.254.169.254/latest/"))
    assert error.code is FetchFailure.ADDRESS_NOT_ALLOWED


def test_redirect_to_a_private_name_is_refused() -> None:
    table = {"partner.example": [PUBLIC], "internal.partner.example": ["10.0.0.7"]}
    error = refused("https://partner.example/", lambda r: redirect("https://internal.partner.example/"), table=table)
    assert error.detail is FetchFailure.ADDRESS_NOT_ALLOWED


def test_redirect_to_a_disallowed_scheme_is_refused() -> None:
    error = refused("https://partner.example/", lambda r: redirect("file:///etc/passwd"))
    assert error.code in {FetchFailure.SCHEME_NOT_ALLOWED, FetchFailure.INVALID_URL}


def test_each_hop_is_resolved_and_pinned() -> None:
    table = {"partner.example": [PUBLIC], "cdn.partner.example": ["93.184.215.15"]}
    calls: list[str] = []
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.headers["host"] == "partner.example":
            return redirect("https://cdn.partner.example/landing", 301)
        return html_response()

    page = run(
        fetch_page(
            "https://partner.example/",
            resolver=resolver_for(table, calls),
            transport=httpx2.MockTransport(handler),
            private_origins=(),
        )
    )

    assert calls == ["partner.example", "cdn.partner.example"]
    assert [r.url.host for r in seen] == [PUBLIC, "93.184.215.15"]
    assert seen[1].extensions["sni_hostname"] == "cdn.partner.example"
    assert page.final_url == "https://cdn.partner.example/landing"
    assert page.url == "https://partner.example/"


def test_relative_location_resolves_against_the_current_url() -> None:
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        return redirect("../b/page") if request.url.path == "/a/start/x" else html_response()

    page = fetch("https://partner.example/a/start/x", handler)

    assert paths == ["/a/start/x", "/a/b/page"]
    assert page.final_url == "https://partner.example/a/b/page"


def test_too_many_redirects() -> None:
    count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return redirect(f"/hop{count}")

    error = refused("https://partner.example/", handler)
    assert error.code is FetchFailure.TOO_MANY_REDIRECTS
    assert count == fetcher.MAX_REDIRECTS + 1


def test_redirect_without_location_is_an_http_error() -> None:
    error = refused("https://partner.example/", lambda r: httpx2.Response(302))
    assert error.code is FetchFailure.HTTP_ERROR


def test_cookies_set_on_one_hop_are_not_sent_on_the_next() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/":
            return httpx2.Response(302, headers={"location": "/next", "set-cookie": "sid=abc; Path=/"})
        return html_response()

    fetch("https://partner.example/", handler)

    assert "cookie" not in seen[1].headers


def test_no_credentials_and_a_clear_user_agent() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html_response()

    fetch("https://partner.example/", handler)

    headers = seen[0].headers
    assert "authorization" not in headers
    assert "cookie" not in headers
    assert headers["user-agent"] == fetcher.USER_AGENT
    assert headers["accept-encoding"] == "identity"


def test_client_ignores_environment_and_never_follows_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    # trust_env=False: no HTTP(S)_PROXY (which would bypass the pin) and no .netrc credentials.
    built: list[dict[str, Any]] = []
    real = httpx2.AsyncClient

    def spy(**kwargs: Any) -> httpx2.AsyncClient:
        built.append(kwargs)
        kwargs_for_mock: dict[str, Any] = {**kwargs, "transport": httpx2.MockTransport(lambda r: html_response())}
        return real(**kwargs_for_mock)

    monkeypatch.setattr(fetcher.httpx2, "AsyncClient", spy)
    run(
        fetch_page("https://partner.example/", resolver=resolver_for({"partner.example": [PUBLIC]}), private_origins=())
    )

    (kwargs,) = built
    assert kwargs["trust_env"] is False
    assert kwargs["follow_redirects"] is False
    assert isinstance(kwargs["transport"], httpx2.AsyncHTTPTransport)


# --- the response ----------------------------------------------------------------------------------------------


def test_returns_the_decoded_page() -> None:
    page = fetch("https://partner.example/", lambda r: html_response())
    assert page.text == HTML
    assert page.status == 200
    assert page.content_type == "text/html"


def test_plain_text_is_accepted() -> None:
    page = fetch(
        "https://partner.example/", lambda r: httpx2.Response(200, headers={"content-type": "text/plain"}, text="hi")
    )
    assert page.text == "hi"


@pytest.mark.parametrize("content_type", ["application/pdf", "image/png", "application/json", ""])
def test_other_content_types_are_refused(content_type: str) -> None:
    headers = {"content-type": content_type} if content_type else {}
    error = refused("https://partner.example/", lambda r: httpx2.Response(200, headers=headers, content=b"x"))
    assert error.code is FetchFailure.CONTENT_TYPE_NOT_ALLOWED


def test_compressed_responses_are_refused() -> None:
    error = refused(
        "https://partner.example/",
        lambda r: httpx2.Response(
            200, headers={"content-type": "text/html", "content-encoding": "gzip"}, content=b"\x1f\x8b"
        ),
    )
    assert error.code is FetchFailure.ENCODING_NOT_ALLOWED


def test_declared_oversize_body_is_refused_before_reading() -> None:
    error = refused(
        "https://partner.example/",
        lambda r: httpx2.Response(
            200, headers={"content-type": "text/html", "content-length": str(3 * 1024 * 1024)}, content=b"x"
        ),
    )
    assert error.code is FetchFailure.TOO_LARGE


def test_streamed_oversize_body_is_refused() -> None:
    async def body() -> AsyncIterator[bytes]:
        for _ in range(40):
            yield b"x" * 65536  # 2.5 MB, no Content-Length

    error = refused(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": "text/html"}, content=body()),
    )
    assert error.code is FetchFailure.TOO_LARGE


@pytest.mark.parametrize(("status", "transient"), [(404, False), (410, False), (403, False), (429, True), (503, True)])
def test_http_errors(status: int, transient: bool) -> None:
    error = refused(
        "https://partner.example/", lambda r: httpx2.Response(status, headers={"content-type": "text/html"})
    )
    assert error.code is FetchFailure.HTTP_ERROR
    assert error.http_status == status
    assert error.transient is transient


def test_total_deadline() -> None:
    async def drip() -> AsyncIterator[bytes]:
        while True:
            await asyncio.sleep(0.05)
            yield b"x"

    error = refused(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": "text/html"}, content=drip()),
        deadline=0.3,
    )
    assert error.code is FetchFailure.TIMEOUT
    assert error.transient


def test_transport_timeout_is_a_timeout() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    assert refused("https://partner.example/", handler).code is FetchFailure.TIMEOUT


def test_fetch_decodes_declared_charset() -> None:
    body = "<p>Café crème 7.49% APR</p>".encode("iso-8859-1")
    page = fetch(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": "text/html; charset=iso-8859-1"}, content=body),
    )
    assert "Café crème" in page.text


def test_fetch_reads_meta_charset_when_the_header_has_none() -> None:
    body = '<meta charset="windows-1252"><p>“Low rates”</p>'.encode("cp1252")
    page = fetch(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": "text/html"}, content=body),
    )
    assert "“Low rates”" in page.text


def test_undeclared_bad_bytes_fall_back_to_replacement() -> None:
    page = fetch(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": "text/html"}, content=b"ok \xff\xfe end"),
    )
    assert page.text.startswith("ok ")
    assert page.text.endswith(" end")


@pytest.mark.parametrize("charset", ["punycode", "idna", "undefined", "utf-7", "unicode_escape", "rot13"])
def test_non_web_charsets_decode_as_utf8(charset: str) -> None:
    # The page picks the codec: punycode is quadratic (300 KB took 12 s, past any deadline), idna and undefined
    # raise instead of replacing, the rest aren't text encodings.
    body = b"-" + b"9" * 300_000
    started = time.monotonic()
    page = fetch(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": f"text/html; charset={charset}"}, content=body),
    )
    assert time.monotonic() - started < 2.0
    assert page.text == body.decode()


def test_meta_punycode_charset_is_ignored() -> None:
    body = b'<meta charset="punycode">' + b"9" * 200_000
    started = time.monotonic()
    fetch(
        "https://partner.example/", lambda r: httpx2.Response(200, headers={"content-type": "text/html"}, content=body)
    )
    assert time.monotonic() - started < 2.0


def test_tls_failure_is_its_own_permanent_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        try:
            raise ssl.SSLCertVerificationError("certificate verify failed: Hostname mismatch")
        except ssl.SSLError as exc:
            raise httpx2.ConnectError("tls", request=request) from exc

    error = refused("https://partner.example/", handler)
    assert error.code is FetchFailure.TLS_FAILED
    assert not error.transient


def test_each_redirect_hop_gets_a_fresh_connection_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pooled connections are keyed by (scheme, IP, port): a second name on the same IP must not reuse a TLS
    # session verified for the first.
    clients: list[httpx2.AsyncClient] = []
    real = fetcher._client

    def counting(transport: httpx2.AsyncBaseTransport | None) -> httpx2.AsyncClient:
        clients.append(real(transport))
        return clients[-1]

    monkeypatch.setattr(fetcher, "_client", counting)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return redirect("https://b.example/") if request.headers["host"] == "a.example" else html_response()

    fetch("https://a.example/", handler, table={"a.example": [PUBLIC], "b.example": [PUBLIC]})
    assert len(clients) == 2
    assert all(c.is_closed for c in clients)


def test_unknown_charset_falls_back_to_utf8() -> None:
    page = fetch(
        "https://partner.example/",
        lambda r: httpx2.Response(200, headers={"content-type": "text/html; charset=x-nonsense"}, content=b"plain"),
    )
    assert page.text == "plain"


# --- the dev allowlist -----------------------------------------------------------------------------------------


def test_allowlisted_origin_may_be_private() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html_response()

    fetch(
        "http://localhost:8000/demo-partners/lendcompare/",
        handler,
        table={"localhost": ["127.0.0.1"]},
        private_origins=("localhost:8000",),
    )

    assert seen[0].url.host == "127.0.0.1"
    assert seen[0].url.port == 8000
    assert seen[0].headers["host"] == "localhost:8000"


def test_allowlist_is_per_origin_not_per_host() -> None:
    error = refused("http://localhost:6379/", table={"localhost": ["127.0.0.1"]}, private_origins=("localhost:8000",))
    assert error.code is FetchFailure.PORT_NOT_ALLOWED


def test_allowlist_covers_only_the_demo_pages() -> None:
    error = refused(
        "http://localhost:8000/admin/", table={"localhost": ["127.0.0.1"]}, private_origins=("localhost:8000",)
    )
    assert error.code is FetchFailure.PORT_NOT_ALLOWED
    error = refused(
        "http://localhost/api/health", table={"localhost": ["127.0.0.1"]}, private_origins=("localhost:80",)
    )
    assert error.detail is FetchFailure.ADDRESS_NOT_ALLOWED


def test_settings_allowlist_is_ignored_outside_debug(settings: Any) -> None:
    settings.DRIFT_FETCH_PRIVATE_ORIGINS = ["localhost:8000"]
    settings.DEBUG = False  # e.g. a deployed box that fell back to dev settings but has DEBUG off
    with pytest.raises(FetchError) as caught:
        run(
            fetch_page(
                "http://localhost:8000/demo-partners/lendcompare/",
                resolver=resolver_for({"localhost": ["127.0.0.1"]}),
                transport=httpx2.MockTransport(lambda r: html_response()),
            )
        )
    assert caught.value.code is FetchFailure.PORT_NOT_ALLOWED


def test_allowlisted_origin_still_has_the_content_rules() -> None:
    error = refused(
        "http://localhost:8000/demo-partners/x/",
        lambda r: httpx2.Response(200, headers={"content-type": "application/json"}, content=b"{}"),
        table={"localhost": ["127.0.0.1"]},
        private_origins=("localhost:8000",),
    )
    assert error.code is FetchFailure.CONTENT_TYPE_NOT_ALLOWED


def test_redirect_from_allowlisted_origin_to_a_private_one_is_refused() -> None:
    error = refused(
        "http://localhost:8000/demo-partners/x/",
        lambda r: redirect("http://127.0.0.1/admin"),
        table={"localhost": ["127.0.0.1"]},
        private_origins=("localhost:8000",),
    )
    assert error.code is FetchFailure.ADDRESS_NOT_ALLOWED


def test_settings_allowlist_is_empty_outside_dev() -> None:
    # Test settings import base, as prod does; only dev.py adds private origins.
    assert settings.DRIFT_FETCH_PRIVATE_ORIGINS == []


def test_prod_settings_add_no_private_origins() -> None:
    from pathlib import Path

    prod = Path(settings.BASE_DIR, "config", "settings", "prod.py").read_text()
    assert "DRIFT_FETCH_PRIVATE_ORIGINS" not in prod
