"""The NinjaAPI: routers, auth default, and the one place errors become HTTP responses (spec §6.1)."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError
from ninja.security import django_auth

from accounts.api import admin_router as accounts_admin_router
from accounts.api import me_router
from core.api import router as core_router
from core.errors import DomainError
from core.schemas import ErrorOut, FieldErrorOut


def _respond(api: NinjaAPI, request: HttpRequest, body: ErrorOut, status: int) -> HttpResponse:
    return api.create_response(request, body.model_dump(mode="json"), status=status)


def install_error_handlers(api: NinjaAPI) -> None:
    """Map every failure to `ErrorOut`. Registered once per NinjaAPI; endpoints contain no try/except."""

    def on_domain_error(request: HttpRequest, exc: DomainError) -> HttpResponse:
        body = ErrorOut(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            fields=[FieldErrorOut(loc=list(f.loc), message=f.message, type=f.type) for f in exc.fields],
        )
        return _respond(api, request, body, exc.status)

    def on_validation_error(request: HttpRequest, exc: ValidationError) -> HttpResponse:
        fields = [
            FieldErrorOut(loc=list(e.get("loc", ())), message=str(e.get("msg", "")), type=str(e.get("type", "")))
            for e in exc.errors
        ]
        body = ErrorOut(code="validation_error", message="Some fields are invalid.", fields=fields)
        return _respond(api, request, body, 422)

    def on_authentication_error(request: HttpRequest, exc: AuthenticationError) -> HttpResponse:
        body = ErrorOut(code="not_authenticated", message="Sign in to continue.")
        return _respond(api, request, body, 401)

    def on_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
        return _respond(api, request, ErrorOut(code="http_error", message=str(exc)), exc.status_code)

    _register(api, DomainError, on_domain_error)
    _register(api, ValidationError, on_validation_error)
    _register(api, AuthenticationError, on_authentication_error)
    _register(api, HttpError, on_http_error)


def _register[E: Exception](
    api: NinjaAPI, exc_class: type[E], handler: Callable[[HttpRequest, E], HttpResponse]
) -> None:
    # ninja types the handler's exception parameter as `E | type[E]`; it is always called with an instance.
    api.add_exception_handler(exc_class, handler)  # pyrefly: ignore[bad-argument-type]


# Session-cookie auth by default; django_auth enforces CSRF on unsafe methods.
# Public endpoints opt out per operation with auth=None.
api = NinjaAPI(
    title="ClearPath Compliance Review API",
    version="0.1.0",
    auth=django_auth,
    urls_namespace="api",
)
install_error_handlers(api)

api.add_router("/", core_router)
api.add_router("/", me_router)
api.add_router("/", accounts_admin_router)
