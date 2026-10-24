import { SeverityBadge, SourceTag } from '../badges';
import { Button } from '../Button';
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
  /** Present when the suggestion is literal text for the flagged span: Apply puts it in the editor. */
  onApply?: () => void;
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
  onApply,
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
        <div className="app-finding-fix-row">
          <p className="app-finding-fix">
            <span className="app-finding-fix-label">Suggested:</span> {suggestedFix}
          </p>
          {onApply !== undefined && (
            <Button
              size="sm"
              className="app-finding-apply"
              aria-label={`Apply suggestion: ${suggestedFix}`}
              onPress={onApply}
            >
              Apply
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
