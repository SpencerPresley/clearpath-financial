/*
 * /dev/design: every token family and component in every state, for review and screenshots.
 * Not in the nav. Ages use a fixed clock so screenshots are stable.
 */
import type { ReactNode } from 'react';
import { useId } from 'react';

import { contrastRatio } from '../../theme/contrast';
import { RiskTierBadge, SeverityBadge, SourceTag, StatusBadge } from '../badges';
import type { Tone } from '../badges';
import { Button } from '../Button';
import { FINDING_SOURCES, ITEM_STATUSES, RISK_TIERS, SEVERITIES } from '../domain';
import type { ItemStatus } from '../domain';
import { EmptyState } from '../EmptyState';
import { Icon } from '../Icon';
import { IconButton } from '../IconButton';
import { icons } from '../icons';
import type { IconKey } from '../icons';
import { ItemKey } from '../ItemKey';
import { Kbd } from '../Kbd';
import { RelativeAge } from '../RelativeAge';
import { SkeletonBadge, SkeletonTable, SkeletonText } from '../Skeleton';
import { showToast } from '../toast';
import { Tooltip } from '../Tooltip';

const RADIUS_PX = { xs: '2px', sm: '3px', md: '4px', lg: '6px' } as const;

const NOW = new Date('2026-10-24T15:00:00Z');
const hoursAgo = (hours: number) => new Date(NOW.getTime() - hours * 3_600_000);

const TONES: { tone: Tone; meaning: string }[] = [
  { tone: 'neutral', meaning: 'Waiting, inactive' },
  { tone: 'info', meaning: 'Someone is working on it' },
  { tone: 'warning', meaning: "Marketer's court; non-blocking" },
  { tone: 'success', meaning: 'Cleared' },
  { tone: 'error', meaning: 'Blocked or refused' },
  { tone: 'alert', meaning: 'Live content at risk' },
];

