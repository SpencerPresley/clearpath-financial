"""Replay the catalog through the real services, in time order, with a backdated clock.

Every story's steps, the offer-terms publishes, the partner setup, the team-wide events and a daily expiry sweep go
on one timeline sorted by instant. Each entry sets the shared `FixedClock` to its instant and calls the service a
person (or the beat schedule) would have called then. After each entry the outbox is drained in-process: events are
dispatched and their handlers delivered (notifications, the AI-check request), and every AI check the handler
requested is answered by the scripted model at the same instant plus a few seconds. Outbox handlers that would
enqueue a Celery task on commit are pointed at no-ops by `demo.reset.quiet_side_effects`; the runner does that work
itself (the terms fan-out per item, the import commit, the AI check).

The runner raises `SeedError` the moment a story can't be told (a finding it expects to triage isn't open, a gate
refuses a decision, a story ends in the wrong status), so a broken catalog never yields a half-plausible demo.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Final

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Exists, OuterRef

from accounts.models import User
from accounts.services import MeChanges, update_me
from audit.outbox import deliver, dispatch_pending
from checks import handlers as check_handlers
from checks import prereview
from checks.models import CheckRun, Finding
from checks.services import accept_finding, dismiss_finding
from core.clock import FixedClock
from core.domain import (
    AttachmentKind,
    CheckStatus,
    DecisionOutcome,
    DriftResult,
    DriftTrigger,
    FindingSource,
    FindingState,
    ItemStatus,
    ReopenReason,
    TakedownState,
)
from demo.ai import OverloadedModel, ScriptedReviewModel
from demo.story import (
    LOCAL_TZ,
    Accept,
    AiOutage,
    AiResult,
    AiScript,
    Assign,
    Attach,
    Catalog,
    Checklist,
    Claim,
    Comment,
    ConfirmTakedown,
    Decide,
    Dismiss,
    EditFields,
    FastTrack,
    GlobalStep,
    ImportTracker,
    NewRound,
    OnDemoPage,
    PageCheck,
    PartnerEdit,
    PartnerSpec,
    Place,
    Pull,
    Reaffirm,
    ReleaseQueue,
    Resubmit,
    SetAvailability,
    Step,
    Story,
    Submit,
    TermsSpec,
    When,
)
from drift.demo import get_page, render_page, seed_placement
from drift.fetcher import FetchedPage
from drift.services import claim as claim_drift_check
from drift.services import complete as complete_drift_check
from drift.services import request_check as request_drift_check
from imports.services import commit_import, create_sample_import, request_commit
from partners.services import NewPartner, create_partner
from reviews.assignment import assign_item, claim_item
from reviews.decisions import DecisionInput, pull_item, reaffirm, record_decision
from reviews.errors import FindingsNeedTriage
from reviews.models import QUEUE_STATUSES, Placement, ReviewItem, Snapshot
from reviews.placements import PlacementInput, confirm_takedown, record_placement
from reviews.rereview import run_expiry_sweep
from reviews.selectors import live_placements_q
from reviews.services import (
    AttachmentOwner,
    ItemFieldChanges,
    NewComment,
    SubmitItemInput,
    add_attachment,
    add_comment,
    submit_item,
    update_item_fields,
)
from reviews.versions import resubmit_item, start_new_round
from terms.fanout import fan_out_item, recheck_in_flight_item
from terms.fast_track import fast_track_approve
from terms.models import OfferTerms
from terms.selectors import affected_approvals, in_flight_quoting_superseded
from terms.services import PublishTermsInput, publish_terms

AI_LATENCY: Final = timedelta(seconds=6)  # an AI check lands this long after the version it reviews
SWEEP_AT: Final = time(6, 0, tzinfo=UTC)  # the beat schedule's daily expiry sweep (config/settings/base.py)
DRIFT_SWEEP_AT: Final = time(7, 0, tzinfo=UTC)  # and its daily drift sweep, after the expiry sweep

# What a reviewer writes when clearing the human checklist on ordinary copy.
CHECKLIST_NOTES: Final = {
    "human.reg_b_discouragement": "Creative and targeting reviewed: no imagery, wording or audience exclusions "
    "suggesting a prohibited basis.",
    "human.prescreen_format": "Proof reviewed: both notices in the required type size, placement and heading.",
    "human.government_imagery": "No seals, flags, eagles or other government-style imagery in the creative.",
    "human.sms_send_window": "Send schedule is inside 8am-9pm recipient local time.",
}


class SeedError(Exception):
    """The catalog asked for something the services refused or that didn't happen. A bug in the catalog."""


