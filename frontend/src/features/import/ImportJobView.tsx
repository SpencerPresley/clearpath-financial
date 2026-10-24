/*
 * One import, step by step: columns → values → preview → import → done. The step comes from the job's state
 * (steps.ts); before commit, earlier steps stay one click away in the step list.
 */
import { Button as AriaButton } from 'react-aria-components';

import { Badge } from '../../ui/badges';
import { Button } from '../../ui/Button';
import { cx } from '../../ui/cx';
import { EmptyState } from '../../ui/EmptyState';
import { errorMessage, errorStatus } from '../../ui/errorMessage';
import { Icon } from '../../ui/Icon';
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

const isEditableStep = (id: ImportStep): id is EditableStep =>
  id === 'columns' || id === 'values' || id === 'preview';

function StepList({
  step,
  editable,
  committed,
  onPick,
}: {
  step: ImportStep;
  editable: boolean;
  /** Finished: every step is done, and all but Import can be opened (Done is the summary). */
  committed: boolean;
  onPick: (step: EditableStep | undefined) => void;
}) {
  const index = STEP_ORDER.findIndex((s) => s.id === step);
  return (
    <ol className="app-import-steps" aria-label="Import steps">
      {STEP_ORDER.map((s, i) => {
        const state =
          s.id === step ? 'current' : committed || i < index ? 'done' : i === index ? 'current' : 'upcoming';
        const pickable =
          s.id !== step &&
          ((editable && isEditableStep(s.id)) || (committed && (isEditableStep(s.id) || s.id === 'summary')));
        const body = (
          <>
            <span className="app-import-step-num" aria-hidden="true">
              {state === 'done' ? <Icon name="action.check" size={12} /> : i + 1}
            </span>
            {state === 'done' && <span className="sr-only">Done: </span>}
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
                className={cx('app-import-steps-btn', 'app-import-steps-pick')}
                onPress={() => {
                  onPick(isEditableStep(s.id) ? s.id : undefined);
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
  const commit = useCommit(jobId, () => {
    onStep(undefined);
  });

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
  const committed = data.status === 'committed';
  const step = currentStep(data, preview.data, editable || committed ? requested : undefined);
  const meta = IMPORT_STATUS_META[data.status];
  // Columns always lead to Values: the admin sees the value mapping the importer inferred, even a complete one.
  const saved = () => {
    onStep(step === 'columns' ? 'values' : 'preview');
  };

  let body;
  if (step === 'columns') {
    body = <ColumnsStep key={data.updated_at} job={data} onSaved={saved} readOnly={committed} />;
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
    body = (
      <ValuesStep
        key={data.updated_at}
        job={data}
        preview={preview.data}
        onSaved={saved}
        readOnly={committed}
      />
    );
  } else {
    body = (
      <PreviewStep
        job={data}
        preview={preview.data}
        committing={commit.isPending}
        commitError={commit.error}
        onCommit={commit.commit}
        onMapValues={() => {
          onStep('values');
        }}
      />
    );
  }

  return (
    <div className="app-import-job">
      <div className="app-import-job-head">
        <div className="app-import-job-file">
          <span className="app-import-job-name">{data.filename}</span>
          <Badge meta={meta} />
          <span className="app-import-job-meta">
            Sheet “{data.sheet_name}” · {plural(data.row_count, 'row')}
          </span>
        </div>
        <Button size="sm" variant="ghost" onPress={onBack}>
          Start another import
        </Button>
      </div>
      <StepList step={step} editable={editable} committed={committed} onPick={onStep} />
      {body}
    </div>
  );
}
