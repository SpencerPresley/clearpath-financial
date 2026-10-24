/*
 * New submission (spec §4.3 Intake, product-spec "New submission"). The marketer fills the minimum fields
 * and the copy; code checks run live beside the editor. Submitting with open findings is allowed after an
 * inline count. The item is created first, then each queued file uploads against it.
 */
import { revalidateLogic, useForm, useSelector } from '@tanstack/react-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useState } from 'react';

import { getListItemsQueryKey, submitItem, uploadItemAttachment } from '../../api/generated/items/items';
import { useListPartners } from '../../api/generated/partners/partners';
import { Button } from '../../ui/Button';
import { CopyEditor } from '../../ui/copy/CopyEditor';
import { useLiveChecks } from '../../ui/copy/useLiveChecks';
import { LiveFindings } from '../../ui/findings/LiveFindings';
import { CheckboxField, CheckboxGroupField, SelectField, TextInput } from '../../ui/forms/fields';
import { fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { fieldErrorText } from '../../ui/forms/formErrors';
import { Icon } from '../../ui/Icon';
import { ItemKey } from '../../ui/ItemKey';
import { CHANNEL_LABELS, MARKET_LABELS, PRODUCT_LABELS, plural } from '../../ui/labels';
import { showToast } from '../../ui/toast';
import { EvidenceKindSelect, EvidencePicker, MockupPicker } from './EvidencePicker';
import { FetchFromUrl } from './FetchFromUrl';
import {
  EMPTY_SUBMIT_FORM,
  SUBMIT_FIELD_NAMES,
  isPartnerChannel,
  previewInput,
  queuedUploads,
  submitFormSchema,
  toSubmitIn,
} from './submitForm';
import type { SubmitFormValues } from './submitForm';

const options = <K extends string>(labels: Record<K, string>) =>
  (Object.entries(labels) as [K, string][]).map(([id, label]) => ({ id, label }));

const PRODUCT_OPTIONS = options(PRODUCT_LABELS);
const CHANNEL_OPTIONS = options(CHANNEL_LABELS);
const MARKET_OPTIONS = options(MARKET_LABELS);

/** Create the item, then upload every queued file; a failed upload doesn't undo the item. */
async function createWithFiles(values: SubmitFormValues) {
  const item = await submitItem(toSubmitIn(values));
  const uploads = queuedUploads(values);
  const results = await Promise.allSettled(uploads.map((upload) => uploadItemAttachment(item.id, upload)));
  const failed = uploads.filter((_, index) => results[index]?.status === 'rejected');
  return { item, failed: failed.map((upload) => upload.file.name) };
}

function PartnerField({
  value,
  onChange,
  errorMessage,
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  errorMessage?: string;
}) {
  const partners = useListPartners({ status: 'active' });
  const partnerOptions = (partners.data ?? []).map((partner) => ({
    id: String(partner.id),
    label: partner.name,
  }));
  let description: string | undefined;
  if (partners.isError) description = "Couldn't load partners. Reload the page to try again.";
  else if (partners.isSuccess && partnerOptions.length === 0)
    description = 'No active partners. A compliance lead adds them.';

  return (
    <SelectField
      label="Partner"
      value={value === null ? null : String(value)}
      onChange={(id) => {
        onChange(id === null ? null : Number(id));
      }}
      options={partnerOptions}
      placeholder={partners.isPending ? 'Loading partners…' : 'Select…'}
      description={description}
      errorMessage={errorMessage}
    />
  );
}

export function SubmitPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: createWithFiles,
    onSuccess: ({ item, failed }) => {
      showToast({ title: 'Submitted', description: <ItemKey value={item.key} copyable={false} /> });
      for (const name of failed) {
        showToast({
          title: `${name} didn't upload`,
          description: "Add it from the item's Evidence tab.",
          tone: 'error',
        });
      }
      void queryClient.invalidateQueries({ queryKey: getListItemsQueryKey() });
      void navigate({ to: '/items/$itemId', params: { itemId: String(item.id) } });
    },
    onError: (error) => {
      // A 422's issues go on their fields (cleared when the field changes); anything else is one line.
      const { fields, form: line } = fieldErrorsFrom(error, SUBMIT_FIELD_NAMES);
      for (const name of SUBMIT_FIELD_NAMES) {
        if (form.getFieldMeta(name) === undefined) continue;
        form.setFieldMeta(name, (prev) => ({
          ...prev,
          errorMap: { ...prev.errorMap, onServer: fields[name] },
        }));
      }
      setFormError(line);
    },
  });

  const form = useForm({
    defaultValues: EMPTY_SUBMIT_FORM,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: submitFormSchema },
    onSubmitMeta: { confirmed: false },
    listeners: {
      // Server errors describe the value that was sent; editing the field retires its error.
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
    onSubmit: ({ value, meta }) => {
      if (!meta.confirmed && checks.findings.length > 0) {
        setConfirming(true);
        return;
      }
      setConfirming(false);
      setFormError(null);
      create.mutate(value);
    },
  });

  const values = useSelector(form.store, (state) => state.values);
  const preview = previewInput(values);
  const checks = useLiveChecks(preview);
  const missingContext = preview === null && values.content_text.trim() !== '';

  const openCount = checks.findings.length;
  const blockingCount = checks.findings.filter((finding) => finding.severity === 'blocking').length;

  return (
    <form
      className="app-submit"
      aria-labelledby="submit-title"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void form.handleSubmit();
      }}
    >
      <h1 id="submit-title" className="app-page-title app-submit-title">
        New submission
      </h1>

      <div className="app-submit-fields">
        <form.Field name="title">
          {(field) => (
            <TextInput
              label="Title"
              className="app-submit-wide"
              value={field.state.value}
              onChange={field.handleChange}
              onBlur={field.handleBlur}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <form.Field name="product">
          {(field) => (
            <SelectField
              label="Product"
              value={field.state.value}
              onChange={field.handleChange}
              options={PRODUCT_OPTIONS}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <form.Field
          name="channel"
          listeners={{
            onChange: ({ value }) => {
              // A partner picked for another channel must not ship with this one.
              if (!isPartnerChannel(value)) form.setFieldValue('partner_id', null);
            },
          }}
        >
          {(field) => (
            <SelectField
              label="Channel"
              value={field.state.value}
              onChange={field.handleChange}
              options={CHANNEL_OPTIONS}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <form.Field name="partner_id">
          {(field) =>
            // The slot stays when empty so the fields after it don't shift as the channel changes.
            isPartnerChannel(values.channel) ? (
              <PartnerField
                value={field.state.value}
                onChange={field.handleChange}
                errorMessage={fieldErrorText(field.state.meta.errors)}
              />
            ) : (
              <div className="app-submit-slot" aria-hidden="true" />
            )
          }
        </form.Field>
        <form.Field name="planned_first_run">
          {(field) => (
            <TextInput
              label="First run"
              type="date"
              value={field.state.value}
              onChange={field.handleChange}
              onBlur={field.handleBlur}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <form.Field name="planned_last_run">
          {(field) => (
            <TextInput
              label="Last run"
              type="date"
              description="Optional."
              value={field.state.value}
              onChange={field.handleChange}
              onBlur={field.handleBlur}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <form.Field name="markets">
          {(field) => (
            <CheckboxGroupField
              label="Markets"
              value={field.state.value}
              onChange={field.handleChange}
              options={MARKET_OPTIONS}
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <form.Field name="is_prescreen">
          {(field) => (
            <div className="app-submit-prescreen">
              <CheckboxField isSelected={field.state.value} onChange={field.handleChange}>
                Prescreened firm offer
              </CheckboxField>
            </div>
          )}
        </form.Field>
      </div>

      <div className="app-submit-copy">
        <form.Field name="content_text">
          {(field) => (
            <CopyEditor
              label="Copy"
              name="content_text"
              value={field.state.value}
              onChange={field.handleChange}
              marks={checks.marks}
              placeholder="Paste the ad copy, email, or page text."
              errorMessage={fieldErrorText(field.state.meta.errors)}
            />
          )}
        </form.Field>
        <FetchFromUrl
          onFetched={(fetched) => {
            form.setFieldValue('content_text', fetched.content_text);
            form.setFieldValue('source_url', fetched.url);
            if (form.getFieldValue('title').trim() === '' && fetched.title) {
              form.setFieldValue('title', fetched.title);
            }
          }}
        />
      </div>

      <aside className="app-submit-live">
        <LiveFindings
          checks={checks}
          className="app-live"
          idleMessage={
            missingContext
              ? 'Choose a product, channel, and market to run checks.'
              : 'Checks run as you type.'
          }
        />
      </aside>

      <div className="app-submit-files">
        <form.Field name="mockup">
          {(field) => <MockupPicker value={field.state.value} onChange={field.handleChange} />}
        </form.Field>
        <form.Field name="evidence" mode="array">
          {(field) => (
            <EvidencePicker
              value={field.state.value}
              onChange={field.handleChange}
              renderKind={(index) => (
                <form.Field name={`evidence[${String(index)}].kind` as `evidence[${number}].kind`}>
                  {(kind) => (
                    <EvidenceKindSelect
                      fileName={field.state.value[index]?.file.name ?? ''}
                      value={kind.state.value}
                      onChange={kind.handleChange}
                      errorMessage={fieldErrorText(kind.state.meta.errors)}
                    />
                  )}
                </form.Field>
              )}
            />
          )}
        </form.Field>
      </div>

      <div className="app-submit-actions">
        {formError !== null && (
          <p className="app-form-error" role="alert">
            {formError}
          </p>
        )}
        {confirming && openCount > 0 ? (
          <div className="app-confirm-strip" role="group" aria-label="Submit with open findings">
            <p className="app-confirm-text" role="status">
              <span data-severity={blockingCount > 0 ? 'blocking' : 'warning'} className="inline-flex">
                <Icon name={blockingCount > 0 ? 'severity.blocking' : 'severity.warning'} />
              </span>
              {plural(openCount, 'open finding')}
              {blockingCount > 0 && ` (${String(blockingCount)} blocking)`}. Reviewers will see them.
            </p>
            <Button
              variant="primary"
              // The Submit button it replaces had focus; keep the keyboard user on the next step.
              autoFocus
              isPending={create.isPending}
              onPress={() => {
                void form.handleSubmit({ confirmed: true });
              }}
            >
              Submit anyway
            </Button>
            <Button
              variant="ghost"
              onPress={() => {
                setConfirming(false);
              }}
            >
              Keep editing
            </Button>
          </div>
        ) : (
          <Button type="submit" variant="primary" isPending={create.isPending}>
            {create.isPending ? 'Submitting…' : 'Submit'}
          </Button>
        )}
      </div>
    </form>
  );
}
