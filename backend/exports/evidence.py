"""Evidence packs: what an approval was recorded against, in a form an examiner can verify offline.

A pack is the latest approving decision's record: the exact approved version, the decision (with every finding
on that version and how it was triaged), the offer-terms versions it quotes, the evidence files it relied on,
and the item's history. `SHA256SUMS` covers every file (`sha256sum -c SHA256SUMS`), and the manifest compares
each evidence file's hash now with the hash the decision recorded.
"""

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pydantic import TypeAdapter

from checks.selectors import FindingRow, list_findings
from core.clock import SYSTEM_CLOCK, Clock
from core.errors import Conflict
from exports.labels import LANE_LABELS, OUTCOME_LABELS, STATUS_LABELS
from reviews.models import APPROVED_OUTCOMES, Attachment, Decision, ReviewItem
from reviews.records import DecisionRow, Evidence, ItemHistory, VersionDetail, get_version, item_history, list_decisions
from reviews.selectors import ItemRow, get_item_row
from terms.selectors import OfferTermsRow, get_offer_terms

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class EvidencePack:
    item: ItemRow
    approved_version: VersionDetail
    decision: DecisionRow
    findings: tuple[FindingRow, ...]
    offer_terms: tuple[OfferTermsRow, ...]
    evidence: tuple[Evidence, ...]
    generated_at: datetime


def latest_approval(item: ReviewItem) -> Decision:
    """The decision a pack records. Raises Conflict when there is none (never approved, or a legacy import)."""
    decision = Decision.objects.filter(item=item, outcome__in=APPROVED_OUTCOMES).order_by("-decided_at", "-pk").first()
    if decision is not None:
        return decision
    if item.is_legacy:
        raise Conflict(
            f"{item.key} is a legacy import with no decision record; its approval is in the tracker history."
        )
    raise Conflict(f"{item.key} has no approval yet; an evidence pack records one.")


