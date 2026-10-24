/*
 * Editing a product's terms: the typed form (left), the impact of publishing it (right, and the affected items
 * below), and the publish confirmation. Publish is gated twice: the values must differ from the version the
 * form is based on (the backend refuses identical values), and the preview on screen must be for exactly these
 * values on exactly that base.
 *
 * The base is frozen when the editor opens. If another lead publishes meanwhile (a 409 on publish, or a refetch
 * that brings a newer version), the editor rebases: fields this lead didn't touch take the new version's values,
 * their own edits stay, and Publish waits for a fresh preview. Without that, publishing on top of v13 would carry
 * v12's value for every untouched field and silently undo the other lead's change.
 */
import { useForm, useSelector } from '@tanstack/react-form';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import type {
  CreditCardTerms,
  ImpactPreviewOut,
  OfferTermsOut,
  PersonalLoanTerms,
} from '../../api/generated/model';
import { usePublishOfferTerms } from '../../api/generated/terms/terms';
import { ApiError } from '../../api/mutator';
import { Button } from '../../ui/Button';
import { ModalDialog } from '../../ui/Dialog';
import { CheckboxField, TextAreaField, TextInput } from '../../ui/forms/fields';
import { apiErrorBody, fieldErrorsFrom } from '../../ui/forms/apiErrors';
import { fieldErrorText } from '../../ui/forms/formErrors';
import { plural, PRODUCT_LABELS } from '../../ui/labels';
import { showToast } from '../../ui/toast';
import { AffectedItems, ImpactPanel, outcomeSentence, refreshedCount } from './ImpactPreview';
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
import type { CcFormValues, TermsFieldDef, TermsProduct, TermsValues } from './termsForm';
import { useImpactPreview } from './useImpactPreview';

export interface TermsEditorProps {
  product: TermsProduct;
  /** The version in effect now (null for a product's first terms). Live: it changes when the terms refetch. */
  current: OfferTermsOut | null;
  onClose: () => void;
  /** Unsaved edits exist (the page locks the other product tabs while true). */
  onDirtyChange: (dirty: boolean) => void;
}

export function TermsEditor(props: TermsEditorProps) {
  return props.product === 'personal_loan' ? (
    <PersonalLoanEditor {...props} />
  ) : (
    <CreditCardEditor {...props} />
  );
}

// ---- The frozen base -------------------------------------------------------------------------------

interface Rebase {
  from: OfferTermsOut | null;
  to: OfferTermsOut;
}

/**
 * The version the form was opened on, and the last rebase onto a newer one. Adjusting state while rendering (not
 * in an effect) is React's pattern for state derived from a changed prop.
 */
