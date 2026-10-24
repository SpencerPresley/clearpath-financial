/*
 * Create and edit share one form. Validation runs on submit, then as fields change (TanStack Form's revalidate
 * logic, as New submission does). The page owns the request; it hands server failures back through `report`,
 * which puts 422 issues on their fields and anything else on the form's one line.
 */
import { revalidateLogic, useForm } from '@tanstack/react-form';
import { useState } from 'react';

import { PartnerStatus, PartnerType } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { SelectField, TextAreaField, TextInput } from '../../ui/forms/fields';
import { fieldErrorText } from '../../ui/forms/formErrors';
import { PARTNER_STATUS_LABELS, PARTNER_TYPE_LABELS } from '../../ui/labels';
import { PARTNER_FIELD_NAMES, partnerFormSchema } from './partnerValues';
import type { PartnerFormValues } from './partnerValues';

const TYPE_OPTIONS = Object.values(PartnerType).map((id) => ({ id, label: PARTNER_TYPE_LABELS[id] }));
const STATUS_OPTIONS = Object.values(PartnerStatus).map((id) => ({ id, label: PARTNER_STATUS_LABELS[id] }));

export interface PartnerFormProps {
  label: string;
  initial: PartnerFormValues;
  submitLabel: string;
  pending: boolean;
  /** Edit shows status; a new partner starts active. */
  withStatus?: boolean;
  layout?: 'wide' | 'stacked';
  onSubmit: (values: PartnerFormValues, report: (error: unknown) => void) => void;
  onCancel: () => void;
}

export function PartnerForm({
  label,
  initial,
  submitLabel,
  pending,
  withStatus = false,
  layout = 'wide',
  onSubmit,
  onCancel,
}: PartnerFormProps) {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm({
    defaultValues: initial,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: partnerFormSchema },
    listeners: {
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
    onSubmit: ({ value }) => {
      setFormError(null);
      onSubmit(value, (error) => {
        const { fields, form: line } = fieldErrorsFrom(error, PARTNER_FIELD_NAMES);
        for (const name of PARTNER_FIELD_NAMES) {
          if (form.getFieldMeta(name) === undefined) continue;
          form.setFieldMeta(name, (prev) => ({
            ...prev,
            errorMap: { ...prev.errorMap, onServer: fields[name] },
          }));
        }
        setFormError(line);
      });
    },
  });

  return (
    <form
      aria-label={label}
      className="app-partner-form"
      data-layout={layout}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void form.handleSubmit();
      }}
    >
      <form.Field name="name">
        {(field) => (
          <TextInput
            label="Name"
            isRequired
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
          />
        )}
      </form.Field>
      <form.Field name="type">
        {(field) => (
          <SelectField
            label="Type"
            isRequired
            value={field.state.value}
            onChange={field.handleChange}
            options={TYPE_OPTIONS}
            placeholder="Choose…"
            errorMessage={fieldErrorText(field.state.meta.errors)}
          />
        )}
      </form.Field>
      {withStatus && (
        <form.Field name="status">
          {(field) => (
            <SelectField
              label="Status"
              value={field.state.value}
              onChange={(value) => {
                if (value !== null) field.handleChange(value);
              }}
              options={STATUS_OPTIONS}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
      )}
      <form.Field name="website">
        {(field) => (
          <TextInput
            label="Website"
            type="url"
            placeholder="https://"
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
          />
        )}
      </form.Field>
      <form.Field name="contact_email">
        {(field) => (
          <TextInput
            label="Contact email"
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
          />
        )}
      </form.Field>
      <form.Field name="agreement_signed_on">
        {(field) => (
          <TextInput
            label="Agreement signed"
            type="date"
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
          />
        )}
      </form.Field>
      <form.Field name="notes">
        {(field) => (
          <TextAreaField
            label="Notes"
            className="app-partner-form-wide"
            rows={2}
            value={field.state.value}
            onChange={field.handleChange}
            onBlur={field.handleBlur}
            errorMessage={fieldErrorText(field.state.meta.errors)}
          />
        )}
      </form.Field>
      {formError !== null && (
        <p className="app-form-error" role="alert">
          {formError}
        </p>
      )}
      <div className="app-partner-form-actions">
        <Button type="submit" variant="primary" size="sm" isDisabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
        <Button size="sm" variant="ghost" onPress={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