@dataclass(order=True)
class _Entry:
    at: datetime
    seq: int
    label: str = field(compare=False)
    run: Callable[[], None] = field(compare=False)


@dataclass
class RunResult:
    item_ids: dict[str, int]
    users: dict[str, User]
    edited_pages: frozenset[str]  # demo partner pages the stories left edited


class Runner:
    def __init__(self, *, catalog: Catalog, now: datetime, users: dict[str, User]) -> None:
        self.demo_placements: dict[str, tuple[int, str]] = {}  # story key -> (placement id, demo page slug)
        self.edited_pages: set[str] = set()
        self.catalog = catalog
        self.now = now
        self.today = now.astimezone(LOCAL_TZ).date()
        self.clock = FixedClock(now)
        self.users = users
        self.partner_ids: dict[str, int] = {}
        self.item_ids: dict[str, int] = {}
        self.ai_scripts: dict[int, tuple[str, AiScript]] = {}  # version id -> (story key, script)
        self._entries: list[_Entry] = []
        self._stories = {story.key: story for story in catalog.stories}
        # The UTC days each story checks its demo page itself; the drift sweep leaves those days to the story.
        self._page_check_days = {
            story.key: {
                step.at.resolve(now).astimezone(UTC).date() for step in story.steps if isinstance(step, PageCheck)
            }
            for story in catalog.stories
        }

    # --- timeline ----------------------------------------------------------------------------------------------

    def _add(self, at: datetime, label: str, run: Callable[[], None]) -> None:
        if at > self.now:
            raise SeedError(f"{label} is scheduled after the seed time ({at.isoformat()})")
        self._entries.append(_Entry(at, len(self._entries), label, run))

    def run(self) -> RunResult:  # noqa: C901  # builds the timeline from five sources, then plays it
        catalog = self.catalog
        check_handlers.clock = self.clock  # the AI-request handler reads its clock from this seam
        go_live = catalog.go_live.resolve(self.now)
        for n, partner in enumerate(catalog.partners):
            # Entered at go-live, or the morning its agreement was signed if that came later.
            signed = When(on=partner.agreement_signed_on, hhmm="09:00").resolve(self.now)
            at = max(go_live, signed) + timedelta(minutes=n)
            self._add(at, f"partner {partner.key}", lambda p=partner: self._partner(p))
        for spec in catalog.terms:
            self._add(spec.at.resolve(self.now), f"terms {spec.product}", lambda s=spec: self._publish(s))
        for event in catalog.events:
            self._add(event.at.resolve(self.now), type(event).__name__, lambda e=event: self._global(e))
        for story in catalog.stories:
            for step in story.steps:
                self._add(
                    step.at.resolve(self.now),
                    f"{story.key}: {type(step).__name__}",
                    lambda s=story, st=step: self._story_step(s, st),
                )
        first = min(e.at for e in self._entries).date()
        for offset in range((self.now.date() - first).days + 1):
            day = first + timedelta(days=offset)
            at = datetime.combine(day, SWEEP_AT)
            if at <= self.now:
                self._add(at, "expiry sweep", lambda: run_expiry_sweep(clock=self.clock))
            drift_at = datetime.combine(day, DRIFT_SWEEP_AT)
            if drift_at <= self.now:
                self._add(drift_at, "drift sweep", self._drift_sweep)
        for entry in sorted(self._entries):
            self.clock.at = entry.at
            try:
                entry.run()
            except SeedError:
                raise
            except Exception as exc:
                raise SeedError(f"{entry.label} at {entry.at.isoformat()}: {exc}{self._open_summary(entry)}") from exc
            self._drain()
        self.clock.at = self.now
        self._check_endings()
        return RunResult(item_ids=dict(self.item_ids), users=self.users, edited_pages=frozenset(self.edited_pages))

    def _open_summary(self, entry: _Entry) -> str:
        """The open findings on the failing story's current version: what a refused decision is usually about."""
        key = entry.label.split(":", 1)[0]
        if key not in self.item_ids:
            return ""
        item = ReviewItem.objects.get(pk=self.item_ids[key])
        current = item.current_version_id  # pyrefly: ignore[missing-attribute]
        listed = ", ".join(
            f"{f.rule_id} {f.quote!r}"
            for f in Finding.objects.filter(version_id=current, state=FindingState.OPEN.value)
        )
        return f" [status {item.status}; open: {listed or 'none'}]"

    # --- outbox and AI -----------------------------------------------------------------------------------------

    def _drain(self) -> None:
        """Deliver every pending event to its handlers, answer the AI checks they request, repeat until quiet."""
        while True:
            deliveries: list[tuple[int, str]] = []
            dispatched = dispatch_pending(enqueue=lambda event_id, name, out=deliveries: out.append((event_id, name)))
            for event_id, name in deliveries:
                deliver(event_id=event_id, handler_name=name)
            answered = self._answer_ai_checks()
            if not dispatched.events and not answered:
                return

    def _answer_ai_checks(self) -> bool:
        pending = list(
            CheckRun.objects.filter(
                source=FindingSource.LLM, status=CheckStatus.PENDING.value, version_id__in=list(self.ai_scripts)
            ).values_list("version_id", flat=True)
        )
        base = self.clock.at
        for version_id in pending:
            key, script = self.ai_scripts.pop(version_id)
            self.clock.at = base + AI_LATENCY
            if isinstance(script, AiResult):
                self._ai_result(key, version_id, script)
            elif isinstance(script, AiOutage):
                self._ai_outage(key, version_id)
            # AiPending: left as requested; the reconciler re-enqueues it once it's older than STUCK_AFTER.
        self.clock.at = base
        return bool(pending)

    def _ai_result(self, key: str, version_id: int, script: AiResult) -> None:
        claim = prereview.claim(version_id=version_id, clock=self.clock)
        if claim is None:
            raise SeedError(f"{key}: the AI check for version {version_id} wasn't pending")
        text = CheckRun.objects.select_related("version").get(pk=claim.run_id).version.content_text
        model = ScriptedReviewModel.reporting(text, script.findings)
        outcome = prereview.attempt(claim=claim, model_factory=lambda: model, clock=self.clock)
        run = CheckRun.objects.get(pk=claim.run_id)
        if outcome.kind != "succeeded" or run.findings_count != len(script.findings) or run.dropped_findings_count:
            raise SeedError(
                f"{key}: scripted AI check ended {outcome.kind} with {run.findings_count} findings "
                f"({run.dropped_findings_count} dropped); expected {len(script.findings)}"
            )

    def _ai_outage(self, key: str, version_id: int) -> None:
        for _ in range(prereview.MAX_ATTEMPTS):
            claim = prereview.claim(version_id=version_id, clock=self.clock)
            if claim is None:
                raise SeedError(f"{key}: the AI check for version {version_id} wasn't pending")
            outcome = prereview.attempt(
                claim=claim, model_factory=lambda: OverloadedModel(messages=iter([])), clock=self.clock
            )
            if outcome.kind == "failed":
                break
            self.clock.at += timedelta(seconds=outcome.countdown + 1)
        run = CheckRun.objects.get(version_id=version_id, source=FindingSource.LLM)
        if run.status != CheckStatus.FAILED.value:
            raise SeedError(f"{key}: the scripted outage didn't fail the AI check")

    # --- team-wide steps ---------------------------------------------------------------------------------------

    def _partner(self, spec: PartnerSpec) -> None:
        lead = self.users[self.catalog.lead]
        partner_id = create_partner(
            actor=lead,
            data=NewPartner(
                name=spec.name,
                type=spec.type,
                website=spec.website,
                contact_email=spec.contact_email,
                agreement_signed_on=spec.agreement_signed_on,
                notes=spec.notes,
            ),
            clock=self.clock,
        )
        self.partner_ids[spec.key] = partner_id
        add_attachment(
            actor=lead,
            owner=AttachmentOwner("partner", partner_id),
            kind=AttachmentKind.AGREEMENT,
            file=_file(f"{spec.key}-marketing-agreement.txt", spec.agreement),
            clock=self.clock,
        )

    def _publish(self, spec: TermsSpec) -> None:
        current = OfferTerms.objects.filter(product=spec.product, effective_range__upper_inf=True).first()
        publish_terms(
            actor=self.users[self.catalog.lead],
            data=PublishTermsInput(
                product=spec.product,
                values=spec.values,
                based_on_terms_id=current.pk if current is not None else None,
                note=spec.note,
            ),
            clock=self.clock,
        )
        self._drain()
        # What the terms.fan_out handler's per-item tasks do, one item per transaction.
        for affected in affected_approvals(product=spec.product, clock=self.clock):
            fan_out_item(item_id=affected.item_id, clock=self.clock)
        # And what the terms.recheck_in_flight handler's tasks do: re-check in-flight items quoting the old terms.
        for item_id in in_flight_quoting_superseded(product=spec.product, clock=self.clock):
            recheck_in_flight_item(item_id=item_id, clock=self.clock)

    def _global(self, event: GlobalStep) -> None:
        if isinstance(event, SetAvailability):
            update_me(actor=self.users[event.who], changes=MeChanges(is_available=event.available), clock=self.clock)
        elif isinstance(event, ReleaseQueue):
            queued = ReviewItem.objects.filter(
                assignee=self.users[event.who], status__in=QUEUE_STATUSES, is_legacy=False
            ).order_by("pk")
            for item_id, status in queued.values_list("pk", "status"):
                started = status != ItemStatus.SUBMITTED.value
                assign_item(
                    actor=self.users[event.by],
                    item_id=item_id,
                    assignee_id=self.users[event.cover].pk if started else None,
                    reason=event.cover_reason if started else event.reason,
                    clock=self.clock,
                )
        elif isinstance(event, ImportTracker):
            admin = self.users[event.by]
            clock = self.clock if event.dated is None else FixedClock(event.dated.resolve(self.now))
            job_id = create_sample_import(actor=admin, clock=clock)
            request_commit(actor=admin, job_id=job_id, skip_blocked=True, clock=clock)
            commit_import(job_id=job_id, clock=clock)  # what imports.commit (the Celery task) runs

    # --- story steps -------------------------------------------------------------------------------------------

    def _item(self, story: Story) -> ReviewItem:
        return ReviewItem.objects.select_related("current_version", "assignee").get(pk=self.item_ids[story.key])

    def _reviewer(self, story: Story, by: str | None) -> User:
        if by is not None:
            return self.users[by]
        item = self._item(story)
        if item.assignee is None:
            raise SeedError(f"{story.key}: nobody is assigned, so the step needs `by`")
        return item.assignee

    def _marketer(self, story: Story, by: str | None = None) -> User:
        return self.users[by or story.owner]

    def _date(self, offset: int) -> date:
        return self.today + timedelta(days=offset)

    def _remember_ai(self, story: Story, version_id: int, script: AiScript) -> None:
        self.ai_scripts[version_id] = (story.key, script)

    def _open_findings(self, story: Story, rule: str, quote: str | None) -> list[Finding]:
        item = self._item(story)
        found = Finding.objects.filter(version=item.current_version, rule_id=rule, state=FindingState.OPEN.value)
        if quote is not None:
            found = found.filter(quote=quote)
        findings = list(found.order_by("pk"))
        if not findings:
            raise SeedError(f"{story.key}: no open {rule} finding on v{item.current_version.n}")  # pyrefly: ignore[missing-attribute]
        return findings

    def _story_step(self, story: Story, step: Step) -> None:  # noqa: C901, PLR0912, PLR0915  # one branch per step kind
        clock = self.clock
        if isinstance(step, Submit):
            self._submit(story, step)
            return
        item_id = self.item_ids[story.key]
        if isinstance(step, Resubmit):
            result = resubmit_item(
                actor=self._marketer(story),
                item_id=item_id,
                content_text=story.versions[step.text],
                note=step.note,
                clock=clock,
            )
            self._remember_ai(story, result.version_id, step.ai)
        elif isinstance(step, NewRound):
            text = story.versions[step.text] if step.text is not None else None
            result = start_new_round(actor=self._marketer(story), item_id=item_id, content_text=text, clock=clock)
            self._remember_ai(story, result.version_id, step.ai)
        elif isinstance(step, Claim):
            claim_item(actor=self._reviewer(story, step.by), item_id=item_id, clock=clock)
        elif isinstance(step, Assign):
            to = self.users[step.to].pk if step.to is not None else None
            assign_item(actor=self.users[step.by], item_id=item_id, assignee_id=to, reason=step.reason, clock=clock)
        elif isinstance(step, Accept):
            actor = self._reviewer(story, step.by)
            for finding in self._open_findings(story, step.rule, step.quote):
                accept_finding(actor=actor, finding_id=finding.pk, note=step.note, clock=clock)
        elif isinstance(step, Dismiss):
            actor = self._reviewer(story, step.by)
            for finding in self._open_findings(story, step.rule, step.quote):
                dismiss_finding(actor=actor, finding_id=finding.pk, reason=step.reason, clock=clock)
        elif isinstance(step, Checklist):
            self._checklist(story, step)
        elif isinstance(step, Comment):
            author = self._reviewer(story, step.by) if step.by is None else self.users[step.by]
            add_comment(
                actor=author,
                item_id=item_id,
                data=NewComment(body=step.body, mention_user_ids=tuple(self.users[m].pk for m in step.mentions)),
                clock=clock,
            )
        elif isinstance(step, Decide):
            self._decide(story, step)
        elif isinstance(step, EditFields):
            update_item_fields(
                actor=self._reviewer(story, step.by),
                item_id=item_id,
                changes=ItemFieldChanges(tags=step.tags, notes=step.notes, risk_tier=step.risk_tier),
                clock=clock,
            )
        elif isinstance(step, Place):
            record_placement(
                actor=self._marketer(story),
                item_id=item_id,
                data=PlacementInput(
                    location=step.location,
                    first_run=self._date(step.first_run),
                    last_run=self._date(step.last_run) if step.last_run is not None else None,
                    url=step.url or None,
                    monitored=step.monitored,
                ),
                clock=clock,
            )
        elif isinstance(step, Pull):
            pull_item(actor=self._reviewer(story, step.by), item_id=item_id, reason=step.reason, clock=clock)
        elif isinstance(step, ConfirmTakedown):
            requested = Placement.objects.filter(item_id=item_id, takedown_state=TakedownState.REQUESTED.value)
            for placement_id in requested.values_list("pk", flat=True):
                confirm_takedown(actor=self._marketer(story), placement_id=placement_id, clock=clock)
        elif isinstance(step, Reaffirm):
            try:
                reaffirm(actor=self._reviewer(story, step.by), item_id=item_id, reason=step.reason, clock=clock)
            except FindingsNeedTriage:
                if not step.finds_new:
                    raise
        elif isinstance(step, FastTrack):
            item = self._item(story)
            fast_track_approve(
                actor=self._reviewer(story, step.by),
                item_id=item_id,
                version_n=item.current_version.n,  # pyrefly: ignore[missing-attribute]
                reason=step.reason,
                clock=clock,
            )
        elif isinstance(step, OnDemoPage):
            if get_page(step.slug) is None:
                raise SeedError(f"{story.key}: no demo page {step.slug!r}")
            placement_id = seed_placement(
                actor=self._marketer(story, step.by), item_id=item_id, slug=step.slug, clock=clock
            )
            self.demo_placements[story.key] = (placement_id, step.slug)
        elif isinstance(step, PartnerEdit):
            self.edited_pages.add(self._demo_placement(story)[1])
        elif isinstance(step, PageCheck):
            self._check_page(story, step, clock)
        elif isinstance(step, Attach):
            add_attachment(
                actor=self._marketer(story, step.by),
                owner=AttachmentOwner("item", item_id),
                kind=step.kind,
                file=_file(step.name, step.body),
                clock=clock,
            )

    def _demo_placement(self, story: Story) -> tuple[int, str]:
        placed = self.demo_placements.get(story.key)
        if placed is None:
            raise SeedError(f"{story.key}: a page step before OnDemoPage")
        return placed

    def _check_page(self, story: Story, step: PageCheck, clock: FixedClock) -> None:
        found = self._run_page_check(story, clock)
        if found is not step.expect:
            raise SeedError(f"{story.key}: the drift check found {found}, expected {step.expect}")

    def _run_page_check(self, story: Story, clock: FixedClock) -> DriftResult | None:
        """One scheduled drift check, as the worker runs it (request, claim, complete), on the HTML the page serves
        now."""
        placement_id, slug = self._demo_placement(story)
        page = get_page(slug)
        if page is None:
            raise SeedError(f"{story.key}: no demo page {slug!r}")
        snapshot_id = request_drift_check(
            actor=None, placement_id=placement_id, trigger=DriftTrigger.SCHEDULED, clock=clock
        )
        claimed = claim_drift_check(snapshot_id=snapshot_id, clock=clock)
        if claimed is None:
            raise SeedError(f"{story.key}: drift check {snapshot_id} couldn't be claimed")
        html = render_page(page, edited=slug in self.edited_pages, today=clock.today())
        fetched = FetchedPage(url=claimed.url, final_url=claimed.url, status=200, content_type="text/html", text=html)
        return complete_drift_check(claim=claimed, page=fetched, clock=clock).result

    def _drift_sweep(self) -> None:
        """The daily drift sweep (`drift.services.run_sweep`'s filters: monitored, live, approved, not legacy), for
        the placements on the demo pages, so "Checked daily" is true of the seeded history (walkthrough nit 9). Other
        monitored placements point at partner sites nothing here can fetch, so they're left out rather than failed
        (three failed checks would count as missing copy). A page's first check is its story's PageCheck (the demo
        page serves one copy, written for the moment the story checks it: LendCompare's already carries the
        fast-tracked numbers), and the sweep runs from then on; a story's own PageCheck that UTC day is that day's
        check. Every sweep check must find the page unchanged: drift is something a story tells, with a PageCheck."""
        today = self.clock.at.astimezone(UTC).date()
        by_placement = {placement_id: key for key, (placement_id, _) in self.demo_placements.items()}
        due = Placement.objects.filter(
            live_placements_q(self.clock.today()),
            pk__in=list(by_placement),
            monitored=True,
            item__status=ItemStatus.APPROVED.value,
            item__is_legacy=False,
        ).exclude(url="")
        checked_before = due.filter(Exists(Snapshot.objects.filter(placement=OuterRef("pk"))))
        for placement_id in checked_before.order_by("pk").values_list("pk", flat=True):
            story = self._stories[by_placement[placement_id]]
            if today in self._page_check_days.get(story.key, set()):
                continue
            found = self._run_page_check(story, self.clock)
            if found is not DriftResult.UNCHANGED:
                raise SeedError(f"{story.key}: the daily drift sweep found {found}; tell it with a PageCheck step")

    def _submit(self, story: Story, step: Submit) -> None:
        result = submit_item(
            actor=self._marketer(story),
            data=SubmitItemInput(
                title=story.title,
                product=story.product,
                channel=story.channel,
                markets=story.markets,
                content_text=story.versions[0],
                planned_first_run=self._date(story.first_run),
                planned_last_run=self._date(story.last_run) if story.last_run is not None else None,
                partner_id=self.partner_ids[story.partner] if story.partner is not None else None,
                is_prescreen=story.prescreen,
                tags=story.tags,
            ),
            clock=self.clock,
        )
        self.item_ids[story.key] = result.item_id
        self._remember_ai(story, result.version_id, step.ai)

    def _checklist(self, story: Story, step: Checklist) -> None:
        actor = self._reviewer(story, step.by)
        notes = {**CHECKLIST_NOTES, **dict(step.notes)}
        item = self._item(story)
        human = Finding.objects.filter(
            version=item.current_version, source=FindingSource.HUMAN.value, state=FindingState.OPEN.value
        )
        for finding in human.order_by("pk"):
            dismiss_finding(actor=actor, finding_id=finding.pk, reason=notes[finding.rule_id], clock=self.clock)

    def _decide(self, story: Story, step: Decide) -> None:
        item = self._item(story)
        data = DecisionInput(
            outcome=step.outcome,
            version_n=item.current_version.n,  # pyrefly: ignore[missing-attribute]
            reason=step.reason,
            llm_override_reason=step.override,
            edited_content_text=story.versions[step.edited] if step.edited is not None else None,
        )
        try:
            record_decision(actor=self._reviewer(story, step.by), item_id=item.pk, data=data, clock=self.clock)
        except FindingsNeedTriage:
            if not (step.needs_triage and step.outcome is DecisionOutcome.APPROVED_WITH_EDITS):
                raise

    def _check_endings(self) -> None:
        for story in self.catalog.stories:
            item = ReviewItem.objects.get(pk=self.item_ids[story.key])
            reason = ReopenReason(item.reopen_reason) if item.reopen_reason else None
            if ItemStatus(item.status) is not story.expect or (
                story.expect_reason is not None and reason is not story.expect_reason
            ):
                raise SeedError(
                    f"{story.key} ended {item.status}({item.reopen_reason}); the catalog expects "
                    f"{story.expect}({story.expect_reason})"
                )


def _file(name: str, body: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, body.encode(), content_type="text/plain")


def run_catalog(*, catalog: Catalog, now: datetime, users: dict[str, User]) -> RunResult:
    with transaction.atomic():
        return Runner(catalog=catalog, now=now, users=users).run()
