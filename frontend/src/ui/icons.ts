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
  ArrowsCounterClockwiseIcon,
  ArrowSquareOutIcon,
  ArrowUUpLeftIcon,
  BooksIcon,
  CalendarXIcon,
  CaretDoubleDownIcon,
  CaretDoubleUpIcon,
  CaretDownIcon,
  ChartLineIcon,
  ChatCircleIcon,
  CheckCircleIcon,
  CheckIcon,
  CopyIcon,
  CpuIcon,
  DotsThreeIcon,
  EnvelopeSimpleIcon,
  EqualsIcon,
  ExportIcon,
  EyeIcon,
  FilePlusIcon,
  FileTextIcon,
  FlagIcon,
  FolderSimpleUserIcon,
  FunnelIcon,
  GavelIcon,
  HandshakeIcon,
  InfoIcon,
  KeyboardIcon,
  ListChecksIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
  MinusCircleIcon,
  MinusIcon,
  NotePencilIcon,
  PaperPlaneTiltIcon,
  PencilSimpleIcon,
  PercentIcon,
  PlugsIcon,
  ProhibitIcon,
  TrayIcon,
  RulerIcon,
  SidebarSimpleIcon,
  SignOutIcon,
  SortAscendingIcon,
  StackIcon,
  TrayArrowDownIcon,
  UserCircleIcon,
  UserPlusIcon,
  WarningCircleIcon,
  WarningIcon,
  WarningOctagonIcon,
  XCircleIcon,
  XIcon,
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
  'action.toggle_nav': regular(SidebarSimpleIcon),
  'action.sign_out': regular(SignOutIcon),
  // Pull live content: the bare sibling of status.withdrawn (MinusCircle), like Approve / Approved.
  'action.pull': regular(MinusIcon),
  'action.shortcuts': regular(KeyboardIcon),

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

  // System and feedback.
  'system.api_offline': bold(PlugsIcon),
  'feedback.error': regular(WarningCircleIcon),
  'feedback.info': regular(InfoIcon),
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
