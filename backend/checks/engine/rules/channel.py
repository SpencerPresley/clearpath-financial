"""Channel and partner rules: SMS (TCPA), email (CAN-SPAM), paid endorsements (regs table rows 14-16)."""

import re
from collections.abc import Iterable

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import (
    ALL_PRODUCTS,
    CANSPAM_16_CFR_316,
    FTC_255_5,
    TCPA_64_1200,
    URL_64_1200,
    URL_255_5,
    URL_7704,
    Hit,
    Rule,
    make_spec,
)
from checks.engine.text import QUOTE_OPEN, compile_i
from checks.engine.types import RuleContext, Span
from core.domain import AttachmentKind, Channel, Severity

SMS = frozenset({Channel.SMS})
EMAIL = frozenset({Channel.EMAIL})

SMS_CONSENT = make_spec(
    "sms.consent_record",
    title="Marketing texts need prior express written consent on file",
    citation="TCPA 47 CFR 64.1200(a)(2), (f)(9)",
    url=URL_64_1200,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    channels=SMS,
    effective_from=TCPA_64_1200,
)
SMS_OPT_OUT = make_spec(
    "sms.opt_out",
    title="Texts tell recipients how to stop them",
    citation="TCPA 47 CFR 64.1200(a)(10)",
    url=URL_64_1200,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    channels=SMS,
    effective_from=TCPA_64_1200,
)
EMAIL_OPT_OUT = make_spec(
    "email.opt_out",
    title="Commercial email has a working opt-out",
    citation="CAN-SPAM 15 U.S.C. 7704(a)(3), (a)(5)(A)(ii); 16 CFR 316.5",
    url=URL_7704,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    channels=EMAIL,
    effective_from=CANSPAM_16_CFR_316,
)
EMAIL_ADDRESS = make_spec(
    "email.postal_address",
    title="Commercial email includes a valid postal address",
    citation="CAN-SPAM 15 U.S.C. 7704(a)(5)(A)(iii); 16 CFR 316.2(p)",
    url=URL_7704,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    channels=EMAIL,
    effective_from=CANSPAM_16_CFR_316,
)
EMAIL_AD_ID = make_spec(
    "email.ad_identification",
    title="Commercial email identifies itself as an advertisement",
    citation="CAN-SPAM 15 U.S.C. 7704(a)(5)(A)(i)",
    url=URL_7704,
    severity=Severity.WARNING,
    products=ALL_PRODUCTS,
    channels=EMAIL,
    effective_from=CANSPAM_16_CFR_316,
)
EMAIL_SUBJECT = make_spec(
    "email.subject_reply_prefix",
    title="Subject lines don't fake a reply or forward",
    citation="CAN-SPAM 15 U.S.C. 7704(a)(2)",
    url=URL_7704,
    severity=Severity.WARNING,
    products=ALL_PRODUCTS,
    channels=EMAIL,
    effective_from=CANSPAM_16_CFR_316,
)
MATERIAL_CONNECTION = make_spec(
    "endorsement.material_connection",
    title="Partner content discloses the paid relationship",
    citation="FTC 16 CFR 255.5; Reg Z comment 2(a)(2)-2; CFPB Supervisory Highlights Issue 37",
    url=URL_255_5,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=FTC_255_5,
)

