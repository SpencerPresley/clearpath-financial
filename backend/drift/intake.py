"""Intake's "Fetch from a URL": a page's visible text and title, to prefill the copy. Async end to end, so the
request awaits network I/O on the event loop instead of holding the process's one sync thread (which would also
deadlock fetching a page this same process serves, such as the demo partner pages)."""

import asyncio
from dataclasses import dataclass

from core.errors import FieldIssue, InvalidInput
from drift.extract import MAX_TEXT_CHARS, PageText, visible_text
from drift.fetcher import FetchError, fetch_page


@dataclass(frozen=True)
class FetchedCopy:
    url: str  # where the copy came from, after redirects
    title: str | None
    content_text: str


def _url_problem(message: str, reason: str) -> InvalidInput:
    return InvalidInput(message, details={"reason": reason}, fields=[FieldIssue(loc=("body", "url"), message=message)])


async def fetch_copy(url: str) -> FetchedCopy:
    """The page's visible text. Every refusal or failure is a 422 on `url` with `details.reason` (a
    `drift.fetcher.FetchFailure` value, or `no_text`)."""
    try:
        page = await fetch_page(url)
    except FetchError as error:
        raise _url_problem(error.message, str(error.code)) from error
    if page.content_type == "text/html":
        text = await asyncio.to_thread(visible_text, page.text)  # parsing is CPU: keep it off the event loop
    else:
        text = PageText(title=None, text=page.text[:MAX_TEXT_CHARS].strip())
    if not text.text:
        raise _url_problem(
            "That page has no readable text. If it's built by JavaScript, paste the copy instead.", "no_text"
        )
    return FetchedCopy(url=page.final_url, title=text.title, content_text=text.text)
