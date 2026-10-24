from .base import *

DEBUG = False

# Refuse to serve or run workers without the production configuration: the AI key, the documents bucket, https
# URLs for the CloudFront host. Enforced by `manage.py check --deploy` (deploy.sh, before migrate) and at ASGI and
# Celery startup, not at import: CI runs collectstatic on these settings with no secrets (core/deploy_checks.py).
PRODUCTION_CONFIG_REQUIRED = True

# --- Uploaded files: S3 (Terraform's documents bucket), private ---
# Credentials come from the instance role (IMDSv2, hop limit 2 so containers reach it). No ACL is ever sent: the
# bucket is BucketOwnerEnforced, so objects are private and an ACL header would be rejected.
# file_overwrite=False: attachments keep their original filename under attachments/%Y/%m/, and S3Storage's default
# (True) would let a second "rate-sheet.pdf" that month replace the first's bytes under the first row's sha256.
# FileSystemStorage (dev, tests) suffixes collisions; this matches it.
# max_memory_size: reads buffer the whole object before streaming; above 5 MB that buffer spools to disk
# instead of RAM (django-storages' default 0 never spools).
# Downloads stream through the permission-checked endpoints (reviews/api.py, exports/api.py), never a bucket URL.
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": DOCUMENTS_BUCKET,
            "region_name": env.aws_default_region,
            "file_overwrite": False,
            "max_memory_size": 5 * 1024 * 1024,
        },
    },
    # collectstatic writes /app/staticfiles in the build; deploy.yaml syncs it to the frontend bucket.
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- Client IP for allauth's rate limits ---
# CloudFront sets CloudFront-Viewer-Address ("198.51.100.10:46532"; allauth strips the port) via the origin
# request policy. Trusted only because the origin is reachable solely through the CloudFront VPC origin (security
# group: CloudFront origin-facing prefix list on 8000). With the header configured allauth never falls back to
# REMOTE_ADDR, so a request without it gets 403 from the rate-limited allauth endpoints.
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "CloudFront-Viewer-Address"

# TLS terminates at CloudFront; the app sits behind it in a private subnet.
SECURE_PROXY_SSL_HEADER = ("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# deploy.sh runs `check --deploy --fail-level WARNING`, so every remaining warning is a decision:
# - W008 (SECURE_SSL_REDIRECT): CloudFront already redirects the SPA to HTTPS and accepts only HTTPS on the app
#   paths. The compose healthcheck and deploy.sh call http://localhost:8000 without CloudFront's proto header, and a
#   redirect would fail them.
# - W021 (SECURE_HSTS_PRELOAD): preload is a commitment for a registrable domain; *.cloudfront.net isn't ours, and
#   the custom domain's parent shouldn't be preloaded by this app.
SILENCED_SYSTEM_CHECKS = ["security.W008", "security.W021"]

# The published demo password is refused where it's used (seed_demo, Reset demo, seed_demo_users), not at import:
# collectstatic runs these settings at build time without any app secrets.
DEMO_PASSWORD_DEFAULT_ALLOWED = False
