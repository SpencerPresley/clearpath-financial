from datetime import date

from checks.engine import human_checklist, run_code_checks
from core.domain import AttachmentKind, Channel, FindingSource, Product

from .conftest import make_ctx


def ids(text: str, **kw: object) -> set[str]:
    return {f.rule_id for f in human_checklist(make_ctx(text, **kw))}  # type: ignore[arg-type]


def test_every_item_gets_the_reg_b_check() -> None:
    assert ids("Personal loans for life.") == {"human.reg_b_discouragement"}


def test_reg_b_item_follows_its_effective_date() -> None:
    assert "human.reg_b_discouragement" not in ids("Personal loans.", today=date(2026, 7, 20))


def test_mortgage_adds_government_imagery() -> None:
    assert "human.government_imagery" in ids("Get prequalified.", product=Product.MORTGAGE_PREQUAL)


def test_sms_adds_send_window() -> None:
    assert "human.sms_send_window" in ids("Reply STOP to opt out.", channel=Channel.SMS)


def test_prescreen_adds_notice_format_check() -> None:
    assert "human.prescreen_format" in ids("Offer.", attachments=(AttachmentKind.PRESCREEN_CRITERIA,))
    assert "human.prescreen_format" in ids("This prescreened offer is for you.")
    assert "human.prescreen_format" not in ids("Personal loans.")


def test_code_checks_never_emit_human_items() -> None:
    result = run_code_checks(make_ctx("This prescreened offer is for you.", channel=Channel.SMS))
    assert all(f.source == FindingSource.CODE for f in result.findings)
