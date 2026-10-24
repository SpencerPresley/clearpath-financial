/*
 * The New submission form: its values, the zod schema TanStack Form validates them with, and the mapping to
 * the API body. The schema extends the generated `SubmitItemBody` (so lengths and enums track the backend)
 * with this form's shapes (empty selects are null, empty dates are '') and the rules the backend enforces
 * across fields: a partner on partner channels, last run not before first run (spec §4.3 Intake).
 */
import { z } from 'zod';

import { SubmitItemBody } from '../../api/generated/items/items.zod';
import type {
  AttachmentKind,
  Channel,
  CheckPreviewIn,
  Market,
  Product,
  SubmitItemIn,
} from '../../api/generated/model';
import { PARTNER_CHANNELS } from '../../ui/labels';

/** Evidence kinds a marketer picks per file; the mockup is the one `creative`, chosen separately. */
export const EVIDENCE_KINDS = [
  'substantiation',
  'rate_sheet',
  'prescreen_criteria',
  'consent_record',
  'agreement',
  'screenshot',
  'other',
] as const satisfies readonly Exclude<AttachmentKind, 'creative'>[];
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

export interface QueuedEvidence {
  file: File;
  kind: EvidenceKind | null;
}

export interface SubmitFormValues {
  title: string;
  product: Product | null;
  channel: Channel | null;
  partner_id: number | null;
  markets: Market[];
  /** `YYYY-MM-DD`, or '' while empty (what a date input gives). */
  planned_first_run: string;
  planned_last_run: string;
  is_prescreen: boolean;
  content_text: string;
  mockup: File | null;
  evidence: QueuedEvidence[];
}

export const EMPTY_SUBMIT_FORM: SubmitFormValues = {
  title: '',
  product: null,
  channel: null,
  partner_id: null,
  markets: ['national'],
  planned_first_run: '',
  planned_last_run: '',
  is_prescreen: false,
  content_text: '',
  mockup: null,
  evidence: [],
};

/** The form fields a 422's `loc` can land on (`fieldErrorsFrom`); anything else is a form-level line. */
export const SUBMIT_FIELD_NAMES = [
  'title',
  'product',
  'channel',
  'partner_id',
  'markets',
  'planned_first_run',
  'planned_last_run',
  'is_prescreen',
  'content_text',
] as const satisfies readonly (keyof SubmitFormValues & keyof SubmitItemIn)[];

export function isPartnerChannel(channel: Channel | null): boolean {
  return channel !== null && PARTNER_CHANNELS.includes(channel);
}

const api = SubmitItemBody.shape;

export const submitFormSchema = SubmitItemBody.extend({
  title: z
    .string()
    .trim()
    .min(1, 'Enter a title.')
    .max(api.title.maxLength ?? Infinity, 'Shorten the title.'),
  product: z.enum(api.product.options, { error: 'Choose a product.' }),
  channel: z.enum(api.channel.options, { error: 'Choose a channel.' }),
  partner_id: z.number().int().nullable(),
  is_prescreen: z.boolean(),
  markets: z.array(z.enum(['national', 'CA'])).min(1, 'Choose at least one market.'),
  planned_first_run: z.iso.date({ error: 'Enter the first run date.' }),
  planned_last_run: z.union([z.literal(''), z.iso.date()], { error: 'Enter a date or leave it empty.' }),
  content_text: z
    .string()
    .refine((text) => text.trim() !== '', 'Paste or type the copy.')
    .refine((text) => text.length <= (api.content_text.maxLength ?? Infinity), 'The copy is too long.'),
  mockup: z.instanceof(File).nullable(),
  evidence: z.array(
    z.object({
      file: z.instanceof(File),
      kind: z.enum(EVIDENCE_KINDS, { error: 'Choose what this file is.' }),
    }),
  ),
})
  // `when` runs these even while other fields are invalid, so every problem shows on the first submit.
  .refine((values) => !isPartnerChannel(values.channel) || values.partner_id != null, {
    message: 'Choose the partner that runs this page.',
    path: ['partner_id'],
    when: () => true,
  })
  .refine(
    (values) =>
      !values.planned_first_run ||
      !values.planned_last_run ||
      values.planned_last_run >= values.planned_first_run,
    {
      message: 'Last run must be on or after the first run.',
      path: ['planned_last_run'],
      when: () => true,
    },
  );

/** The API body for valid form values. A partner chosen before switching channels doesn't ship. */
export function toSubmitIn(values: SubmitFormValues): SubmitItemIn {
  if (values.product === null || values.channel === null) {
    throw new Error('toSubmitIn needs validated values');
  }
  return {
    title: values.title.trim(),
    product: values.product,
    channel: values.channel,
    partner_id: isPartnerChannel(values.channel) ? values.partner_id : null,
    markets: values.markets,
    planned_first_run: values.planned_first_run,
    planned_last_run: values.planned_last_run === '' ? null : values.planned_last_run,
    is_prescreen: values.is_prescreen,
    content_text: values.content_text,
  };
}

/** Every file to upload after the item exists, in order: the mockup first. */
export function queuedUploads(values: SubmitFormValues): { file: File; kind: AttachmentKind }[] {
  const uploads: { file: File; kind: AttachmentKind }[] = [];
  if (values.mockup !== null) {
    uploads.push({ file: values.mockup, kind: 'creative' });
  }
  for (const item of values.evidence) {
    if (item.kind !== null) {
      uploads.push({ file: item.file, kind: item.kind });
    }
  }
  return uploads;
}

/**
 * The live-check request for the current values, or null when there's nothing to check yet: no copy, or
 * the product, channel, or markets the rules key off are missing (the endpoint would 422).
 */
export function previewInput(values: SubmitFormValues): CheckPreviewIn | null {
  if (
    values.content_text.trim() === '' ||
    values.product === null ||
    values.channel === null ||
    values.markets.length === 0
  ) {
    return null;
  }
  const kinds = [...new Set(queuedUploads(values).map((upload) => upload.kind))];
  return {
    content_text: values.content_text,
    product: values.product,
    channel: values.channel,
    markets: values.markets,
    partner_id: isPartnerChannel(values.channel) ? values.partner_id : null,
    is_prescreen: values.is_prescreen,
    attachment_kinds: kinds,
  };
}
