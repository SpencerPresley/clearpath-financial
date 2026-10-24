import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { getGetMeMockHandler } from '../../api/generated/me/me.msw';
import type { ImpactPreviewIn, OfferTermsOut, OfferTermsPublishIn } from '../../api/generated/model';
import {
  getGetCurrentOfferTermsMockHandler,
  getListOfferTermsMockHandler,
  getPreviewTermsImpactMockHandler,
} from '../../api/generated/terms/terms.msw';
import {
  CC_HISTORY,
  CURRENT_TERMS,
  PL_V12,
  IMPACT_PL,
  LEAD_ME,
  PL_HISTORY,
  PL_V13,
  REVIEWER_ME,
} from '../../test/fixtures/termsPartners';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

function serveHistory() {
  server.use(
    getListOfferTermsMockHandler(({ request }) => {
      const product = new URL(request.url).searchParams.get('product');
      return product === 'credit_card' ? CC_HISTORY : PL_HISTORY;
    }),
  );
}

/** Records every impact-preview body and answers with `IMPACT_PL`. */
function servePreview(): ImpactPreviewIn[] {
  const bodies: ImpactPreviewIn[] = [];
  server.use(
    getPreviewTermsImpactMockHandler(async ({ request }) => {
      bodies.push((await request.json()) as ImpactPreviewIn);
      return IMPACT_PL;
    }),
  );
  return bodies;
}

async function openEditor() {
  await userEvent.click(await screen.findByRole('button', { name: 'Edit terms' }));
  return screen.findByRole('form', { name: 'Edit personal loan terms' });
}

async function setField(label: string, value: string) {
  const input = screen.getByRole('textbox', { name: label });
  await userEvent.clear(input);
  await userEvent.type(input, value);
}

beforeEach(() => {
  server.use(getGetMeMockHandler(LEAD_ME), getGetCurrentOfferTermsMockHandler(CURRENT_TERMS));
  serveHistory();
});

