import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { uploadItemAttachment } from '../../api/generated/items/items';
import { getListPartnersMockHandler } from '../../api/generated/partners/partners.msw';
import type {
  AttachmentOut,
  CheckPreviewIn,
  CheckPreviewOut,
  PartnerRowOut,
  SubmitItemIn,
} from '../../api/generated/model';
import { ApiError } from '../../api/mutator';
import { MARKETER, NOW, itemFixture, spanOf } from '../../test/fixtures/review';
import { server } from '../../test/server';
import { showToast } from '../../ui/toast';
import { SubmitPage } from './SubmitPage';
import { renderAtRoute } from '../../test/router';

// jsdom's File can't go through undici's multipart encoder, so uploads are asserted at the client call.
vi.mock('../../api/generated/items/items', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/generated/items/items')>()),
  uploadItemAttachment: vi.fn(),
}));
vi.mock('../../ui/toast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../ui/toast')>()),
  showToast: vi.fn(),
}));

const COPY = 'Need cash fast? 💸 Personal loans as low as 5.99% APR.';
const CLEAN_COPY = 'Personal loans for home projects.';

const PARTNERS: PartnerRowOut[] = [
  {
    id: 7,
    name: 'LendCompare',
    type: 'affiliate',
    status: 'active',
    item_count: 3,
    approved_count: 2,
    open_findings_count: 0,
    last_submitted_at: null,
  },
];

function uploaded(kind: AttachmentOut['kind'], name: string): AttachmentOut {
  return {
    id: 1,
    kind,
    original_name: name,
    content_type: 'application/octet-stream',
    size_bytes: 3,
    sha256: 'f'.repeat(64),
    uploaded_by: MARKETER,
    uploaded_at: NOW,
    download_url: '/api/attachments/1/download',
  };
}

/** Live checks: one blocking finding on "as low as" wherever it sits (code-point span, as the API sends). */
function previewHandler(requests: CheckPreviewIn[] = []) {
  return http.post('*/api/checks/preview', async ({ request }) => {
    const body = (await request.json()) as CheckPreviewIn;
    requests.push(body);
    const out: CheckPreviewOut = {
      ruleset_key: 'k',
      terms_refs: [],
      findings: body.content_text.includes('as low as')
        ? [
            {
              rule_id: 'pricing.as_low_as_range',
              citation: 'Reg Z 12 CFR 1026.24(a)',
              source: 'code',
              severity: 'blocking',
              message: 'Rate claim needs the full APR range',
              suggested_fix: 'Show the range: 5.99%–35.99% APR',
              span: spanOf(body.content_text, 'as low as'),
              quote: 'as low as',
            },
          ]
        : [],
    };
    return HttpResponse.json(out);
  });
}

function recordSubmits(log: string[], bodies: SubmitItemIn[] = []) {
  return http.post('*/api/items', async ({ request }) => {
    bodies.push((await request.json()) as SubmitItemIn);
    log.push('create');
    return HttpResponse.json(itemFixture({ id: 1042, key: 'CP-1042', status: 'submitted' }), { status: 201 });
  });
}

async function choose(user: ReturnType<typeof userEvent.setup>, label: RegExp, option: string) {
  await user.click(screen.getByRole('button', { name: label }));
  await user.click(await screen.findByRole('option', { name: option }));
}

async function fillValid(user: ReturnType<typeof userEvent.setup>, copy = CLEAN_COPY) {
  await user.type(screen.getByLabelText('Title'), 'Fall personal loan promo');
  await choose(user, /Product/, 'Personal loan');
  await choose(user, /Channel/, 'Paid social');
  fireEvent.change(screen.getByLabelText('First run'), { target: { value: '2026-11-01' } });
  await user.click(screen.getByLabelText('Copy'));
  await user.paste(copy);
}

async function renderSubmit() {
  const rendered = renderAtRoute(SubmitPage, { path: '/submit' });
  await screen.findByRole('heading', { name: 'New submission' });
  return rendered;
}

beforeEach(() => {
  vi.mocked(showToast).mockClear();
  vi.mocked(uploadItemAttachment).mockReset();
});