function readVar(name: string): string {
  if (typeof window === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
}

function ratio(fg: string, bg: string): string {
  try {
    return `${contrastRatio(readVar(fg), readVar(bg)).toFixed(2)}:1`;
  } catch {
    return '—'; // token not resolvable here (e.g. jsdom has no stylesheet)
  }
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="app-gallery-section">
      <h2 id={id} className="app-gallery-heading">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Swatch({ bg, fg, name }: { bg: string; fg: string; name: string }) {
  return (
    <div className="app-swatch" style={{ background: `var(--color-${bg})`, color: `var(--color-${fg})` }}>
      <span className="font-medium">{name}</span>
      <span className="font-mono tabular-nums">
        {fg} · {ratio(fg, bg)}
      </span>
    </div>
  );
}

const SAMPLE_ROWS: { key: string; title: string; status: ItemStatus; age: number; findings: number }[] = [
  {
    key: 'CP-1042',
    title: 'Personal loan email: "Rates as low as 7.49% APR"',
    status: 'in_review',
    age: 30,
    findings: 3,
  },
  {
    key: 'CP-1038',
    title: 'Card landing page, balance transfer offer',
    status: 'changes_requested',
    age: 75,
    findings: 2,
  },
  {
    key: 'CP-0987',
    title: 'Affiliate page, LendWise comparison table',
    status: 'needs_rereview',
    age: 4,
    findings: 1,
  },
  { key: 'CP-1051', title: 'Paid search ad group, prequal', status: 'submitted', age: 2, findings: 0 },
  {
    key: 'CP-0954',
    title: 'Direct mail, personal loan refinance',
    status: 'approved',
    age: 400,
    findings: 0,
  },
];

export function DesignGallery() {
  const iconGroups = Object.keys(icons).reduce<Record<string, IconKey[]>>((groups, key) => {
    const prefix = key.split('.')[0] ?? key;
    (groups[prefix] ??= []).push(key as IconKey);
    return groups;
  }, {});

  return (
    <div className="app-gallery">
      <header>
        <h1 className="app-page-title">Design system</h1>
        <p className="app-muted">
          Tokens and components from src/theme/theme.css and src/ui. Internal reference; not in navigation.
        </p>
      </header>

      <Section title="Status tones">
        <div className="app-gallery-grid">
          {TONES.map(({ tone, meaning }) => (
            <div key={tone} className="flex flex-col gap-1">
              <Swatch bg={`status-${tone}`} fg={`status-${tone}-content`} name={`${tone} · ${meaning}`} />
              <Swatch bg={`status-${tone}-soft`} fg={`status-${tone}-soft-content`} name={`${tone} soft`} />
            </div>
          ))}
        </div>
        <p className="app-gallery-label">
          The three warm status colors side by side (no warm brand color competes with them):
        </p>
        <div className="app-gallery-row">
          <Swatch bg="status-warning" fg="status-warning-content" name="Warning" />
          <Swatch bg="status-alert" fg="status-alert-content" name="Alert" />
          <Swatch bg="status-error" fg="status-error-content" name="Error" />
        </div>
      </Section>

      <Section title="Brand and surfaces">
        <div className="app-gallery-grid">
          <Swatch bg="primary" fg="primary-content" name="Primary (navy)" />
          <Swatch bg="primary" fg="brand-muted" name="Chrome secondary text" />
          <Swatch bg="nav-active" fg="primary" name="Selected nav row" />
          <Swatch bg="base-100" fg="base-content" name="Base 100 · content" />
          <Swatch bg="base-200" fg="base-content" name="Base 200 · canvas" />
          <Swatch bg="base-200" fg="muted" name="Muted text" />
          <Swatch bg="base-300" fg="base-content" name="Base 300 · rules" />
          <Swatch bg="neutral" fg="neutral-content" name="Inverse surface · tooltip, toast" />
          <Swatch bg="base-100" fg="focus" name="Focus ring" />
        </div>
      </Section>

      <Section title="Type">
        <div className="app-gallery-panel flex flex-col gap-2 p-4">
          <p className="text-lg font-semibold">Page title · 18 semibold</p>
          <p className="text-sm">Reading copy · 14 regular. Rate claim may need the full APR range.</p>
          <p className="text-ui">UI default · 13 regular. Tables, controls, and chrome.</p>
          <p className="text-meta text-muted">Meta · 12. Badges, timestamps, labels.</p>
          <div className="flex gap-8">
            <ItemKey value="CP-1042" copyable={false} />
            <span className="font-mono text-meta">Reg Z 1026.24(a)</span>
          </div>
          <div className="flex gap-6 text-ui">
            <div className="flex flex-col items-end tabular-nums">
              <span>7.49%</span>
              <span>11.25%</span>
              <span>35.99%</span>
            </div>
            <div className="flex flex-col items-end tabular-nums">
              <span>$1,000</span>
              <span>$15,500</span>
              <span>$50,000</span>
            </div>
            <span className="app-gallery-label self-center">Tabular figures align in columns.</span>
          </div>
        </div>
      </Section>

      <Section title="Radius, shadow, spacing">
        <div className="app-gallery-row">
          {(['xs', 'sm', 'md', 'lg'] as const).map((size) => (
            <div
              key={size}
              className="app-gallery-panel flex size-16 items-end p-1.5 text-meta"
              style={{ borderRadius: `var(--radius-${size})` }}
            >
              {size} · {RADIUS_PX[size]}
            </div>
          ))}
          <div className="flex h-16 w-40 items-end rounded-lg bg-base-100 p-1.5 text-meta shadow-overlay">
            shadow-overlay (overlays only)
          </div>
          <div className="app-gallery-label">
            Topbar 48px · nav 216px / 52px collapsed · row 36px · button 32px / 28px small
          </div>
        </div>
      </Section>

      <Section title="Icons">
        {Object.entries(iconGroups).map(([prefix, keys]) => (
          <div key={prefix} className="flex flex-col gap-1">
            <span className="app-gallery-label">{prefix}</span>
            <div className="app-gallery-grid">
              {keys.map((key) => (
                <div key={key} className="flex items-center gap-2 text-meta">
                  <Icon name={key} size={18} />
                  <span className="font-mono">{key}</span>
                  <span className="text-muted">{icons[key].weight}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Section>

      <Section title="Status">
        <div className="app-gallery-row">
          {ITEM_STATUSES.map((status) => (
            <StatusBadge key={status} status={status} />
          ))}
        </div>
        <div className="app-gallery-row">
          {SEVERITIES.map((severity) => (
            <SeverityBadge key={severity} severity={severity} />
          ))}
          <span className="w-4" />
          {FINDING_SOURCES.map((source) => (
            <SourceTag key={source} source={source} />
          ))}
          <span className="w-4" />
          {RISK_TIERS.map((tier) => (
            <RiskTierBadge key={tier} tier={tier} />
          ))}
        </div>
        <p className="app-gallery-label">In a dense row (36px), on the content surface:</p>
        <div className="app-gallery-panel overflow-hidden">
          {SAMPLE_ROWS.map((row) => (
            <div
              key={row.key}
              className="grid h-row grid-cols-[6rem_minmax(0,1fr)_10rem_5rem_4rem] items-center gap-3 border-b border-base-300 px-3 last:border-b-0"
            >
              <ItemKey value={row.key} />
              <span className="truncate">{row.title}</span>
              <span>
                <StatusBadge status={row.status} />
              </span>
              <span className="flex items-center gap-1 text-muted tabular-nums">
                <Icon name="entity.finding" size={14} />
                {row.findings}
              </span>
              <RelativeAge at={hoursAgo(row.age)} now={NOW} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Buttons">
        {(['primary', 'secondary', 'ghost', 'danger'] as const).map((variant) => (
          <div key={variant} className="app-gallery-row">
            <span className="app-gallery-label w-20">{variant}</span>
            <Button variant={variant}>
              {variant === 'danger' ? 'Reject' : variant === 'primary' ? 'Approve' : 'Request changes'}
            </Button>
            <Button variant={variant} icon={variant === 'danger' ? 'action.reject' : 'action.approve'}>
              With icon
            </Button>
            <Button variant={variant} size="sm">
              Small
            </Button>
            <Button variant={variant} isDisabled>
              Disabled
            </Button>
            {variant === 'danger' ? (
              <IconButton icon="action.reject" aria-label="Reject" variant="danger" />
            ) : (
              <>
                <IconButton icon="action.more" aria-label="More actions" variant={variant} />
                <IconButton icon="action.filter" aria-label="Filter" variant={variant} size="sm" />
              </>
            )}
          </div>
        ))}
      </Section>

      <Section title="Item key, age, tooltip, keyboard">
        <div className="app-gallery-row gap-6">
          <ItemKey value="CP-1042" />
          <span className="flex gap-3">
            <RelativeAge at={hoursAgo(0.2)} now={NOW} />
            <RelativeAge at={hoursAgo(5)} now={NOW} />
            <RelativeAge at={hoursAgo(72)} now={NOW} />
            <RelativeAge at={hoursAgo(24 * 20)} now={NOW} />
            <RelativeAge at={hoursAgo(24 * 120)} now={NOW} />
            <RelativeAge at="not a date" now={NOW} />
          </span>
          <Tooltip
            content={
              <span className="flex items-center gap-1.5">
                Shortcut <Kbd keys={['C']} />
              </span>
            }
          >
            <Button size="sm" icon="action.assign">
              Claim
            </Button>
          </Tooltip>
          <span className="flex items-center gap-2 text-muted">
            Approve <Kbd keys={['A']} /> · Next item <Kbd keys={['J']} /> · Search <Kbd keys={['⌘', 'K']} />
          </span>
        </div>
      </Section>

      <Section title="Toasts">
        <div className="app-gallery-row">
          <Button
            onPress={() => {
              showToast({ title: 'Claimed', description: <ItemKey value="CP-1042" copyable={false} /> });
            }}
          >
            Show confirmation
          </Button>
          <Button
            onPress={() => {
              showToast({
                title: 'Decision not saved. Try again in a minute.',
                tone: 'error',
              });
            }}
          >
            Show error
          </Button>
        </div>
      </Section>

      <Section title="Empty and loading">
        <div className="grid grid-cols-2 gap-3">
          <div className="app-gallery-panel">
            <EmptyState
              icon="nav.queue"
              title="Nothing assigned to you"
              action={
                <Button size="sm" variant="primary">
                  Show unassigned
                </Button>
              }
            >
              4 unassigned items are waiting.
            </EmptyState>
          </div>
          <div className="app-gallery-panel">
            <EmptyState icon="entity.finding" title="No findings on v2">
              Code checks ran on this version and flagged nothing.
            </EmptyState>
          </div>
        </div>
        <div className="app-gallery-panel overflow-hidden">
          <div className="flex items-center gap-3 px-3 py-2">
            <SkeletonText width="10rem" />
            <SkeletonBadge />
          </div>
          <SkeletonTable
            rows={5}
            columns={['6rem', 'minmax(0,1fr)', '10rem', '5rem', '4rem']}
            label="Loading queue"
          />
        </div>
      </Section>
    </div>
  );
}
