/*
 * One import, step by step: columns → values → preview → import → done. The step comes from the job's state
 * (steps.ts); before commit, earlier steps stay one click away in the step list.
 */
import { Button as AriaButton } from 'react-aria-components';

import type { ImportPreviewOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { cx } from '../../ui/cx';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage, errorStatus } from '../../ui/errorMessage';
import { plural } from '../../ui/labels';
import { SkeletonTable, SkeletonText } from '../../ui/Skeleton';
import { ColumnsStep } from './ColumnsStep';
import { CommitProgress, ImportSummary } from './CommitSteps';
import { IMPORT_STATUS_META } from './labels';
import { PreviewStep } from './PreviewStep';
import type { EditableStep } from './search';
import { currentStep, isEditable, STEP_ORDER } from './steps';
import type { ImportStep } from './steps';
import { useCommit, useImportJob } from './useImportJob';
import { ValuesStep } from './ValuesStep';

function StepList({
  step,
  editable,
  onPick,
}: {
  step: ImportStep;
  editable: boolean;
  onPick: (step: EditableStep) => void;
}) {
  const index = STEP_ORDER.findIndex((s) => s.id === step);
  return (
    <ol className="app-import-steps" aria-label="Import steps">
      {STEP_ORDER.map((s, i) => {
        const state = i < index ? 'done' : i === index ? 'current' : 'upcoming';
        const pickable =
          editable && (s.id === 'columns' || s.id === 'values' || s.id === 'preview') && s.id !== step;
        const body = (
          <>
            <span className="app-import-step-num" aria-hidden="true">
              {i + 1}
            </span>
            {s.label}
          </>
        );
        return (
          <li
            key={s.id}
            className="app-import-steps-item"
            data-state={state}
            aria-current={state === 'current' ? 'step' : undefined}
          >
            {pickable ? (
              <AriaButton
                className={cx('app-import-steps-btn')}
                onPress={() => {
                  onPick(s.id as EditableStep);
                }}
              >
                {body}
              </AriaButton>
            ) : (
              <span className="app-import-steps-btn">{body}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function StepSkeleton() {
  return (
    <div className="app-import-step" role="status" aria-label="Loading the import">
      <SkeletonText width="8rem" />
      <div className="app-import-panel">
        <SkeletonTable rows={8} columns={['18rem', '1fr', '15rem']} />
      </div>
    </div>
  );
}

export function ImportJobView({
  jobId,
  requested,
  onStep,
  onBack,
}: {
  jobId: number;
  requested: EditableStep | undefined;
  onStep: (step: EditableStep | undefined) => void;
  onBack: () => void;
}) {
  const { job, preview } = useImportJob(jobId);
  const commit = useCommit(jobId);

  if (job.isPending) {
    return <StepSkeleton />;
  }
  if (job.isError) {
    const missing = errorStatus(job.error) === 404;
    return (
      <div className="app-import-panel" role="alert">
        <EmptyState
          icon={missing ? 'nav.import' : 'feedback.error'}
          title={missing ? `Import ${String(jobId)} not found` : "Couldn't load this import"}
          action={
            missing ? (
              <Button size="sm" onPress={onBack}>
                Start a new import
              </Button>
            ) : (
              <Button
                size="sm"
                icon="action.reload"
                onPress={() => {
                  void job.refetch();
                }}
              >
                Retry
              </Button>
            )
          }
        >
          {errorMessage(job.error, 'Check your connection and try again.')}
        </EmptyState>
      </div>
    );
  }

  const data = job.data;
  const editable = isEditable(data);
  const step = currentStep(data, preview.data, editable ? requested : undefined);
  const meta = IMPORT_STATUS_META[data.status];
  const saved = (next: ImportPreviewOut) => {
    onStep(step === 'columns' && next.unmapped.length > 0 ? 'values' : 'preview');
  };

  let body;
  if (step === 'columns') {
    body = <ColumnsStep key={data.updated_at} job={data} onSaved={saved} />;
  } else if (step === 'commit') {
    body = <CommitProgress ready={preview.data?.counts.ready} />;
  } else if (step === 'summary') {
    body = <ImportSummary job={data} preview={preview.data} />;
  } else if (preview.isPending) {
    body = <StepSkeleton />;
  } else if (preview.isError) {
    body = (
      <div className="app-import-panel" role="alert">
        <EmptyState
          icon="feedback.error"
          title="Couldn't read the sheet"
          action={
            <Button
              size="sm"
              icon="action.reload"
              onPress={() => {
                void preview.refetch();
              }}
            >
              Retry
            </Button>
          }
        >
          {errorMessage(preview.error, 'Check your connection and try again.')}
        </EmptyState>
      </div>
    );
  } else if (step === 'values') {
    body = <ValuesStep key={data.updated_at} job={data} preview={preview.data} onSaved={saved} />;
  } else {
    body = (
      <PreviewStep
        job={data}
        preview={preview.data}
        committing={commit.isPending}
        commitError={commit.error}
        onCommit={commit.commit}
      />
    );
  }

  return (
    <div className="app-import-job">
      <div className="app-import-job-head">
        <div className="app-import-job-file">
          <span className="app-import-job-name">{data.filename}</span>
          <span className="app-badge" data-tone={meta.tone}>
            {meta.label}
          </span>
          <span className="app-import-job-meta">
            Sheet “{data.sheet_name}” · {plural(data.row_count, 'row')}
          </span>
        </div>
        <Button size="sm" variant="ghost" onPress={onBack}>
          Start another import
        </Button>
      </div>
      <StepList step={step} editable={editable} onPick={onStep} />
      {body}
    </div>
  );
}