describe('Offer terms', () => {
  it('shows the terms in effect and what changed between versions', async () => {
    renderApp('/terms');
    expect(await screen.findByRole('heading', { name: 'Offer terms', level: 1 })).toBeInTheDocument();
    const current = await screen.findByRole('region', { name: 'Personal loan terms in effect' });
    expect(within(current).getByText('v12')).toBeInTheDocument();
    expect(within(current).getByText(/Priya Raman/)).toBeInTheDocument();
    expect(within(current).getByText('7.49%')).toBeInTheDocument();
    expect(within(current).getByText('24, 36, 60 months')).toBeInTheDocument();
    expect(within(current).getByText('$50,000')).toBeInTheDocument();

    const history = await screen.findByRole('list', { name: 'Personal loan version history' });
    const v12 = within(history).getByRole('listitem', { name: 'v12' });
    expect(within(v12).getByText('APR min')).toBeInTheDocument();
    expect(within(v12).getByText('6.99% → 7.49%')).toBeInTheDocument();
    expect(within(v12).getByText('36, 60 months → 24, 36, 60 months')).toBeInTheDocument();
    expect(within(history).getByRole('listitem', { name: 'v10' })).toHaveTextContent(
      'Earliest version on record',
    );
  });

  it('switches products through the URL; mortgage has no rate terms and no form', async () => {
    const { router } = renderApp('/terms');
    await screen.findByRole('region', { name: 'Personal loan terms in effect' });

    await userEvent.click(screen.getByRole('tab', { name: /Credit card/ }));
    await waitFor(() => {
      expect(router.state.location.search).toMatchObject({ product: 'credit_card' });
    });
    expect(await screen.findByText('Coastal Community Bank')).toBeInTheDocument();
    expect(screen.getByText('0% for 15 months')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: /Mortgage/ }));
    expect(
      await screen.findByRole('heading', { name: 'Mortgage prequalification has no rate terms' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/checked by rules only/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit terms' })).not.toBeInTheDocument();
  });

  it('keeps Publish disabled until a preview exists for the current values, and when nothing changed', async () => {
    const bodies = servePreview();
    renderApp('/terms');
    const form = await openEditor();
    const publish = within(form).getByRole('button', { name: /Publish v13/ });

    expect(publish).toBeDisabled();
    expect(within(form).getByText("Nothing changed yet: these are v12's values.")).toBeInTheDocument();

    await setField('APR min', '12.99');
    expect(await screen.findByText(IMPACT_PL.summary)).toBeInTheDocument();
    await waitFor(() => {
      expect(publish).toBeEnabled();
    });
    expect(bodies.at(-1)).toEqual({
      product: 'personal_loan',
      values: { ...PL_HISTORY[0]?.values, apr_min: '12.99' },
    });

    // 7.490 is v12's 7.49: the backend would refuse it, so the form doesn't offer it.
    await setField('APR min', '7.490');
    expect(publish).toBeDisabled();
    expect(within(form).getByText("Nothing changed yet: these are v12's values.")).toBeInTheDocument();
  });

  it('shows the impact: counts, affected items linking to review, partners', async () => {
    servePreview();
    renderApp('/terms');
    await openEditor();
    await setField('APR min', '12.99');

    const impact = await screen.findByRole('region', { name: 'Impact of publishing v13' });
    expect(await within(impact).findByText(IMPACT_PL.summary)).toBeInTheDocument();
    // The full-review split is a subset of the re-review count (T4).
    expect(
      within(impact).getByRole('group', { name: '9 Needs re-review, all fast-track' }),
    ).toBeInTheDocument();
    expect(within(impact).getByRole('group', { name: '5 Expire, not live' })).toBeInTheDocument();
    expect(within(impact).getByRole('button', { name: '14 affected items ↓' })).toBeInTheDocument();
    expect(within(impact).getByRole('link', { name: 'LoanFinder' })).toHaveAttribute('href', '/partners/31');

    const table = screen.getByRole('table', { name: 'Affected items' });
    const row = within(table).getByRole('row', { name: /CP-1042/ });
    expect(within(row).getByRole('link', { name: 'Spring personal loan email' })).toHaveAttribute(
      'href',
      '/items/1042',
    );
    expect(within(row).getByText('Live')).toBeInTheDocument();
    expect(within(row).getByText('Fast-track')).toBeInTheDocument();
    expect(within(table).getByRole('row', { name: /CP-1043/ })).toHaveTextContent('No number changes');
    // An expired item has no lane (T4).
    expect(within(table).getByRole('row', { name: /CP-1051/ })).toHaveTextContent('—');
  });

  it('validates per product before previewing: max below min goes on the max field', async () => {
    const bodies = servePreview();
    renderApp('/terms');
    const form = await openEditor();
    await setField('APR max', '5');
    await userEvent.tab();

    expect(await within(form).findByText('APR max must be at least APR min.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'APR max' })).toHaveAttribute('aria-invalid', 'true');
    expect(within(form).getByRole('button', { name: /Publish v13/ })).toBeDisabled();
    expect(bodies).toHaveLength(0);
  });

  it('confirms with the summary, publishes against the version it loaded, then reloads', async () => {
    servePreview();
    let published: OfferTermsPublishIn | undefined;
    server.use(
      http.post('*/api/terms', async ({ request }) => {
        published = (await request.json()) as OfferTermsPublishIn;
        server.use(getGetCurrentOfferTermsMockHandler([PL_V13, ...CURRENT_TERMS.slice(1)]));
        return HttpResponse.json(PL_V13, { status: 201 });
      }),
    );
    renderApp('/terms');
    const form = await openEditor();
    await setField('APR min', '12.99');
    await userEvent.type(within(form).getByRole('textbox', { name: 'Note (optional)' }), 'Rate move');
    const publish = within(form).getByRole('button', { name: /Publish v13/ });
    await waitFor(() => {
      expect(publish).toBeEnabled();
    });
    await userEvent.click(publish);

    const dialog = await screen.findByRole('alertdialog', { name: 'Publish personal loan terms v13?' });
    expect(within(dialog).getByText(IMPACT_PL.summary)).toBeInTheDocument();
    expect(within(dialog).getByText('7.49% → 12.99%')).toBeInTheDocument();
    expect(within(dialog).getByText('9 live items')).toBeInTheDocument();
    expect(within(dialog).getByText('5 items')).toBeInTheDocument();
    expect(within(dialog).getByText('2 partners')).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Can't be undone: publishing the old values creates v14/),
    ).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish v13' }));

    await waitFor(() => {
      expect(published).toEqual({
        product: 'personal_loan',
        values: { ...PL_HISTORY[0]?.values, apr_min: '12.99' },
        based_on_terms_id: 112,
        note: 'Rate move',
      });
    });
    expect(await screen.findByText('Published personal loan terms v13')).toBeInTheDocument();
    expect(screen.getByText('9 live items move to Needs re-review; 5 expire.')).toBeInTheDocument();
    const current = await screen.findByRole('region', { name: 'Personal loan terms in effect' });
    expect(await within(current).findByText('v13')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Edit personal loan terms' })).not.toBeInTheDocument();
  });

  it('puts a 422 on its field and a 409 on the form, reloading the terms', async () => {
    servePreview();
    let calls = 0;
    server.use(
      http.post('*/api/terms', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              {
                code: 'invalid_input',
                message: 'Check the highlighted fields.',
                fields: [
                  {
                    loc: ['body', 'values', 'personal_loan', 'apr_min'],
                    message: 'Input should be greater than 0',
                  },
                ],
              },
              { status: 422 },
            )
          : HttpResponse.json(
              {
                code: 'conflict',
                message:
                  'The offer terms changed since you opened this (v13 is in effect now). Review the impact again.',
              },
              { status: 409 },
            );
      }),
    );
    let currentLoads = 0;
    server.use(
      getGetCurrentOfferTermsMockHandler(() => {
        currentLoads += 1;
        return CURRENT_TERMS;
      }),
    );
    renderApp('/terms');
    const form = await openEditor();
    await setField('APR min', '12.99');
    const publish = within(form).getByRole('button', { name: /Publish v13/ });
    await waitFor(() => {
      expect(publish).toBeEnabled();
    });

    await userEvent.click(publish);
    await userEvent.click(
      within(await screen.findByRole('alertdialog', { name: 'Publish personal loan terms v13?' })).getByRole(
        'button',
        { name: 'Publish v13' },
      ),
    );
    expect(await within(form).findByText('Input should be greater than 0')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'APR min' })).toHaveAttribute('aria-invalid', 'true');
    await waitFor(() => {
      expect(
        screen.queryByRole('alertdialog', { name: 'Publish personal loan terms v13?' }),
      ).not.toBeInTheDocument();
    });

    await setField('APR min', '12.98');
    await waitFor(() => {
      expect(publish).toBeEnabled();
    });
    const loadsBefore = currentLoads;
    await userEvent.click(publish);
    await userEvent.click(
      within(await screen.findByRole('alertdialog', { name: 'Publish personal loan terms v13?' })).getByRole(
        'button',
        { name: 'Publish v13' },
      ),
    );
    expect(await within(form).findByRole('alert')).toHaveTextContent('v13 is in effect now');
    await waitFor(() => {
      expect(currentLoads).toBeGreaterThan(loadsBefore);
    });
  });

  it('keeps Publish disabled when the preview fails, and retries it', async () => {
    let calls = 0;
    server.use(
      getPreviewTermsImpactMockHandler(() => {
        calls += 1;
        if (calls === 1) throw new Error('down');
        return IMPACT_PL;
      }),
    );
    renderApp('/terms');
    const form = await openEditor();
    await setField('APR min', '12.99');
    const impact = screen.getByRole('region', { name: 'Impact of publishing v13' });
    expect(await within(impact).findByText(/Couldn.t preview the impact/)).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: /Publish v13/ })).toBeDisabled();

    await userEvent.click(within(impact).getByRole('button', { name: 'Retry' }));
    expect(await within(impact).findByText(IMPACT_PL.summary)).toBeInTheDocument();
    await waitFor(() => {
      expect(within(form).getByRole('button', { name: /Publish v13/ })).toBeEnabled();
    });
  });

  it('after a 409, rebases untouched fields on the new version before Publish can go out (T1)', async () => {
    servePreview();
    const v13: OfferTermsOut = {
      ...PL_V12,
      id: 113,
      version: 13,
      created_by_name: 'Sam Okafor',
      values: { ...PL_V12.values, apr_max: '29.99' },
    };
    const published: OfferTermsPublishIn[] = [];
    server.use(
      http.post('*/api/terms', async ({ request }) => {
        published.push((await request.json()) as OfferTermsPublishIn);
        if (published.length === 1) {
          // Another lead published v13 (APR max 29.99) after this form loaded.
          server.use(
            getGetCurrentOfferTermsMockHandler([v13, ...CURRENT_TERMS.slice(1)]),
            getPreviewTermsImpactMockHandler({ ...IMPACT_PL, current_version: 13, next_version: 14 }),
          );
          return HttpResponse.json(
            {
              code: 'conflict',
              message:
                'The offer terms changed since you opened this (v13 is in effect now). Review the impact again.',
            },
            { status: 409 },
          );
        }
        return HttpResponse.json({ ...v13, id: 114, version: 14 }, { status: 201 });
      }),
    );
    renderApp('/terms');
    const form = await openEditor();
    await setField('APR min', '12.99');
    const publish = within(form).getByRole('button', { name: /Publish v13/ });
    await waitFor(() => {
      expect(publish).toBeEnabled();
    });
    await userEvent.click(publish);
    await userEvent.click(
      within(await screen.findByRole('alertdialog', { name: 'Publish personal loan terms v13?' })).getByRole(
        'button',
        { name: 'Publish v13' },
      ),
    );

    expect(await within(form).findByText(/v13 was published since you opened this/)).toBeInTheDocument();
    // The untouched field moved to v13's value; the lead's own edit stayed.
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'APR max' })).toHaveValue('29.99');
    });
    expect(screen.getByRole('textbox', { name: 'APR min' })).toHaveValue('12.99');
    const again = within(form).getByRole('button', { name: /Publish v14/ });
    await waitFor(() => {
      expect(again).toBeEnabled();
    });
    await userEvent.click(again);
    await userEvent.click(
      within(await screen.findByRole('alertdialog', { name: 'Publish personal loan terms v14?' })).getByRole(
        'button',
        { name: 'Publish v14' },
      ),
    );
    await waitFor(() => {
      expect(published).toHaveLength(2);
    });
    expect(published[1]).toMatchObject({
      based_on_terms_id: 113,
      values: { apr_min: '12.99', apr_max: '29.99' },
    });
  });

  it('shows a min above max on the field just edited and says to fix it (T2)', async () => {
    const bodies = servePreview();
    renderApp('/terms');
    const form = await openEditor();
    await setField('APR min', '40');

    expect(await within(form).findByText('APR min must be at most APR max.')).toBeInTheDocument();
    expect(within(form).getByText('Fix the highlighted fields to preview the impact.')).toBeInTheDocument();
    expect(bodies).toHaveLength(0);
  });

  it('keeps the last preview on screen, marked stale, while a field is being retyped (T3)', async () => {
    servePreview();
    renderApp('/terms');
    await openEditor();
    await setField('APR min', '12.99');
    const impact = await screen.findByRole('region', { name: /Impact of publishing/ });
    expect(await within(impact).findByText(IMPACT_PL.summary)).toBeInTheDocument();

    await userEvent.clear(screen.getByRole('textbox', { name: 'APR min' }));
    expect(within(impact).getByText(IMPACT_PL.summary)).toBeInTheDocument();
    expect(impact).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('table', { name: 'Affected items' })).toBeInTheDocument();
  });

  it('guards unsaved edits: other products are locked, impact links open a new tab (T7)', async () => {
    servePreview();
    renderApp('/terms');
    await openEditor();
    await setField('APR min', '12.99');
    const cc = screen.getByRole('tab', { name: /Credit card/ });
    expect(cc).toHaveAttribute('aria-disabled', 'true');
    expect(
      screen.getByText('Publish or cancel your personal loan edits to switch products.'),
    ).toBeInTheDocument();

    const impact = await screen.findByRole('region', { name: /Impact of publishing/ });
    expect(await within(impact).findByRole('link', { name: 'LoanFinder' })).toHaveAttribute(
      'target',
      '_blank',
    );
    const table = screen.getByRole('table', { name: 'Affected items' });
    expect(within(table).getByRole('link', { name: 'Spring personal loan email' })).toHaveAttribute(
      'target',
      '_blank',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('tab', { name: /Credit card/ })).not.toHaveAttribute('aria-disabled');
    // Focus returns to the trigger.
    expect(screen.getByRole('button', { name: 'Edit terms' })).toHaveFocus();
  });

  it('checks the credit card intro offer together', async () => {
    servePreview();
    renderApp('/terms?product=credit_card');
    await userEvent.click(await screen.findByRole('button', { name: 'Edit terms' }));
    const form = await screen.findByRole('form', { name: 'Edit credit card terms' });
    await userEvent.clear(within(form).getByRole('textbox', { name: 'Intro period' }));
    await userEvent.tab();
    expect(
      await within(form).findByText('Set the intro period with the intro APR, or clear both.'),
    ).toBeInTheDocument();
  });

  it('is read-only for reviewers', async () => {
    server.use(getGetMeMockHandler(REVIEWER_ME));
    renderApp('/terms');
    await screen.findByRole('region', { name: 'Personal loan terms in effect' });
    expect(screen.queryByRole('button', { name: 'Edit terms' })).not.toBeInTheDocument();
  });

  it('says when a product has no terms yet and lets a lead publish the first', async () => {
    server.use(getGetCurrentOfferTermsMockHandler(CURRENT_TERMS.slice(1)));
    server.use(getListOfferTermsMockHandler([] as OfferTermsOut[]));
    renderApp('/terms');
    expect(
      await screen.findByRole('heading', { name: 'No personal loan terms published yet' }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Publish first terms' }));
    const form = await screen.findByRole('form', { name: 'Edit personal loan terms' });
    expect(within(form).getByRole('button', { name: /Publish v1/ })).toBeDisabled();
  });

  it('shows a load error with Retry, and keeps the terms when only history fails', async () => {
    server.use(
      http.get('*/api/terms/current', () =>
        HttpResponse.json({ code: 'server_error', message: 'Terms are unavailable.' }, { status: 503 }),
      ),
    );
    const { unmount } = renderApp('/terms');
    expect(await screen.findByText(/Terms are unavailable\./)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    unmount();

    server.use(
      getGetCurrentOfferTermsMockHandler(CURRENT_TERMS),
      http.get('*/api/terms', () =>
        HttpResponse.json({ code: 'server_error', message: 'History is unavailable.' }, { status: 503 }),
      ),
    );
    renderApp('/terms');
    expect(await screen.findByRole('region', { name: 'Personal loan terms in effect' })).toBeInTheDocument();
    expect(await screen.findByText(/History is unavailable\./)).toBeInTheDocument();
  });
});
