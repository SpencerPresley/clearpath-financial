import { SeverityBadge, SourceTag } from '../badges';
import type { FindingSource, Severity } from '../domain';

export interface FindingSummaryProps {
  severity: Severity;
  source: FindingSource;
  message: string;
  citation: string;
  quote?: string | null;
  suggestedFix?: string;
  /** id for the message line, so copy marks can point at it with aria-describedby. */
  id?: string;
  /** Triaged: the severity pill drops its alarm color (red/amber means "still open"). */
  quiet?: boolean;
}

/**
 * What a finding says: severity, where it came from, the message with its citation, the quoted text, and
 * the suggested fix. AI output reads as a suggestion with a citation (spec §5.4); the source tag says
 * "AI suggestion" and nothing here says "violation".
 */
export function FindingSummary({
  severity,
  source,
  message,
  citation,
  quote,
  suggestedFix,
  id,
  quiet = false,
}: FindingSummaryProps) {
  return (
    <div className="app-finding-summary" data-quiet={quiet ? 'true' : undefined}>
      <div className="app-finding-tags">
        <SeverityBadge severity={severity} />
        <SourceTag source={source} />
      </div>
      <p id={id} className="app-finding-message">
        {message}
        {citation !== '' && <span className="app-finding-citation"> · {citation}</span>}
      </p>
      {quote != null && quote !== '' && <q className="app-finding-quote">{quote}</q>}
      {suggestedFix !== undefined && suggestedFix !== '' && (
        <p className="app-finding-fix">
          <span className="app-finding-fix-label">Suggested:</span> {suggestedFix}
        </p>
      )}
    </div>
  );
}
