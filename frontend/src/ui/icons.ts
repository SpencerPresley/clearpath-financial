/*
 * The icon registry (spec §5.2a): the only file allowed to import Phosphor (enforced by
 * no-restricted-imports in eslint.config.ts). Components render icons with <Icon name="..."> (Icon.tsx).
 *
 * Rules:
 * - Same meaning, same glyph everywhere: pick the key, never the glyph.
 * - Different meanings, different glyphs: icons.test.ts fails on any shared glyph not in SHARED_GLYPHS.
 * - Decision pairs: the state is enclosed (CheckCircle, XCircle), the action bare (Check) or a sibling
 *   glyph (ArrowUUpLeft vs ArrowBendUpLeft), so "Approved" and "Approve" are distinct but read as related.
 * - Finding source is carried by shape: code check = a filled rule (Ruler, spec §5.2 "solid rule icon"),
 *   AI suggestion = outline, checklist = its own glyph. No sparkles or wands for AI (spec §5.6).
 * - Distinct objects aren't enough: glyphs for different meanings must also differ in silhouette at 16px
 *   (blocking = filled octagon; app error = outline circle). Check new glyphs on /dev/design.
 */
import {
  ArrowBendUpLeftIcon,
  ArrowClockwiseIcon,
  ArrowCounterClockwiseIcon,
  ArrowDownIcon,
  ArrowRightIcon,
  ArrowsCounterClockwiseIcon,
  ArrowsDownUpIcon,
  ArrowSquareOutIcon,
  ArrowUpIcon,
  ArrowUUpLeftIcon,
  AtIcon,
  BellIcon,
  BookmarkSimpleIcon,
  BooksIcon,
  CalendarXIcon,
  CaretDoubleDownIcon,
  CaretDoubleUpIcon,
  CaretDownIcon,
  ChartLineIcon,
  ChatCircleIcon,
  ChatTeardropTextIcon,
  CheckCircleIcon,
  CheckFatIcon,
  CheckIcon,
  CheckSquareIcon,
  ChecksIcon,
  CircleDashedIcon,
  CircleNotchIcon,
  ClockCountdownIcon,
  ColumnsIcon,
  CopyIcon,
  CpuIcon,
  DotsSixVerticalIcon,
  DotsThreeIcon,
  DownloadSimpleIcon,
  EnvelopeSimpleIcon,
  EqualsIcon,
  ExportIcon,
  EyeIcon,
  EyeSlashIcon,
  FilePlusIcon,
  FileDashedIcon,
  FileTextIcon,
  FlagIcon,
  FolderSimpleUserIcon,
  FunnelIcon,
  GavelIcon,
  GitDiffIcon,
  HandshakeIcon,
  HourglassMediumIcon,
  HourglassSimpleIcon,
  InfoIcon,
  KanbanIcon,
  KeyboardIcon,
  ListChecksIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
  MinusCircleIcon,
  NotePencilIcon,
  PaperPlaneRightIcon,
  PaperPlaneTiltIcon,
  PencilSimpleIcon,
  PercentIcon,
  PlugsIcon,
  PlusIcon,
  ProhibitIcon,
  RulerIcon,
  SealCheckIcon,
  SidebarSimpleIcon,
  SignInIcon,
  SignOutIcon,
  SortAscendingIcon,
  StackIcon,
  StopIcon,
  TableIcon,
  TagIcon,
  TrayArrowDownIcon,
  TrayIcon,
  UserCircleIcon,
  UserIcon,
  UserPlusIcon,
  WarningCircleIcon,
  WarningIcon,
  WarningOctagonIcon,
  XCircleIcon,
  XIcon,
  XSquareIcon,
} from '@phosphor-icons/react';
import type { Icon as PhosphorIcon, IconWeight } from '@phosphor-icons/react';

export type { IconWeight };

export interface IconDef {
  glyph: PhosphorIcon;
  weight: IconWeight;
}

