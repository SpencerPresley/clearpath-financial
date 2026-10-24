import { useQueryClient } from '@tanstack/react-query';

import { useRetryLlmCheck } from '../../api/generated/findings/findings';
import { getGetItemQueryKey } from '../../api/generated/items/items';
import type { ItemDetailOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import { LLM_FAILURE_LABELS, plural } from '../../ui/labels';
import { showToast } from '../../ui/toast';

/**
 * Which version's AI review a skipped (fast-track) version relies on: the version it was generated from, which
 * is what the decision records as `ai_review_carried_from` (reviews/decisions.py `_write`). Once that decision
 * exists, its record is the source. Null when nothing was carried.
 */
export function aiCarriedFromN(item: ItemDetailOut): number | null {
  const decision = item.latest_decision;
  if (decision !== null && decision.version_n === item.current_version_n) {
    return decision.ai_review_carried_from_n;
  }
  return item.current_version?.origin === 'submission' ? null : (item.current_version?.based_on_n ?? null);
}

/**
 * The AI pre-review's state, at the top of the Findings tab (spec §6.1: a failed external call is visible
 * state with a Retry, never a silent gap). It only ever gates the human's Approve; nothing here passes
 * an item (spec §7).
 *
 * Reviewers and leads get the copy about approving. Everyone else (the marketer, an admin) gets neutral copy
 * with nothing to act on: they can't approve or retry, and red means blocked or refused (spec §5.2).
 */
export function LlmStatus({
  item,
  aiCount,
  canRetry,
  isDecider,
  isMarketer = false,
}: {
  item: ItemDetailOut;
  aiCount: number;
  canRetry: boolean;
  isDecider: boolean;
  /** "your reviewer" rather than "the reviewer". */
  isMarketer?: boolean;
}) {
  const queryClient = useQueryClient();
  const retry = useRetryLlmCheck({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getGetItemQueryKey(item.id) });
      },
      onError: (error) => {
        showToast({ title: 'AI check not restarted', description: apiErrorMessage(error), tone: 'error' });
      },
    },
  });

  const reviewer = isMarketer ? 'your reviewer' : 'the reviewer';
  switch (item.llm_check_status) {
    case 'pending':
    case 'running':
      if (!isDecider) {
        return (
          <div className="app-llm-status" data-state="running" role="status">
            <Icon name="source.ai" />
            <span>
              {item.llm_check_status === 'pending' ? 'AI pre-review queued.' : 'AI pre-review running…'}
              <span className="app-llm-status-note"> Its suggestions go to {reviewer}.</span>
            </span>
            <span className="app-llm-progress" aria-hidden="true" />
          </div>
        );
      }
      return (
        <div className="app-llm-status" data-state="running" role="status">
          <Icon name="source.ai" />
          <span>
            {item.llm_check_status === 'pending' ? 'AI check queued.' : 'AI check running…'}
            <span className="app-llm-status-note"> Approving waits for it.</span>
          </span>
          <span className="app-llm-progress" aria-hidden="true" />
        </div>
      );
    case 'failed': {
      if (!isDecider) {
        return (
          <div className="app-llm-status" data-state="neutral" role="status">
            <Icon name="source.ai" />
            <span>AI pre-review didn’t run; {reviewer} will check this by hand.</span>
          </div>
        );
      }
      // No API key on this server: Retry would fail the same way, so it isn't offered.
      const code = item.llm_check_failure_code;
      const notConfigured = code === 'not_configured';
      return (
        <div className="app-llm-status" data-state="failed" role="alert">
          <Icon name="feedback.error" />
          <span>
            {notConfigured
              ? LLM_FAILURE_LABELS.not_configured
              : code === null
                ? 'AI check failed.'
                : `AI check failed: ${LLM_FAILURE_LABELS[code]}`}
            <span className="app-llm-status-note">
              {notConfigured
                ? ' Give an override reason when you approve.'
                : ' Retry, or give an override reason when you approve.'}
            </span>
          </span>
          {canRetry && !notConfigured && (
            <Button
              size="sm"
              className="ml-auto"
              isDisabled={retry.isPending}
              onPress={() => {
                retry.mutate({ itemId: item.id });
              }}
            >
              {retry.isPending ? 'Retrying…' : 'Retry'}
            </Button>
          )}
        </div>
      );
    }
    case 'skipped': {
      const carried = aiCarriedFromN(item);
      const fastTrack = item.current_version?.origin === 'fast_track';
      return (
        <div className="app-llm-status" data-state="skipped">
          <Icon name="source.ai" />
          <span>
            {carried === null
              ? 'AI check skipped for this version'
              : `AI review carried from v${String(carried)}`}
            {fastTrack && (
              <span className="app-llm-status-note">
                {item.numbers_change === false
                  ? ' · offer terms changed, numbers unchanged'
                  : ' · only offer-terms numbers changed'}
              </span>
            )}
          </span>
        </div>
      );
    }
    case 'succeeded':
      return (
        <div className="app-llm-status" data-state="succeeded">
          <Icon name="source.ai" />
          <span>AI check finished · {aiCount === 0 ? 'no suggestions' : plural(aiCount, 'suggestion')}</span>
        </div>
      );
  }
}
