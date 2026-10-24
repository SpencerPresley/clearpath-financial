"""The public demo partner pages (`/demo-partners/<slug>/`). Plain Django views, not API operations: they stand in
for third-party sites. Static content from `drift.demo`; nothing from the request is rendered."""

import hashlib

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from drift import demo


@require_safe
@never_cache
def partner_page(request: HttpRequest, slug: str) -> HttpResponse:
    page = demo.get_page(slug)
    if page is None:
        raise Http404
    edited = demo.is_edited(slug)
    today = timezone.localdate()
    # Page noise that changes every day, like a real partner page: the date and a reader count.
    reads = 1000 + int(hashlib.sha256(f"{slug}{today}".encode()).hexdigest()[:4], 16) % 9000
    context = {
        "page": page,
        "edited": edited,
        "copy": page.edited_copy if edited else page.copy,
        "today": today,
        "reads": f"{reads:,}",
    }
    return render(request, "drift/partner_page.html", context)
