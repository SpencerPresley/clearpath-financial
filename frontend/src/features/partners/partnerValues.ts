/*
 * The partner form (create and edit): values, the zod schema mirroring the backend's PartnerIn (name required
 * and unique, contact email pattern, lengths), and the mapping to the create body and to a PATCH of only the
 * fields that changed.
 */
import { z } from 'zod';

import { PartnerStatus, PartnerType } from '../../api/generated/model';
import type { PartnerDetailOut, PartnerIn, PartnerUpdateIn } from '../../api/generated/model';

export interface PartnerFormValues {
  name: string;
  type: PartnerType | null;
  status: PartnerStatus;
  website: string;
  contact_email: string;
  /** `YYYY-MM-DD`, or '' while empty. */
  agreement_signed_on: string;
  notes: string;
}

export const PARTNER_FIELD_NAMES = [
  'name',
  'type',
  'status',
  'website',
  'contact_email',
  'agreement_signed_on',
  'notes',
] as const satisfies readonly (keyof PartnerFormValues)[];

export const EMPTY_PARTNER_FORM: PartnerFormValues = {
  name: '',
  type: null,
  status: 'active',
  website: '',
  contact_email: '',
  agreement_signed_on: '',
  notes: '',
};

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export const partnerFormSchema = z.object({
  name: z.string().trim().min(1, 'Enter a name.').max(200, 'Keep the name under 200 characters.'),
  type: z
    .enum(Object.values(PartnerType))
    .nullable()
    .refine((v) => v !== null, 'Choose a type.'),
  status: z.enum(Object.values(PartnerStatus)),
  website: z.string().trim().max(200, 'Keep the website under 200 characters.'),
  contact_email: z
    .string()
    .trim()
    .max(254)
    .refine((v) => v === '' || EMAIL.test(v), 'Enter an email address, e.g. compliance@partner.com.'),
  agreement_signed_on: z.string().refine((v) => v === '' || /^\d{4}-\d{2}-\d{2}$/.test(v), 'Pick a date.'),
  notes: z.string().max(10_000, 'Keep notes under 10,000 characters.'),
});

export function partnerFormFrom(detail: PartnerDetailOut): PartnerFormValues {
  return {
    name: detail.name,
    type: detail.type,
    status: detail.status,
    website: detail.website,
    contact_email: detail.contact_email,
    agreement_signed_on: detail.agreement_signed_on ?? '',
    notes: detail.notes,
  };
}

export function createBody(values: PartnerFormValues): PartnerIn {
  return {
    name: values.name.trim(),
    type: values.type ?? 'affiliate',
    website: values.website.trim(),
    contact_email: values.contact_email.trim(),
    agreement_signed_on: values.agreement_signed_on === '' ? null : values.agreement_signed_on,
    notes: values.notes,
  };
}

/** Only the fields that differ from the partner as loaded (PATCH semantics; the backend uses exclude_unset). */
export function patchBody(values: PartnerFormValues, detail: PartnerDetailOut): PartnerUpdateIn {
  const before = partnerFormFrom(detail);
  const patch: PartnerUpdateIn = {};
  if (values.name.trim() !== before.name) patch.name = values.name.trim();
  if (values.type !== null && values.type !== before.type) patch.type = values.type;
  if (values.status !== before.status) patch.status = values.status;
  if (values.website.trim() !== before.website) patch.website = values.website.trim();
  if (values.contact_email.trim() !== before.contact_email) patch.contact_email = values.contact_email.trim();
  if (values.agreement_signed_on !== before.agreement_signed_on) {
    patch.agreement_signed_on = values.agreement_signed_on === '' ? null : values.agreement_signed_on;
  }
  if (values.notes !== before.notes) patch.notes = values.notes;
  return patch;
}

/** "https://loanfinder.example.com/" → "loanfinder.example.com" for display. */
export function websiteLabel(url: string): string {
  return url.replace(/^https?:\/\//, '').replace(/\/$/, '');
}

/** An href for a website typed without a scheme. */
export function websiteHref(url: string): string {
  return /^https?:\/\//.test(url) ? url : `https://${url}`;
}
