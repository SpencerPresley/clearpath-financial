from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "web"]

# Vite proxies /api and /_allauth (same origin, so no CORS), but the browser's Origin is still Vite's, so
# Django's CSRF check needs it trusted. CSRF_TRUSTED_ORIGINS has no port wildcard: the dev server (5173) and
# `vite preview` / Playwright (4173) are trusted by default; add others (an E2E_PORT run, a second dev server)
# with DJANGO_CSRF_TRUSTED_ORIGINS. Listed origins add to the defaults, so an .env naming only 5173 keeps 4173.
DEV_ORIGINS = [f"http://{host}:{port}" for port in (5173, 4173) for host in ("localhost", "127.0.0.1")]
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([*DEV_ORIGINS, *env.django_csrf_trusted_origins]))
