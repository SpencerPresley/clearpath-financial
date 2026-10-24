/*
 * Editing a product's terms: the typed form (left), the impact of publishing it (right, and the affected items
 * below), and the publish confirmation. Publish is gated twice: the values must differ from the version in
 * effect (the backend refuses identical values), and the preview on screen must be for exactly these values.
 */
import { useForm, useSelector } from '@tanstack/react-form';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { ReactNode } from 'react';

import type { CreditCardTerms, OfferTermsOut, PersonalLoanTerms } from '../../api/generated/model';
import { usePublishOfferTerms } from '../../api/generated/terms/terms';
import { ApiError } from '../../api/mutator';
import { Button } from '../../ui/Button';
import { ModalDialog } from '../../ui/Dialog';
import { CheckboxField, TextAreaField, TextInput } from '../../ui/forms/fields';
import { apiErrorBody, apiErrorMessage, fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { fieldErrorText } from '../../ui/forms/formErrors';
import { PRODUCT_LABELS } from '../../ui/labels';
import { showToast } from '../../ui/toast';
import { AffectedItems, ImpactPanel } from './ImpactPreview';
import { invalidateAfterPublish, invalidateTerms } from './invalidate';
import {
  CC_FIELDS,
  ccFormFrom,
  ccFormSchema,
  ccValuesFrom,
  formatTermsValue,
  inputChanged,
  PL_FIELDS,
  plFormFrom,
  plFormSchema,
  plValuesFrom,
  sameTerms,
  termsChanges,
} from './termsForm';
import type { TermsFieldDef, TermsProduct, TermsValues } from './termsForm';
import { useImpactPreview } from './useImpactPreview';

export interface TermsEditorProps {
  product: TermsProduct;
  /** The version in effect when the editor opened (null for a product's first terms). */
  current: OfferTermsOut | null;
  onClose: () => void;
}

export function TermsEditor(props: TermsEditorProps) {
  return props.product === 'personal_loan' ? (
    <PersonalLoanEditor {...props} />
  ) : (
    <CreditCardEditor {...props} />
  );
}

// ---- One row: label | value in effect | new value --------------------------------------------------

interface RowFieldApi<V> {
  state: {
    value: V;
    meta: { errors: readonly unknown[]; isTouched: boolean; errorMap: { onServer?: unknown } };
  };
  handleChange: (value: V) => void;
  handleBlur: () => void;
}

function shownError<V>(field: RowFieldApi<V>): string | undefined {
  const { meta } = field.state;
  return meta.isTouched || meta.errorMap.onServer !== undefined ? fieldErrorText(meta.errors) : undefined;
}

function InputRow({
  def,
  field,
  base,
  baseText,
}: {
  def: TermsFieldDef<string>;
  field: RowFieldApi<string>;
  base: string;
  baseText: string;
}) {
  const changed = inputChanged(def.kind, field.state.value, base);
  return (
    <div className="app-terms-edit-row" data-changed={changed || undefined}>
      <TextInput
        className="app-terms-edit-field"
        label={def.label}
        value={field.state.value}
        onChange={field.handleChange}
        onBlur={field.handleBlur}
        description={def.hint}
        errorMessage={shownError(field)}
      />
      <span className="app-terms-edit-current">{baseText}</span>
    </div>
  );
}

function VariableRow({
  def,
  field,
  base,
  baseText,
}: {
  def: TermsFieldDef<string>;
  field: RowFieldApi<boolean>;
  base: boolean;
  baseText: string;
}) {
  return (
    <div className="app-terms-edit-row" data-changed={field.state.value !== base || undefined}>
      <span className="app-field-label">{def.label}</span>
      <span className="app-terms-edit-current">{baseText}</span>
      <div className="app-terms-edit-control">
        <CheckboxField isSelected={field.state.value} onChange={field.handleChange}>
          Variable APR
        </CheckboxField>
      </div>
    </div>
  );
}

function baseText(def: TermsFieldDef<string>, current: OfferTermsOut | null): string {
  if (current === null) return '—';
  return formatTermsValue(def.kind, (current.values as unknown as Record<string, unknown>)[def.key]);
}

// ---- Per-product forms ---------------------------------------------------------------------------

type ServerErrors = Record<string, string | undefined>;

function PersonalLoanEditor({ current, onClose }: TermsEditorProps) {
  const base = plFormFrom(current?.values as PersonalLoanTerms | undefined);
  const form = useForm({
    defaultValues: base,
    validators: { onChange: plFormSchema },
    listeners: {
      // A server error describes the value that was sent; editing the field retires it.
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
  });
  const formValues = useSelector(form.store, (state) => state.values);
  const values = plValuesFrom(formValues);

  return (
    <EditorFrame
      product="personal_loan"
      current={current}
      values={values}
      fieldNames={PL_FIELDS.map((def) => def.key)}
      onServerErrors={(fields: ServerErrors) => {
        for (const def of PL_FIELDS) {
          form.setFieldMeta(def.key, (prev) => ({
            ...prev,
            errorMap: { ...prev.errorMap, onServer: fields[def.key] },
          }));
        }
      }}
      onClose={onClose}
    >
      {PL_FIELDS.map((def) => (
        <form.Field key={def.key} name={def.key}>
          {(field) => (
            <InputRow def={def} field={field} base={base[def.key]} baseText={baseText(def, current)} />
          )}
        </form.Field>
      ))}
    </EditorFrame>
  );
}

function CreditCardEditor({ current, onClose }: TermsEditorProps) {
  const base = ccFormFrom(current?.values as CreditCardTerms | undefined);
  const form = useForm({
    defaultValues: base,
    validators: { onChange: ccFormSchema },
    listeners: {
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
  });
  const formValues = useSelector(form.store, (state) => state.values);
  const values = ccValuesFrom(formValues);

  return (
    <EditorFrame
      product="credit_card"
      current={current}
      values={values}
      fieldNames={CC_FIELDS.map((def) => def.key)}
      onServerErrors={(fields: ServerErrors) => {
        for (const def of CC_FIELDS) {
          form.setFieldMeta(def.key, (prev) => ({
            ...prev,
            errorMap: { ...prev.errorMap, onServer: fields[def.key] },
          }));
        }
      }}
      onClose={onClose}
    >
      {CC_FIELDS.map((def) =>
        def.key === 'purchase_apr_variable' ? (
          <form.Field key={def.key} name="purchase_apr_variable">
            {(field) => (
              <VariableRow
                def={def}
                field={field}
                base={base.purchase_apr_variable}
                baseText={baseText(def, current)}
              />
            )}
          </form.Field>
        ) : (
          <form.Field key={def.key} name={def.key}>
            {(field) => (
              <InputRow
                def={def}
                field={field}
                base={base[def.key as Exclude<typeof def.key, 'purchase_apr_variable'>]}
                baseText={baseText(def, current)}
              />
            )}
          </form.Field>
        ),
      )}
    </EditorFrame>
  );
}

// ---- Shared frame: note, gate, publish, impact ---------------------------------------------------

function EditorFrame({
  product,
  current,
  values,
  fieldNames,
  onServerErrors,
  onClose,
  children,
}: {
  product: TermsProduct;
  current: OfferTermsOut | null;
  /** The API values when the form is valid; null otherwise. */
  values: TermsValues | null;
  fieldNames: readonly string[];
  onServerErrors: (fields: ServerErrors) => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const unchanged = values !== null && current !== null && sameTerms(values, current.values);
  const preview = useImpactPreview(product, unchanged ? null : values);
  const shown = preview.query.data;
  const nextVersion = preview.ready && shown !== undefined ? shown.next_version : (current?.version ?? 0) + 1;
  const productLabel = PRODUCT_LABELS[product].toLowerCase();

  const publish = usePublishOfferTerms({
    mutation: {
      onSuccess: (created) => {
        showToast({
          title: `Published ${productLabel} terms v${String(created.version)}`,
          description: 'Affected items move to re-review within a few seconds.',
        });
        void invalidateAfterPublish(queryClient);
        onClose();
      },
      onError: (error) => {
        setConfirming(false);
        const body = apiErrorBody(error);
        if (error instanceof ApiError && error.status === 409 && body?.code === 'conflict') {
          // Another lead published since this form loaded: reload the terms, the preview is for the old base.
          setFormError(body.message);
          void invalidateTerms(queryClient);
          return;
        }
        const { fields, form: line } = fieldErrorsFrom(error, fieldNames);
        onServerErrors(fields);
        setFormError(line);
      },
    },
  });

  let gate: ReactNode;
  if (values === null) gate = 'Complete the fields to preview the impact.';
  else if (unchanged) gate = `Nothing changed yet: these are v${String(current.version)}'s values.`;
  else if (preview.failed)
    gate = (
      <>
        Couldn&apos;t preview the impact. {apiErrorMessage(preview.query.error)}{' '}
        <Button
          size="sm"
          variant="ghost"
          onPress={() => {
            void preview.query.refetch();
          }}
        >
          Retry
        </Button>
      </>
    );
  else if (preview.checking) gate = 'Checking the impact…';
  else gate = 'Review the impact, then publish.';

  const canPublish = values !== null && !unchanged && preview.ready && !publish.isPending;
  const changes = values === null || current === null ? [] : termsChanges(current.values, values);

  return (
    <>
      <div className="app-terms-body">
        <form
          aria-label={`Edit ${productLabel} terms`}
          className="app-terms-editor"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (canPublish) setConfirming(true);
          }}
        >
          <div className="app-terms-edit-head" aria-hidden="true">
            <span>Field</span>
            <span>{current === null ? 'In effect' : `v${String(current.version)}`}</span>
            <span>New</span>
          </div>
          {children}
          <TextAreaField
            label="Note (optional)"
            value={note}
            onChange={setNote}
            rows={2}
            placeholder="Why the terms changed, e.g. Q1 rate card"
            className="app-terms-note"
          />
          {formError !== null && (
            <p className="app-form-error" role="alert">
              {formError}
            </p>
          )}
          <div className="app-terms-actions">
            <Button type="submit" variant="primary" isDisabled={!canPublish}>
              {`Publish v${String(nextVersion)}…`}
            </Button>
            <Button variant="ghost" onPress={onClose}>
              Cancel
            </Button>
            <p className="app-terms-gate" aria-live="polite">
              {gate}
            </p>
          </div>
        </form>
        <ImpactPanel
          nextVersion={nextVersion}
          preview={values === null || unchanged ? undefined : shown}
          stale={!preview.ready}
          loading={preview.checking && shown === undefined}
        />
      </div>
      {values !== null && !unchanged && shown !== undefined && (
        <AffectedItems preview={shown} stale={!preview.ready} />
      )}
      <ModalDialog
        title={`Publish ${productLabel} terms v${String(nextVersion)}?`}
        isOpen={confirming}
        onOpenChange={setConfirming}
        role="alertdialog"
        size="md"
      >
        <div className="app-terms-confirm">
          {shown !== undefined && <p className="app-terms-confirm-summary">{shown.summary}</p>}
          {changes.length > 0 && (
            <dl className="app-details">
              {changes.map((change) => (
                <div key={change.field} className="app-detail-row">
                  <dt>{change.label}</dt>
                  <dd className="app-figure">{`${change.from} → ${change.to}`}</dd>
                </div>
              ))}
            </dl>
          )}
          {note.trim() !== '' && <p className="app-muted">Note: {note.trim()}</p>}
          <p className="app-muted">
            It takes effect now. Affected items move to re-review within a few seconds of publishing.
          </p>
          <div className="app-dialog-actions">
            <Button
              onPress={() => {
                setConfirming(false);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              isDisabled={publish.isPending || values === null}
              onPress={() => {
                if (values === null) return;
                setFormError(null);
                publish.mutate({
                  data: { product, values, based_on_terms_id: current?.id ?? null, note: note.trim() },
                });
              }}
            >
              {publish.isPending ? 'Publishing…' : `Publish v${String(nextVersion)}`}
            </Button>
          </div>
        </div>
      </ModalDialog>
    </>
  );
}
