/*
 * Library (product-spec "Screens"): the approved archive and precedent search, for everyone. Two views as tabs
 * (ledger ruling): "Approved to run" (what may run now; default) and "Precedents" (every approval ever given,
 * with the item's status now). Filters, the view, and the query are the URL (search.ts). Export is for
 * reviewers, leads, and admins (marketers get 403 from the server, so they don't see the control).
 */
import { useNavigate, useSearch } from '@tanstack/react-router';
import type { Key } from 'react-aria-components';
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components';

import { useViewer } from '../../ui/layout/Viewer';
import type { Role } from '../../ui/domain';
import { ApprovedList } from './ApprovedList';
import { ExportControl } from './ExportControl';
import { LibraryFilters } from './LibraryFilters';
import { PrecedentResults, PrecedentSearchBar } from './Precedents';
import { CLEARED } from './search';
import type { LibrarySearch, LibraryTab } from './search';
import { useLibraryItems } from './useLibraryItems';

const EXPORT_ROLES: readonly Role[] = ['reviewer', 'lead', 'admin'];

export function LibraryPage() {
  const search = useSearch({ from: '/library' });
  const navigate = useNavigate({ from: '/library' });
  const viewer = useViewer();
  const canExport = viewer.roles.some((role) => EXPORT_ROLES.includes(role));
  const { rows, query } = useLibraryItems(search, search.tab === 'approved');

  const update = (patch: Partial<LibrarySearch>, replace = false) => {
    void navigate({ search: (prev) => ({ ...prev, ...patch }), replace });
  };
  const clear = () => {
    update(CLEARED);
  };

  return (
    <section className="app-library" aria-labelledby="library-title">
      <h1 id="library-title" className="app-library-heading">
        Library
      </h1>
      <Tabs
        selectedKey={search.tab}
        onSelectionChange={(key: Key) => {
          if (key === 'approved' || key === 'precedents') update({ tab: key satisfies LibraryTab });
        }}
        className="app-library-tabs"
      >
        <div className="app-library-tabbar">
          <TabList aria-label="Library views" className="app-tabs app-library-tablist">
            <Tab id="approved" className="app-tab">
              Approved to run
            </Tab>
            <Tab id="precedents" className="app-tab">
              Precedents
            </Tab>
          </TabList>
          {search.tab === 'approved' && canExport && <ExportControl search={search} />}
        </div>
        <TabPanel id="approved" className="app-library-panel">
          <LibraryFilters search={search} onChange={update} />
          <ApprovedList
            search={search}
            rows={rows}
            query={query}
            onClear={clear}
            onPrecedents={() => {
              update({ tab: 'precedents' });
            }}
          />
        </TabPanel>
        <TabPanel id="precedents" className="app-library-panel">
          <PrecedentSearchBar
            search={search}
            onQuery={(q) => {
              update({ query: q }, true);
            }}
            onMode={(mode) => {
              update({ mode });
            }}
          />
          <LibraryFilters search={search} onChange={update} />
          <PrecedentResults
            search={search}
            onMode={(mode) => {
              update({ mode });
            }}
            onClear={clear}
          />
        </TabPanel>
      </Tabs>
    </section>
  );
}
