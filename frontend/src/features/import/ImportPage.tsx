/*
 * Import (product-spec "Screens", admin): upload a tracker or load the sample, map columns and values, preview
 * the problems, commit. Imported rows become legacy items that carry their history. The job id and the chosen
 * step are the URL (search.ts), so the page can be left and resumed.
 */
import { useNavigate, useSearch } from '@tanstack/react-router';

import { EmptyState } from '../../ui/EmptyState';
import { useViewer } from '../../ui/layout/Viewer';
import { ImportJobView } from './ImportJobView';
import { ImportStart } from './ImportStart';

export function ImportPage() {
  const search = useSearch({ from: '/import' });
  const navigate = useNavigate({ from: '/import' });
  const viewer = useViewer();

  let body;
  if (!viewer.roles.includes('admin')) {
    body = (
      <div className="app-import-panel">
        <EmptyState icon="nav.import" title="Import is for admins">
          Ask an admin to import a tracker. Imported items appear in the library marked Legacy.
        </EmptyState>
      </div>
    );
  } else if (search.job === undefined) {
    body = (
      <ImportStart
        onStarted={(job) => {
          void navigate({ search: { job } });
        }}
      />
    );
  } else {
    body = (
      <ImportJobView
        key={search.job}
        jobId={search.job}
        requested={search.step}
        onStep={(step) => {
          void navigate({ search: (prev) => ({ ...prev, step }) });
        }}
        onBack={() => {
          void navigate({ search: {} });
        }}
      />
    );
  }

  return (
    <section className="app-import" aria-labelledby="import-title">
      <h1 id="import-title" className="app-library-heading">
        Import
      </h1>
      {body}
    </section>
  );
}
