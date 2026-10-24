import time

from core.domain import DriftResult
from drift.compare import MISSING_BELOW, compare, normalize
from drift.extract import MAX_TEXT_CHARS, visible_text
from reviews.diff import DiffOp

NBSP, RSQUO, LDQUO, RDQUO, ELLIPSIS = chr(0xA0), chr(0x2019), chr(0x201C), chr(0x201D), chr(0x2026)

APPROVED = (
    "Personal loans from ClearPath: fixed rates from 7.49% to 35.99% APR. Loan amounts from $2,000 to $40,000 "
    "with terms of 24 to 60 months. Checking your rate won't affect your credit score."
)

PAGE = f"""<!doctype html>
<html><head><title>Best personal loans | LendCompare</title>
<style>.x {{ color: red }}</style><script>var t = "Rates from 1% APR";</script></head>
<body>
<nav><a href="/">Home</a> <a href="/loans">Loans</a></nav>
<p>Updated October 24, 2026</p>
<div class="offer"><h2>ClearPath</h2><p>{APPROVED}</p></div>
<aside hidden>Secret: guaranteed approval</aside>
<div style="display: none">Also hidden</div>
<span aria-hidden="true">decorative</span>
<noscript>Enable JavaScript</noscript>
<footer>Advertiser disclosure: we may be compensated.</footer>
</body></html>"""


# --- visible text ----------------------------------------------------------------------------------------------


def test_visible_text_keeps_what_a_reader_sees() -> None:
    page = visible_text(PAGE)

    assert page.title == "Best personal loans | LendCompare"
    assert APPROVED in normalize(page.text)
    assert "Updated October 24, 2026" in page.text
    for hidden in ("color: red", "Rates from 1% APR", "guaranteed approval", "Also hidden", "decorative", "Enable"):
        assert hidden not in page.text


def test_blocks_break_lines_and_inline_elements_do_not() -> None:
    page = visible_text("<div>One</div><div>Two <b>bold</b> text</div><p>Three</p>")
    assert page.text.splitlines() == ["One", "Two bold text", "Three"]


def test_text_is_capped() -> None:
    page = visible_text("<p>" + "word " * 50_000 + "</p>")
    assert len(page.text) <= MAX_TEXT_CHARS


def test_deep_nesting_does_not_raise() -> None:
    assert visible_text("<div>" * 10_000 + "deep" + "</div>" * 10_000).text == "deep"


def test_deep_nesting_is_linear_not_quadratic() -> None:
    # 400 KB of unclosed divs took 73 s when every block was mutated in the tree (O(depth) per insert).
    started = time.monotonic()
    visible_text("<div>" * 80_000 + "x")
    assert time.monotonic() - started < 3.0


def test_comments_doctype_and_cdata() -> None:
    page = visible_text("<!doctype html><p>a<!-- hidden note -->b</p><p><![CDATA[c]]></p>")
    assert "hidden note" not in page.text
    assert "doctype" not in page.text.lower()


def test_plain_text_and_empty_documents() -> None:
    assert visible_text("").text == ""
    assert visible_text("").title is None
    assert visible_text("just text").text == "just text"


def test_a_large_page_parses_quickly() -> None:
    html = "<div><p>" + ("Lorem ipsum dolor sit amet. " * 40 + "</p><p>") * 900 + "</p></div>"  # ~1 MB
    started = time.monotonic()
    visible_text(html)
    assert time.monotonic() - started < 3.0


# --- normalization ---------------------------------------------------------------------------------------------


def test_normalize_folds_whitespace_quotes_and_compatibility_forms() -> None:
    assert normalize(f"  Checking{NBSP}your rate\nwon{RSQUO}t  affect {LDQUO}score{RDQUO}{ELLIPSIS} ") == (
        'Checking your rate won\'t affect "score"...'
    )


# --- compare ---------------------------------------------------------------------------------------------------


def test_exact_copy_among_page_noise_is_unchanged() -> None:
    result = compare(APPROVED, visible_text(PAGE).text)

    assert result.result is DriftResult.UNCHANGED
    assert result.score == 100.0
    assert result.matched_text == normalize(APPROVED)
    assert result.diff == ()


def test_compare_ignores_markup_and_whitespace() -> None:
    split = APPROVED.replace("fixed rates", "<em>fixed</em>\n   rates").replace("won't", f"won{RSQUO}t")
    page = visible_text(f"<p>Intro</p><p>{split}</p>").text
    assert compare(APPROVED, page).result is DriftResult.UNCHANGED


