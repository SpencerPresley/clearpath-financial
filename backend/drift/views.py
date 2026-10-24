"""The public demo partner pages (`/demo-partners/<slug>/`). Plain Django views, not API operations: they stand in
for third-party sites. Static content from `drift.demo`; nothing from the request is rendered."""

from django.http import Http404, HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from drift import demo


@require_safe
@never_cache
def partner_page(request: HttpRequest, slug: str) -> HttpResponse:  # noqa: ARG001  # Django view signature
    page = demo.get_page(slug)
    if page is None:
        raise Http404
    html = demo.render_page(page, edited=demo.is_edited(slug), today=timezone.localdate())
    return HttpResponse(html)