def evidence_pack(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> EvidencePack:
    item = get_item_row(item_id=item_id, clock=clock)  # 404 for a missing item
    decision = latest_approval(ReviewItem.objects.get(pk=item_id))
    row = next(d for d in list_decisions(item_id=item_id) if d.id == decision.pk)
    return EvidencePack(
        item=item,
        approved_version=get_version(item_id=item_id, n=row.version_n),
        decision=row,
        findings=list_findings(item_id=item_id, version_n=row.version_n),
        offer_terms=tuple(get_offer_terms(terms_id=t.id, clock=clock) for t in row.terms_versions),
        evidence=row.evidence,
        generated_at=clock.now(),
    )


# --- the zip ---------------------------------------------------------------------------------------------------

_DUMP: Final = {
    "decision": TypeAdapter(DecisionRow),
    "findings": TypeAdapter(tuple[FindingRow, ...]),
    "version": TypeAdapter(VersionDetail),
    "terms": TypeAdapter(OfferTermsRow),
    "item": TypeAdapter(ItemRow),
}


def _json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _history(history: ItemHistory) -> list[dict[str, object]]:
    return [
        {
            "id": e.id,
            "type": e.type.value,
            "at": e.at.isoformat(),
            "actor": e.actor.name if e.actor else None,
            "entity": e.entity.value,
            "entity_id": e.entity_id,
            "from_status": e.from_status.value if e.from_status else None,
            "to_status": e.to_status.value if e.to_status else None,
            "payload": e.payload.model_dump(mode="json"),
        }
        for e in history.entries
    ]


def _summary(pack: EvidencePack, evidence_rows: list[dict[str, object]]) -> str:
    d, v, item = pack.decision, pack.approved_version, pack.item
    terms = ", ".join(f"{t.product.value} v{t.version}" for t in pack.offer_terms) or "none"
    mismatched = [e for e in evidence_rows if not e["matches_decision"]]
    lines = [
        f"Evidence pack: {item.key} {item.title}",
        f"Generated {pack.generated_at.isoformat()}",
        "",
        f"Status now:       {STATUS_LABELS[item.status]}",
        f"Decision:         {OUTCOME_LABELS[d.outcome]} ({LANE_LABELS[d.lane]}) by {d.approver.name}",
        f"Decided at:       {d.decided_at.isoformat()}",
        f"Approval expires: {d.expires_at.isoformat() if d.expires_at else 'not set'}",
        f"Reason:           {d.reason}",
        f"Rule set date:    {d.ruleset_date.isoformat()}",
        f"Approved version: v{v.n}, sha256 {v.content_sha256}",
        f"Offer terms:      {terms}",
        f"Findings:         {len(pack.findings)} on v{v.n} with how each was triaged (decision.json)",
        f"Evidence files:   {len(evidence_rows)}"
        + (f"; {len(mismatched)} no longer match the hash recorded at decision" if mismatched else ""),
    ]
    if d.llm_override_reason:
        lines.append(f"AI check override: {d.llm_override_reason}")
    if d.ai_review_carried_from_n is not None:
        lines.append(f"AI review carried from v{d.ai_review_carried_from_n}")
    lines += ["", "Verify every file: sha256sum -c SHA256SUMS", ""]
    return "\n".join(lines)


def write_evidence_pack(pack: EvidencePack, zf: zipfile.ZipFile, *, prefix: str = "") -> None:
    """Write the pack under `prefix` (e.g. "evidence-packs/CP-12/"). Paths in SHA256SUMS are relative to it."""
    files: dict[str, bytes] = {}
    v = pack.approved_version

    version_name = f"approved-version-v{v.n}.txt"
    files[version_name] = v.content_text.encode()

    files["decision.json"] = _json(
        {
            "item": _DUMP["item"].dump_python(pack.item, mode="json"),
            "decision": _DUMP["decision"].dump_python(pack.decision, mode="json"),
            "decision_label": OUTCOME_LABELS[pack.decision.outcome],
            "findings": _DUMP["findings"].dump_python(pack.findings, mode="json"),
        }
    )

    for terms in pack.offer_terms:
        quotes = [r for r in v.terms_refs if r.offer_terms.id == terms.id]
        files[f"offer-terms/{terms.product.value}-v{terms.version}.json"] = _json(
            {
                "offer_terms": _DUMP["terms"].dump_python(terms, mode="json"),
                "quoted_in_approved_version": [
                    {
                        "field": r.field.value,
                        "quote": r.quote,
                        "quoted_value": r.quoted_value,
                        "span": [r.span.start, r.span.end],
                    }
                    for r in quotes
                ],
            }
        )

    attachments = {a.pk: a for a in Attachment.objects.filter(pk__in=[e.attachment_id for e in pack.evidence])}
    evidence_rows: list[dict[str, object]] = []
    for e in pack.evidence:
        path = f"evidence/{e.attachment_id}-{_SAFE_NAME.sub('_', e.original_name)[:120]}"
        with attachments[e.attachment_id].file.open("rb") as f:
            data = f.read()
        files[path] = data
        now = _sha(data)
        evidence_rows.append(
            {
                "attachment_id": e.attachment_id,
                "kind": e.kind.value,
                "original_name": e.original_name,
                "path": path,
                "sha256_at_decision": e.sha256,
                "sha256": now,
                "matches_decision": now == e.sha256,
            }
        )

    files["history.json"] = _json(_history(item_history(item_id=pack.item.id)))
    files["summary.txt"] = _summary(pack, evidence_rows).encode()
    files["manifest.json"] = _json(
        {
            "item": pack.item.key,
            "decision_id": pack.decision.id,
            "generated_at": pack.generated_at.isoformat(),
            "approved_version": {
                "n": v.n,
                "path": version_name,
                "sha256_recorded": v.content_sha256,
                "sha256": _sha(files[version_name]),
                "matches_recorded": _sha(files[version_name]) == v.content_sha256,
            },
            "evidence": evidence_rows,
            "files": [{"path": p, "sha256": _sha(b), "size": len(b)} for p, b in sorted(files.items())],
        }
    )
    files["SHA256SUMS"] = "".join(f"{_sha(b)}  {p}\n" for p, b in sorted(files.items())).encode()

    stamp = pack.generated_at.timetuple()[:6]
    for path, data in files.items():
        info = zipfile.ZipInfo(prefix + path, date_time=stamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(info, data)
