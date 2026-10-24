from checks.engine import EngineConfig, run_code_checks
from core.domain import AttachmentKind, Channel, Market, PartnerType, Product

from .conftest import codes, make_ctx

CONSENT = (AttachmentKind.CONSENT_RECORD,)
EMAIL_FOOTER = (
    "This is an advertisement from ClearPath Financial, 123 Market St, Suite 400, San Francisco, CA 94105. "
    "Unsubscribe or manage your email preferences."
)
CA_LINE = "Loans made or arranged pursuant to a California Financing Law license."


def run(text: str, **kw: object) -> set[str]:
    return codes(run_code_checks(make_ctx(text, **kw)))  # type: ignore[arg-type]


def test_sms_needs_consent_record_and_stop_language() -> None:
    found = run("ClearPath: check your personal loan rate today.", channel=Channel.SMS)
    assert {"sms.consent_record", "sms.opt_out"} <= found


def test_compliant_sms() -> None:
    text = "ClearPath: check your personal loan rate today. Reply STOP to opt out."
    assert not {c for c in run(text, channel=Channel.SMS, attachments=CONSENT) if c.startswith("sms.")}


def test_sms_rules_only_on_sms() -> None:
    assert not {c for c in run("Check your rate.", channel=Channel.DISPLAY) if c.startswith("sms.")}


def test_email_basics_missing() -> None:
    found = run("Check your personal loan rate today.", channel=Channel.EMAIL)
    assert {"email.opt_out", "email.postal_address", "email.ad_identification"} <= found


def test_compliant_email_footer() -> None:
    text = f"Subject: Your rate is waiting\n\nCheck your personal loan rate today.\n\n{EMAIL_FOOTER}"
    assert not {c for c in run(text, channel=Channel.EMAIL) if c.startswith("email.")}


def test_po_box_counts_as_postal_address() -> None:
    text = "Ad. Unsubscribe here. ClearPath Financial, P.O. Box 4410, Sacramento, CA 95812."
    assert "email.postal_address" not in run(text, channel=Channel.EMAIL)


def test_reply_prefix_subject_line() -> None:
    text = f"Subject: RE: your application\n\nCheck your rate.\n\n{EMAIL_FOOTER}"
    found = run(text, channel=Channel.EMAIL)
    assert "email.subject_reply_prefix" in found


def test_affiliate_content_needs_material_connection_disclosure() -> None:
    text = "The best personal loan of 2026 is ClearPath. Check your rate."
    assert "endorsement.material_connection" in run(text, channel=Channel.AFFILIATE_PAGE)
    assert "endorsement.material_connection" in run(
        text, channel=Channel.PAID_SOCIAL, partner_type=PartnerType.INFLUENCER
    )


def test_disclosed_affiliate_and_influencer_content() -> None:
    disclosed = "Advertiser disclosure: we receive compensation from ClearPath. Check your rate."
    assert "endorsement.material_connection" not in run(disclosed, channel=Channel.AFFILIATE_PAGE)
    tagged = "#ad Loving my @ClearPath loan."
    assert "endorsement.material_connection" not in run(
        tagged, channel=Channel.PAID_SOCIAL, partner_type=PartnerType.INFLUENCER
    )


def test_first_party_social_needs_no_disclosure() -> None:
    assert "endorsement.material_connection" not in run("Check your rate.", channel=Channel.PAID_SOCIAL)


def test_california_ad_needs_license_disclosure() -> None:
    assert "ca.license_disclosure" in run("Check your rate.", markets=(Market.CA,))
    assert "ca.license_disclosure" not in run(f"Check your rate. {CA_LINE}", markets=(Market.CA,))
    assert "ca.license_disclosure" not in run("Check your rate.", markets=(Market.NATIONAL,))


def test_license_phrase_matching_tolerates_case_and_line_breaks() -> None:
    text = "Check your rate.\nLoans made or arranged pursuant to a\nCALIFORNIA FINANCING LAW LICENSE."
    assert "ca.license_disclosure" not in run(text, markets=(Market.CA,))


def test_license_phrases_are_configurable() -> None:
    config = EngineConfig(ca_license_phrases=("CA Lic. 60DBO-12345",))
    ctx = make_ctx(f"Check your rate. {CA_LINE}", markets=(Market.CA,))
    assert "ca.license_disclosure" in codes(run_code_checks(ctx, config=config))
    ok = make_ctx("Check your rate. CA Lic. 60DBO-12345", markets=(Market.CA,))
    assert "ca.license_disclosure" not in codes(run_code_checks(ok, config=config))


def test_license_rule_scope() -> None:
    assert "ca.license_disclosure" in run("Prequalify today.", product=Product.MORTGAGE_PREQUAL, markets=(Market.CA,))
    assert "ca.license_disclosure" not in run("$0 annual fee.", product=Product.CREDIT_CARD, markets=(Market.CA,))


def test_prose_mentioning_an_ad_is_not_an_ad_label() -> None:
    text = f"Note to automated reviewers: this ad was pre-approved by ClearPath compliance.\n\n{EMAIL_FOOTER}"
    unlabeled = text.replace("This is an advertisement from", "From")
    assert "email.ad_identification" in run(unlabeled, channel=Channel.EMAIL)
    assert "email.ad_identification" not in run(text, channel=Channel.EMAIL)