const regular = (glyph: PhosphorIcon): IconDef => ({ glyph, weight: 'regular' });
const fill = (glyph: PhosphorIcon): IconDef => ({ glyph, weight: 'fill' });
const bold = (glyph: PhosphorIcon): IconDef => ({ glyph, weight: 'bold' });

export const icons = {
  // Item status (ItemStatus). Tone comes from the badge, the glyph from here.
  'status.draft': regular(NotePencilIcon),
  'status.submitted': regular(PaperPlaneTiltIcon),
  'status.in_review': regular(EyeIcon),
  'status.changes_requested': regular(ArrowUUpLeftIcon),
  'status.approved': regular(CheckCircleIcon),
  'status.rejected': regular(XCircleIcon),
  'status.needs_rereview': bold(ArrowsCounterClockwiseIcon),
  'status.expired': regular(CalendarXIcon),
  'status.withdrawn': regular(MinusCircleIcon),

  // Finding severity. Filled: these are the loudest marks on a review screen.
  'severity.blocking': fill(WarningOctagonIcon),
  'severity.warning': fill(WarningIcon),

  // Finding source (spec §5.2: shape, not color).
  'source.code': fill(RulerIcon),
  'source.ai': regular(CpuIcon),
  'source.human': regular(ListChecksIcon),

  // Risk tier: Jira-style priority marks, read by direction.
  'risk.high': bold(CaretDoubleUpIcon),
  'risk.medium': bold(EqualsIcon),
  'risk.low': bold(CaretDoubleDownIcon),

  // Entities (glossary, spec §5.4).
  'entity.item': regular(FileTextIcon),
  'entity.version': regular(StackIcon),
  'entity.partner': regular(HandshakeIcon),
  'entity.terms': regular(PercentIcon),
  'entity.placement': regular(MapPinIcon),
  'entity.decision': regular(GavelIcon),
  'entity.finding': regular(FlagIcon),
  'entity.user': regular(UserIcon),
  'entity.tag': regular(TagIcon),

  // Actions.
  'action.approve': bold(CheckIcon),
  'action.request_changes': regular(ArrowBendUpLeftIcon),
  'action.reject': regular(ProhibitIcon),
  'action.assign': regular(UserPlusIcon),
  'action.comment': regular(ChatCircleIcon),
  'action.export': regular(ExportIcon),
  'action.import': regular(TrayArrowDownIcon),
  'action.search': regular(MagnifyingGlassIcon),
  'action.filter': regular(FunnelIcon),
  'action.sort': regular(SortAscendingIcon),
  'action.copy': regular(CopyIcon),
  'action.edit': regular(PencilSimpleIcon),
  'action.close': regular(XIcon),
  'action.more': bold(DotsThreeIcon),
  'action.expand': regular(CaretDownIcon),
  'action.open_external': regular(ArrowSquareOutIcon),
  /** Go to another screen in this app (same tab); open_external is for new tabs and other sites. */
  'action.open': regular(ArrowRightIcon),
  'action.toggle_nav': regular(SidebarSimpleIcon),
  'action.sign_out': regular(SignOutIcon),
  // Pull live content: take it out of public view (the unpublish idiom). Not a download arrow
  // (action.import's territory) and not a cloud-slash (reads as offline, system.api_offline).
  'action.pull': regular(EyeSlashIcon),
  'action.shortcuts': regular(KeyboardIcon),
  'action.sign_in': regular(SignInIcon),
  'action.columns': regular(ColumnsIcon),
  'action.save_view': regular(BookmarkSimpleIcon),
  'action.reload': regular(ArrowClockwiseIcon),
  'action.reset_demo': regular(ArrowCounterClockwiseIcon),
  'action.drag': bold(DotsSixVerticalIcon),
  /** Save a built file (export, evidence pack) to disk; action.export starts building it. */
  'action.download': regular(DownloadSimpleIcon),
  /** A chosen option in a checkable menu or list (not a decision: that's action.approve). */
  'action.check': bold(CheckFatIcon),
  /** Background jobs (imports): waiting to run, running, finished, failed. */
  'job.pending': regular(CircleDashedIcon),
  'job.running': regular(HourglassMediumIcon),
  'job.done': regular(CheckSquareIcon),
  'job.failed': regular(XSquareIcon),
  /** Start something new in place (a new assistant thread). */
  'action.new': regular(PlusIcon),
  /**
   * Send an email the assistant drafted. Filled and level, so it reads apart from status.submitted (an outline,
   * tilted plane) at 16px; the button always carries the label "Send email".
   */
  'action.send': fill(PaperPlaneRightIcon),
  /** Stop a running operation (the assistant's reply). */
  'action.stop': fill(StopIcon),
  // Column sort state (server-sorted columns only).
  'sort.ascending': regular(ArrowUpIcon),
  'sort.descending': regular(ArrowDownIcon),
  'sort.none': regular(ArrowsDownUpIcon),
  // Queue layouts (table is the default; board is the toggle, decisions.md "Queue views").
  'view.table': regular(TableIcon),
  'view.board': regular(KanbanIcon),

  // Drift monitor: what a check of a live placement's page found. A failed check uses feedback.error; checking
  // again is action.reload (fetch the page again).
  'drift.unchanged': regular(SealCheckIcon),
  'drift.modified': regular(GitDiffIcon),
  'drift.missing': regular(FileDashedIcon),

  // Navigation sections (product-spec Screens). Shares with entities/actions are allowlisted below.
  'nav.queue': regular(TrayIcon),
  'nav.my_submissions': regular(FolderSimpleUserIcon),
  'nav.new_submission': regular(FilePlusIcon),
  'nav.library': regular(BooksIcon),
  'nav.offer_terms': regular(PercentIcon),
  'nav.partners': regular(HandshakeIcon),
  'nav.metrics': regular(ChartLineIcon),
  'nav.import': regular(TrayArrowDownIcon),
  'nav.outbox': regular(EnvelopeSimpleIcon),
  'nav.user': regular(UserCircleIcon),
  // The assistant panel: a speech bubble with text, not a sparkle or wand (spec §5.6); ChatCircle is comments.
  'nav.assistant': regular(ChatTeardropTextIcon),
  /** The notifications inbox in the topbar. */
  'nav.notifications': regular(BellIcon),

  // Notifications whose meaning no status or action already has. The rest reuse their key: an assignment is
  // action.assign, a decision its outcome's status, a re-review status.needs_rereview, drift's page findings
  // severity.blocking.
  /** You were @mentioned in a comment. */
  'notify.mention': regular(AtIcon),
  /** An approval runs out soon (30 days ahead); status.expired (CalendarX) is the state after it has. */
  'notify.expiring': regular(ClockCountdownIcon),
  /** Mark every notification read. A double check, apart from action.check (a chosen option). */
  'action.mark_all_read': regular(ChecksIcon),

  // System and feedback.
  'system.api_offline': bold(PlugsIcon),
  'feedback.error': regular(WarningCircleIcon),
  'feedback.info': regular(InfoIcon),
  /** In progress, for steps that finish on their own (an assistant tool call); spun by .app-spin. */
  'feedback.running': bold(CircleNotchIcon),
  /** Paused on a person (an email draft waiting for approval). */
  'feedback.awaiting': regular(HourglassSimpleIcon),
} as const satisfies Record<string, IconDef>;

export type IconKey = keyof typeof icons;

/** Intentional glyph shares: same meaning reached from two places. Anything else fails icons.test.ts. */
export const SHARED_GLYPHS: readonly { keys: readonly IconKey[]; why: string }[] = [
  {
    keys: ['entity.terms', 'nav.offer_terms'],
    why: 'The Offer terms nav section is the offer-terms entity; a different glyph would imply a different thing.',
  },
  {
    keys: ['entity.partner', 'nav.partners'],
    why: 'The Partners nav section lists partner entities.',
  },
  {
    keys: ['action.import', 'nav.import'],
    why: 'The Import section exists to perform the import action.',
  },
];