function useFrozenBase(current: OfferTermsOut | null) {
  const [base, setBase] = useState(current);
  const [rebase, setRebase] = useState<Rebase | null>(null);
  if (current !== null && current.id !== base?.id) {
    setBase(current);
    setRebase({ from: base, to: current });
  }
  return { base, rebase };
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

const UNITS: Partial<Record<TermsFieldDef<string>['kind'], 'percent' | 'money'>> = {
  apr: 'percent',
  percent: 'percent',
  money: 'money',
};

function InputRow({
  def,
  field,
  base,
  baseText,
  autoFocus,
}: {
  def: TermsFieldDef<string>;
  field: RowFieldApi<string>;
  base: string;
  baseText: string;
  autoFocus?: boolean;
}) {
  const changed = inputChanged(def.kind, field.state.value, base);
  const unit = UNITS[def.kind];
  return (
    <div className="app-terms-edit-row" data-changed={changed || undefined} data-unit={unit}>
      <TextInput
        className="app-terms-edit-field"
        label={def.label}
        value={field.state.value}
        onChange={field.handleChange}
        onBlur={field.handleBlur}
        description={def.hint}
        errorMessage={shownError(field)}
        autoFocus={autoFocus}
      />
      {unit !== undefined && (
        <span className="app-terms-unit" aria-hidden="true">
          {unit === 'percent' ? '%' : '$'}
        </span>
      )}
      <span className="app-terms-edit-current" title={baseText}>
        {baseText}
      </span>
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

function baseText(def: TermsFieldDef<string>, base: OfferTermsOut | null): string {
  if (base === null) return '—';
  return formatTermsValue(def.kind, (base.values as unknown as Record<string, unknown>)[def.key]);
}

// ---- Per-product forms ---------------------------------------------------------------------------

type ServerErrors = Record<string, string | undefined>;

function PersonalLoanEditor({ current, onClose, onDirtyChange }: TermsEditorProps) {
  const { base, rebase } = useFrozenBase(current);
  const baseForm = plFormFrom(base?.values as PersonalLoanTerms | undefined);
  const form = useForm({
    defaultValues: baseForm,
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
  useEffect(() => {
    if (rebase === null) return;
    const from = plFormFrom(rebase.from?.values as PersonalLoanTerms | undefined);
    const to = plFormFrom(rebase.to.values as PersonalLoanTerms);
    for (const def of PL_FIELDS) {
      if (!inputChanged(def.kind, form.getFieldValue(def.key), from[def.key])) {
        form.setFieldValue(def.key, to[def.key]);
      }
    }
  }, [rebase, form]);

  const formValues = useSelector(form.store, (state) => state.values);
  const values = plValuesFrom(formValues);
  const fieldsDirty = PL_FIELDS.some((def) => inputChanged(def.kind, formValues[def.key], baseForm[def.key]));
  const incomplete = PL_FIELDS.some((def) => formValues[def.key].trim() === '');

  return (
    <EditorFrame
      product="personal_loan"
      base={base}
      rebase={rebase}
      values={values}
      invalid={incomplete ? 'incomplete' : 'invalid'}
      fieldsDirty={fieldsDirty}
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
      onDirtyChange={onDirtyChange}
    >
      {PL_FIELDS.map((def, index) => (
        <form.Field key={def.key} name={def.key}>
          {(field) => (
            <InputRow
              def={def}
              field={field}
              base={baseForm[def.key]}
              baseText={baseText(def, base)}
              autoFocus={index === 0}
            />
          )}
        </form.Field>
      ))}
    </EditorFrame>
  );
}

type CcTextKey = Exclude<keyof CcFormValues, 'purchase_apr_variable'>;
const CC_OPTIONAL: ReadonlySet<string> = new Set(['intro_apr', 'intro_months']);

function CreditCardEditor({ current, onClose, onDirtyChange }: TermsEditorProps) {
  const { base, rebase } = useFrozenBase(current);
  const baseForm = ccFormFrom(base?.values as CreditCardTerms | undefined);
  const form = useForm({
    defaultValues: baseForm,
    validators: { onChange: ccFormSchema },
    listeners: {
      onChange: ({ fieldApi }) => {
        if (fieldApi.state.meta.errorMap.onServer !== undefined) {
          fieldApi.setMeta((prev) => ({ ...prev, errorMap: { ...prev.errorMap, onServer: undefined } }));
        }
      },
    },
  });
  useEffect(() => {
    if (rebase === null) return;
    const from = ccFormFrom(rebase.from?.values as CreditCardTerms | undefined);
    const to = ccFormFrom(rebase.to.values as CreditCardTerms);
    for (const def of CC_FIELDS) {
      if (!inputChanged(def.kind, form.getFieldValue(def.key), from[def.key])) {
        form.setFieldValue(def.key, to[def.key]);
      }
    }
  }, [rebase, form]);

  const formValues = useSelector(form.store, (state) => state.values);
  const values = ccValuesFrom(formValues);
  const fieldsDirty = CC_FIELDS.some((def) => inputChanged(def.kind, formValues[def.key], baseForm[def.key]));
  const incomplete = CC_FIELDS.some(
    (def) =>
      !CC_OPTIONAL.has(def.key) && def.key !== 'purchase_apr_variable' && formValues[def.key].trim() === '',
  );

  return (
    <EditorFrame
      product="credit_card"
      base={base}
      rebase={rebase}
      values={values}
      invalid={incomplete ? 'incomplete' : 'invalid'}
      fieldsDirty={fieldsDirty}
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
      onDirtyChange={onDirtyChange}
    >
      {CC_FIELDS.map((def, index) =>
        def.key === 'purchase_apr_variable' ? (
          <form.Field key={def.key} name="purchase_apr_variable">
            {(field) => (
              <VariableRow
                def={def}
                field={field}
                base={baseForm.purchase_apr_variable}
                baseText={baseText(def, base)}
              />
            )}
          </form.Field>
        ) : (
          <form.Field key={def.key} name={def.key}>
            {(field) => (
              <InputRow
                def={def}
                field={field}
                base={baseForm[def.key as CcTextKey]}
                baseText={baseText(def, base)}
                autoFocus={index === 0}
              />
            )}
          </form.Field>
        ),
      )}
    </EditorFrame>
  );
}

// ---- Shared frame: note, gate, publish, impact ---------------------------------------------------

/** "9 live items move to Needs re-review; 5 expire." for the toast, from the preview the lead confirmed. */
function publishedLine(preview: ImpactPreviewOut | undefined): string {
  return preview === undefined ? 'Affected items update within a few seconds.' : outcomeSentence(preview);
}

function EditorFrame({
  product,
  base,
  rebase,
  values,
  invalid,
  fieldsDirty,
  fieldNames,
  onServerErrors,
  onClose,
  onDirtyChange,
  children,
}: {
  product: TermsProduct;
  /** The version the form is based on (frozen; moves only on a rebase). */
  base: OfferTermsOut | null;
  rebase: Rebase | null;
  /** The API values when the form is valid; null otherwise. */
  values: TermsValues | null;
  /** Why `values` is null: fields left empty, or a field that breaks a rule. */
  invalid: 'incomplete' | 'invalid';
  fieldsDirty: boolean;
  fieldNames: readonly string[];
  onServerErrors: (fields: ServerErrors) => void;
  onClose: () => void;
  onDirtyChange: (dirty: boolean) => void;
  children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const dirty = fieldsDirty || note.trim() !== '';
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(
    () => () => {
      onDirtyChange(false);
    },
    [onDirtyChange],
  );

  const unchanged = values !== null && base !== null && sameTerms(values, base.values);
  const preview = useImpactPreview(product, unchanged ? null : values, base?.id ?? null);
  const shown = preview.query.data;
  const nextVersion = preview.ready && shown !== undefined ? shown.next_version : (base?.version ?? 0) + 1;
  const productLabel = PRODUCT_LABELS[product].toLowerCase();

  const publish = usePublishOfferTerms({
    mutation: {
      onSuccess: (created) => {
        showToast({
          title: `Published ${productLabel} terms v${String(created.version)}`,
          description: publishedLine(shown),
        });
        void invalidateAfterPublish(queryClient);
        onClose();
      },
      onError: (error) => {
        setConfirming(false);
        const body = apiErrorBody(error);
        if (error instanceof ApiError && error.status === 409 && body?.code === 'conflict') {
          // Another lead published since this form loaded: reload the terms; the editor rebases when they land.
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

  let gate: string;
  if (values === null)
    gate =
      invalid === 'incomplete'
        ? 'Complete the fields to preview the impact.'
        : 'Fix the highlighted fields to preview the impact.';
  else if (unchanged) gate = `Nothing changed yet: these are v${String(base.version)}'s values.`;
  else if (preview.failed) gate = 'Publishing waits for the impact preview.';
  else if (preview.checking) gate = 'Checking the impact…';
  else gate = 'Review the impact, then publish.';

  const canPublish = values !== null && !unchanged && preview.ready && !publish.isPending;
  const changes = values === null || base === null ? [] : termsChanges(base.values, values);
  // The last preview stays on screen (faded) while a field is mid-edit; it's hidden only when nothing changed.
  const panelPreview = unchanged ? undefined : shown;

  return (
    <>
      <form
        aria-label={`Edit ${productLabel} terms`}
        className="app-terms-body"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (canPublish) setConfirming(true);
        }}
      >
        <div className="app-terms-editor">
          <div className="app-terms-edit-head" aria-hidden="true">
            <span>Field</span>
            <span>{base === null ? 'In effect' : `v${String(base.version)} (in effect)`}</span>
            <span>New</span>
          </div>
          {children}
        </div>
        {/* The decision sits with its consequences: impact first, then the note and Publish. */}
        <div className="app-terms-side">
          <ImpactPanel
            nextVersion={nextVersion}
            preview={panelPreview}
            stale={!preview.ready}
            loading={preview.checking && shown === undefined}
            error={preview.failed ? preview.query.error : null}
            onRetry={() => {
              void preview.query.refetch();
            }}
          />
          <div className="app-terms-publish">
            {rebase !== null && (
              <p className="app-note" data-tone="neutral" role="status">
                <span>
                  v{rebase.to.version} was published since you opened this ({rebase.to.created_by_name}).
                  Fields you didn&apos;t change now show v{rebase.to.version}&apos;s values; check the impact
                  again.
                </span>
              </p>
            )}
            <TextAreaField
              label="Note (optional)"
              value={note}
              onChange={setNote}
              rows={2}
              placeholder="Why the terms changed, e.g. Q1 rate card"
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
          </div>
        </div>
      </form>
      {panelPreview !== undefined && <AffectedItems preview={panelPreview} stale={!preview.ready} />}
      <ModalDialog
        title={`Publish ${productLabel} terms v${String(nextVersion)}?`}
        isOpen={confirming}
        onOpenChange={setConfirming}
        role="alertdialog"
        size="md"
      >
        <div className="app-terms-confirm">
          {shown !== undefined && (
            <>
              <p className="app-terms-confirm-summary">{shown.summary}</p>
              <dl className="app-details app-terms-confirm-counts">
                <div className="app-detail-row">
                  <dt>Needs re-review</dt>
                  <dd className="app-figure">{plural(shown.will_need_rereview, 'live item')}</dd>
                </div>
                <div className="app-detail-row">
                  <dt>Expire</dt>
                  <dd className="app-figure">{plural(shown.will_expire, 'item')}</dd>
                </div>
                {shown.already_in_rereview > 0 && (
                  <div className="app-detail-row">
                    <dt>Already in re-review</dt>
                    <dd className="app-figure">
                      {plural(shown.already_in_rereview, 'item')}, {refreshedCount(shown)} with new numbers
                    </dd>
                  </div>
                )}
                <div className="app-detail-row">
                  <dt>Partners</dt>
                  <dd className="app-figure">{plural(shown.partners.length, 'partner')}</dd>
                </div>
              </dl>
            </>
          )}
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
            It takes effect now, and items update within a few seconds. Can&apos;t be undone: publishing the
            old values creates v{nextVersion + 1} and re-sends these items.
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
                  data: { product, values, based_on_terms_id: base?.id ?? null, note: note.trim() },
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