_STOP = re.compile(
    rf"(?i:\b(?:reply|text|send|respond(?:\s+with)?)\s+{QUOTE_OPEN})"
    r"(?i:STOP|QUIT|END|REVOKE|OPT[-\s]?OUT|CANCEL|UNSUBSCRIBE)\b"
    r"|\b(?:STOP|QUIT|END|CANCEL|UNSUBSCRIBE)\s+to\s+(?i:opt[-\s]?out|stop|end|cancel|unsubscribe)\b"
)
_EMAIL_OPT_OUT = compile_i(
    r"\bunsubscribe\b|\bopt[-\s]?out\b|\bstop\s+receiving\b|\bemail\s+preferences\b|\bmanage\s+(?:your\s+)?"
    r"(?:email\s+)?(?:preferences|subscriptions)\b"
)
_STREET = compile_i(
    r"\b\d{1,6}\s+(?:[\w.'\u2019-]+\s+){0,4}?(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ln|Lane|"
    r"Way|Ct|Court|Pl|Place|Pkwy|Parkway|Sq|Square|Ter|Terrace|Hwy|Highway|Cir|Circle|Plaza|Center|Centre|Tower)"
    r"\b\.?"
)
# "One Market Plaza": a spelled-out building number.
_NAMED_BUILDING = compile_i(
    r"\b(?:One|Two|Three|Four|Five)\s+(?:[A-Z][\w'-]*\s+){1,3}(?:Plaza|Center|Centre|Tower|Square)\b"
)
_PO_BOX = compile_i(r"\bP\.?\s?O\.?\s+Box\s+\d+|\bPost\s+Office\s+Box\s+\d+")
_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_ZIP_REACH = 120
# A clear label, not any prose containing the word "ad" ("this ad was pre-approved" identifies nothing).
_AD_ID = re.compile(
    r"\badvertisement\b|\bsolicitation\b|\b(?:this|it)\s+is\s+an\s+ad\b"
    r"|\b(?:promotional|marketing)\s+(?:email|message|offer)\b|#ad\b"
    r"|^[ \t]*[\[(]?(?:ad|sponsored)[\])]?[ \t]*(?:[.:|\u2013\u2014-]|$)",
    re.IGNORECASE | re.MULTILINE,
)
_REPLY_SUBJECT = re.compile(r"^[ \t]*Subject:[ \t]*(?P<prefix>(?:RE|FWD?)[ \t]*:)", re.IGNORECASE | re.MULTILINE)
_DISCLOSURE = compile_i(
    r"#(?:ad|sponsored|paid|partner|paidpartner|affiliate)\b|\bpaid\s+(?:partner(?:ship)?|promotion|endorsement|"
    r"advertisement)\b|\bsponsored\b|\badvertiser\s+disclosure\b|\bcompensat(?:ed|ion)\b|\bcommissions?\b"
    r"|\baffiliate\s+(?:links?|disclosure|partner)\b|\bmaterial\s+connection\b|\bwe\s+(?:may\s+)?(?:be\s+)?paid\b"
)


def _sms_consent(ctx: RuleContext, _a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if AttachmentKind.CONSENT_RECORD not in ctx.attachment_kinds:
        yield Hit(
            None,
            'Attach the consent record: signed written consent naming the number, with "not a condition of '
            'purchase" language.',
            "Attach the consent record (kind: consent_record).",
        )


def _sms_opt_out(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if not _STOP.search(a.text):
        yield Hit(None, "Tell recipients how to stop texts.", '"Reply STOP to opt out."')


def _email_opt_out(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if not _EMAIL_OPT_OUT.search(a.text):
        yield Hit(None, "Add an unsubscribe link or opt-out instructions.", '"Unsubscribe"')


def _has_postal_address(text: str) -> bool:
    for m in (*_STREET.finditer(text), *_NAMED_BUILDING.finditer(text), *_PO_BOX.finditer(text)):
        if _ZIP.search(text, m.end(), min(len(text), m.end() + _ZIP_REACH)):
            return True
    return False


def _email_address(_ctx: RuleContext, a: Analysis, c: EngineConfig) -> Iterable[Hit]:
    if not _has_postal_address(a.text):
        yield Hit(
            None,
            "Add a valid physical postal address (street address or registered PO box).",
            f'"{c.postal_address}"',
        )


def _email_ad_id(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if not _AD_ID.search(a.text):
        yield Hit(
            None,
            "Identify the email as an advertisement, unless recipients gave prior affirmative consent.",
            '"This is an advertisement."',
        )


def _email_subject(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if m := _REPLY_SUBJECT.search(a.text):
        yield Hit(
            Span(m.start("prefix"), m.end("prefix")),
            "A reply or forward prefix implies an existing conversation; drop it.",
            None,
        )


def _material_connection(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    partner_content = ctx.partner_type is not None or ctx.channel is Channel.AFFILIATE_PAGE
    if partner_content and not _DISCLOSURE.search(a.text):
        yield Hit(
            None,
            "Disclose the paid relationship clearly, near the top.",
            '"#ad" or "Advertiser disclosure: we receive compensation from ClearPath."',
        )


RULES: tuple[Rule, ...] = (
    Rule(SMS_CONSENT, _sms_consent),
    Rule(SMS_OPT_OUT, _sms_opt_out),
    Rule(EMAIL_OPT_OUT, _email_opt_out),
    Rule(EMAIL_ADDRESS, _email_address),
    Rule(EMAIL_AD_ID, _email_ad_id),
    Rule(EMAIL_SUBJECT, _email_subject),
    Rule(MATERIAL_CONNECTION, _material_connection),
)