describe('SubmitPage', () => {
  it('shows required-field errors on the fields and sends nothing', async () => {
    const log: string[] = [];
    server.use(recordSubmits(log));
    const user = userEvent.setup();
    await renderSubmit();

    await user.click(await screen.findByRole('button', { name: 'Submit' }));

    expect(await screen.findByText('Enter a title.')).toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Choose a product.')).toBeInTheDocument();
    expect(screen.getByText('Choose a channel.')).toBeInTheDocument();
    expect(screen.getByText('Enter the first run date.')).toBeInTheDocument();
    expect(screen.getByText('Paste or type the copy.')).toBeInTheDocument();
    expect(log).toEqual([]);

    // Errors clear as the field is fixed (revalidate on change after the first submit).
    await user.type(screen.getByLabelText('Title'), 'Promo');
    expect(screen.queryByText('Enter a title.')).toBeNull();
  });

  it('requires a partner for an affiliate page, on the partner field', async () => {
    server.use(getListPartnersMockHandler(PARTNERS), previewHandler());
    const user = userEvent.setup();
    await renderSubmit();

    await fillValid(user);
    expect(screen.queryByRole('button', { name: /Partner/ })).toBeNull();
    await choose(user, /Channel/, 'Affiliate page');
    await user.click(screen.getByRole('button', { name: 'Submit' }));

    expect(await screen.findByText('Choose the partner that runs this page.')).toBeInTheDocument();
    await choose(user, /Partner/, 'LendCompare');
    expect(screen.queryByText('Choose the partner that runs this page.')).toBeNull();
  });

  it('runs live checks as the marketer types and marks the flagged words', async () => {
    const requests: CheckPreviewIn[] = [];
    server.use(previewHandler(requests));
    const user = userEvent.setup();
    const { container } = await renderSubmit();

    const panel = screen.getByRole('region', { name: 'Code checks' });
    expect(within(panel).getByText('Checks run as you type.')).toBeInTheDocument();

    await fillValid(user, COPY);

    expect(await within(panel).findByText('Rate claim needs the full APR range')).toBeInTheDocument();
    // The emoji before the span is two UTF-16 units but one code point: the mark still lands on the quote.
    await waitFor(() => {
      expect(container.querySelector('.app-copy-backdrop mark')?.textContent).toBe('as low as');
    });
    expect(requests.at(-1)).toMatchObject({
      content_text: COPY,
      product: 'personal_loan',
      channel: 'paid_social',
      markets: ['national'],
    });
  });

  it('says when live checks are unavailable or missing context, and keeps the form usable', async () => {
    server.use(
      http.post('*/api/checks/preview', () =>
        HttpResponse.json({ code: 'internal', message: 'Boom.' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    await renderSubmit();
    const panel = screen.getByRole('region', { name: 'Code checks' });

    await user.click(screen.getByLabelText('Copy'));
    await user.paste(COPY);
    expect(
      within(panel).getByText('Choose a product, channel, and market to run checks.'),
    ).toBeInTheDocument();

    await choose(user, /Product/, 'Personal loan');
    await choose(user, /Channel/, 'Paid social');
    expect(
      await within(panel).findByText('Live checks unavailable. They run again when you submit.'),
    ).toBeInTheDocument();
    expect(within(panel).getByText('AI review runs after you submit.')).toBeInTheDocument();
  });

  it('shows the open-finding count before sending, then submits on confirm', async () => {
    const log: string[] = [];
    server.use(previewHandler(), recordSubmits(log));
    const user = userEvent.setup();
    const { router } = await renderSubmit();

    await fillValid(user, COPY);
    await screen.findByText('Rate claim needs the full APR range');
    await user.click(screen.getByRole('button', { name: 'Submit' }));

    expect(
      await screen.findByText('1 open finding (1 blocking). Reviewers will see them.'),
    ).toBeInTheDocument();
    expect(log).toEqual([]);

    await user.click(screen.getByRole('button', { name: 'Keep editing' }));
    expect(screen.queryByText(/Reviewers will see them/)).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Submit' }));
    await user.click(await screen.findByRole('button', { name: 'Submit anyway' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1042');
    });
    expect(log).toEqual(['create']);
    expect(showToast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Submitted' }));
  });

  it('puts a 422 on the field it names and clears it on edit', async () => {
    server.use(
      previewHandler(),
      http.post('*/api/items', () =>
        HttpResponse.json(
          {
            code: 'validation_error',
            message: 'Some fields need attention.',
            fields: [
              {
                loc: ['body', 'payload', 'title'],
                message: 'A title with this name already exists.',
                type: 'x',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    await renderSubmit();

    await fillValid(user);
    await screen.findByText('No code findings.');
    await user.click(screen.getByRole('button', { name: 'Submit' }));

    const title = screen.getByLabelText('Title');
    const error = await screen.findByText('A title with this name already exists.');
    expect(title).toHaveAttribute('aria-invalid', 'true');
    expect(title.getAttribute('aria-describedby')).toContain(error.id);
    expect(showToast).not.toHaveBeenCalled();

    await user.type(title, ' v2');
    expect(screen.queryByText('A title with this name already exists.')).toBeNull();
  });

  it('shows a server error it cannot place as one form-level line', async () => {
    server.use(
      previewHandler(),
      http.post('*/api/items', () =>
        HttpResponse.json({ code: 'internal', message: 'The server had a problem.' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    await renderSubmit();

    await fillValid(user);
    await screen.findByText('No code findings.');
    await user.click(screen.getByRole('button', { name: 'Submit' }));

    expect(await screen.findByText('The server had a problem.')).toBeInTheDocument();
  });

  it('uploads the mockup and each evidence file after the item exists', async () => {
    const log: string[] = [];
    server.use(previewHandler(), recordSubmits(log));
    vi.mocked(uploadItemAttachment).mockImplementation((itemId, { kind, file }) => {
      const name = (file as File).name;
      log.push(`upload ${String(itemId)} ${kind} ${name}`);
      return name === 'rate-sheet.pdf'
        ? Promise.reject(new ApiError(413, { code: 'too_large', message: 'File too large.' }))
        : Promise.resolve(uploaded(kind, name));
    });
    const user = userEvent.setup();
    const { router, container } = await renderSubmit();

    await fillValid(user);
    const mockupInput = container.querySelector<HTMLInputElement>('input[type=file][accept="image/*"]');
    const evidenceInput = container.querySelector<HTMLInputElement>('input[type=file][multiple]');
    if (mockupInput === null || evidenceInput === null) throw new Error('file inputs missing');
    await user.upload(mockupInput, new File(['png'], 'mock.png', { type: 'image/png' }));
    await user.upload(evidenceInput, [
      new File(['pdf'], 'rate-sheet.pdf', { type: 'application/pdf' }),
      new File(['pdf'], 'study.pdf', { type: 'application/pdf' }),
    ]);
    expect(screen.getByText('mock.png')).toBeInTheDocument();

    // Each evidence file needs a kind before submit.
    await user.click(screen.getByRole('button', { name: 'Submit' }));
    expect(await screen.findAllByText('Choose what this file is.')).toHaveLength(2);
    await choose(user, /Kind for rate-sheet\.pdf/, 'Rate sheet');
    await choose(user, /Kind for study\.pdf/, 'Substantiation');
    await user.click(screen.getByRole('button', { name: 'Submit' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/items/1042');
    });
    expect(log[0]).toBe('create');
    expect([...log.slice(1)].sort()).toEqual([
      'upload 1042 creative mock.png',
      'upload 1042 rate_sheet rate-sheet.pdf',
      'upload 1042 substantiation study.pdf',
    ]);
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ title: "rate-sheet.pdf didn't upload", tone: 'error' }),
    );
  });

  it('shows why a URL could not be fetched, and leaves the copy editable', async () => {
    server.use(
      http.post('*/api/items/fetch-url', () =>
        HttpResponse.json(
          {
            code: 'invalid_input',
            message: "That address points to a private or internal network, so it can't be fetched.",
            details: { reason: 'address_not_allowed' },
            fields: [{ loc: ['body', 'url'], message: 'x', type: 'invalid' }],
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    await renderSubmit();

    await user.type(screen.getByLabelText('Fetch from a URL'), 'http://169.254.169.254/latest');
    await user.click(screen.getByRole('button', { name: 'Fetch' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "That address points to a private or internal network, so it can't be fetched.",
    );
    expect(screen.getByLabelText('Copy')).toBeEnabled();
  });

  it('asks for a full address before fetching', async () => {
    const user = userEvent.setup();
    await renderSubmit();

    await user.type(screen.getByLabelText('Fetch from a URL'), 'lendcompare.example{Enter}');

    expect(await screen.findByText('Enter the full address, starting with https://')).toBeInTheDocument();
  });

  it('shows that a fetch is in progress', async () => {
    let release: () => void = () => undefined;
    server.use(
      http.post('*/api/items/fetch-url', async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json({ url: 'https://lendcompare.example/pl', title: null, content_text: COPY });
      }),
    );
    const user = userEvent.setup();
    await renderSubmit();

    await user.type(screen.getByLabelText('Fetch from a URL'), 'https://lendcompare.example/pl');
    await user.click(screen.getByRole('button', { name: 'Fetch' }));

    expect(await screen.findByRole('button', { name: /Fetching/ })).toBeInTheDocument();
    release();
    expect(await screen.findByText(/Copy filled from lendcompare\.example/)).toBeInTheDocument();
  });

  it('fills the copy from a fetched page', async () => {
    server.use(
      previewHandler(),
      http.post('*/api/items/fetch-url', () =>
        HttpResponse.json({ url: 'https://lendcompare.example/pl', title: 'PL offer', content_text: COPY }),
      ),
    );
    const user = userEvent.setup();
    await renderSubmit();

    await user.type(screen.getByLabelText('Fetch from a URL'), 'https://lendcompare.example/pl');
    await user.click(screen.getByRole('button', { name: 'Fetch' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Copy')).toHaveValue(COPY);
    });
    expect(screen.getByLabelText('Title')).toHaveValue('PL offer');
    expect(screen.getByText(/Copy filled from lendcompare\.example/)).toHaveAttribute('role', 'status');
  });
});
