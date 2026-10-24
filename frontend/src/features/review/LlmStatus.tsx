import { useQueryClient } from '@tanstack/react-query';

import { useRetryLlmCheck } from '../../api/generated/findings/findings';
import { getGetItemQueryKey } from '../../api/generated/items/items';
import type { ItemDetailOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';
import { Icon } from '../../ui/Icon';
import { plural } from '../../ui/labels';
import { showToast } from '../../ui/toast';

/**
 * The AI pre-review's state, at the top of the Findings tab (spec §6.1: a failed external call is visible
 * state with a Retry, never a silent gap). It only ever gates the human's Approve; nothing here passes
 * an item (spec §7).
 */
export function LlmStatus({
  item,
  aiCount,
  canRetry,
}: {
  item: ItemDetailOut;
  aiCount: number;
  canRetry: boolean;
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

  switch (item.llm_check_status) {
    case 'pending':
    case 'running':
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
      // No API key on this server: Retry would fail the same way, so it isn't offered.
      const notConfigured = item.llm_check_failure_code === 'not_configured';
      const reason = item.llm_check_failure_reason;
      return (
        <div className="app-llm-status" data-state="failed" role="alert">
          <Icon name="feedback.error" />
          <span>
            {notConfigured
              ? 'AI review isn’t configured on this server.'
              : reason === null
                ? 'AI check failed.'
                : `AI check failed: ${reason}`}
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
      const carried = item.latest_decision?.version_n;
      return (
        <div className="app-llm-status" data-state="skipped">
          <Icon name="source.ai" />
          <span>
            {carried === undefined
              ? 'AI check skipped for this version'
              : `AI review carried from v${String(carried)}`}
            <span className="app-llm-status-note">
              {item.numbers_change === false
                ? ' · offer terms changed, numbers unchanged'
                : ' · only offer-terms numbers changed'}
            </span>
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