def test_a_changed_rate_is_modified_with_a_tight_diff() -> None:
    page = visible_text(PAGE.replace("7.49%", "5.99%")).text

    result = compare(APPROVED, page)

    assert result.result is DriftResult.MODIFIED
    assert MISSING_BELOW <= result.score < 100
    changes = [(s.op, s.text) for s in result.diff if s.op is not DiffOp.EQUAL]
    assert changes == [(DiffOp.DELETE, "7.49"), (DiffOp.INSERT, "5.99")]
    # No page noise at either end of the matched region.
    assert result.diff[0].op is DiffOp.EQUAL
    assert result.diff[0].text.startswith("Personal loans")
    assert result.diff[-1].text.endswith("credit score.")
    assert "5.99%" in result.matched_text
    assert "Updated" not in result.matched_text


def test_an_inserted_claim_is_modified() -> None:
    page = visible_text(PAGE.replace("APR. Loan", "APR. Guaranteed approval for everyone! Loan")).text

    result = compare(APPROVED, page)

    assert result.result is DriftResult.MODIFIED
    inserted = "".join(s.text for s in result.diff if s.op is DiffOp.INSERT)
    assert "Guaranteed approval for everyone!" in inserted


def test_a_dropped_disclosure_is_modified() -> None:
    page = visible_text(PAGE.replace(" Checking your rate won't affect your credit score.", "")).text

    result = compare(APPROVED, page)

    assert result.result is DriftResult.MODIFIED
    deleted = "".join(s.text for s in result.diff if s.op is DiffOp.DELETE)
    assert "Checking your rate won't affect your credit score." in deleted


def test_copy_removed_from_a_page_about_loans_is_missing() -> None:
    other = (
        "Compare personal loans from top lenders. Rates vary by lender and credit profile. See our picks for "
        "debt consolidation, home improvement and emergency expenses. Loan amounts and terms vary. "
        "Advertiser disclosure: we may be compensated by partners."
    )
    result = compare(APPROVED, visible_text(f"<nav>Home Loans</nav><p>{other}</p>").text)

    assert result.result is DriftResult.MISSING
    assert result.score < MISSING_BELOW
    assert result.diff == ()


def test_empty_page_is_missing() -> None:
    assert compare(APPROVED, "").result is DriftResult.MISSING


def test_rewritten_copy_just_below_the_threshold_is_missing_and_just_above_is_modified() -> None:
    words = normalize(APPROVED).split(" ")
    # Replace a growing share of the words until the score crosses the threshold; both sides must classify right.
    seen: set[DriftResult] = set()
    for n in range(len(words) + 1):
        page = " ".join(["zzzz"] * n + words[n:])
        result = compare(APPROVED, page)
        assert (result.score >= MISSING_BELOW) == (result.result is not DriftResult.MISSING)
        seen.add(result.result)
    assert {DriftResult.MODIFIED, DriftResult.MISSING} <= seen


def test_compare_is_fast_on_a_long_page() -> None:
    page = ("Unrelated filler about savings accounts and mortgages. " * 3000) + APPROVED.replace("7.49", "6.49")
    started = time.monotonic()
    result = compare(APPROVED, page)
    assert time.monotonic() - started < 2.0
    assert result.result is DriftResult.MODIFIED


def test_an_edit_at_the_end_of_the_copy_stays_in_the_diff() -> None:
    page = visible_text(
        PAGE.replace("won't affect your credit score.", "never hurts your credit. Guaranteed approval!")
    ).text

    result = compare(APPROVED, page)

    assert result.result is DriftResult.MODIFIED
    inserted = "".join(s.text for s in result.diff if s.op is DiffOp.INSERT)
    assert "Guaranteed approval!" in inserted
    assert "Advertiser" not in inserted  # the footer is another block


def test_an_edit_at_the_start_of_the_copy_stays_in_the_diff() -> None:
    page = visible_text(PAGE.replace("<p>Personal loans from", "<p>NEW! Loans from")).text

    result = compare(APPROVED, page)

    assert result.result is DriftResult.MODIFIED
    assert [(s.op, s.text.strip()) for s in result.diff if s.op is not DiffOp.EQUAL][:2] == [
        (DiffOp.DELETE, "Personal loans"),
        (DiffOp.INSERT, "NEW! Loans"),
    ]


def test_verbatim_copy_with_text_added_around_it_is_unchanged() -> None:
    # The approved copy is intact; what the partner put next to it is the page code checks' job.
    page = visible_text(PAGE.replace("credit score.", "credit score. Guaranteed approval!")).text
    assert compare(APPROVED, page).result is DriftResult.UNCHANGED
