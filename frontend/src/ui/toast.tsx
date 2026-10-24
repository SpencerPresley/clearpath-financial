/*
 * Toasts: one app-wide queue and one host (mounted in the root route).
 *
 * React Aria's toast API is still UNSTABLE_-prefixed in react-aria-components 1.22; this file is the only
 * importer, so a rename or API change lands here and nowhere else.
 *
 * Use toasts for confirmation of something the user just did elsewhere on screen, or a failure they
 * need to see. Not for validation (that belongs inline) and not for celebration (spec §5.4).
 */
import {
  Button as AriaButton,
  Text,
  UNSTABLE_Toast as AriaToast,
  UNSTABLE_ToastContent as AriaToastContent,
  UNSTABLE_ToastQueue as AriaToastQueue,
  UNSTABLE_ToastRegion as AriaToastRegion,
} from 'react-aria-components';

import { Icon } from './Icon';

export interface ToastContent {
  title: string;
  description?: string;
  /** neutral: confirmation. error: something failed; say what happened and what to do (§5.4). */
  tone?: 'neutral' | 'error';
}

export const toastQueue = new AriaToastQueue<ToastContent>({ maxVisibleToasts: 3 });

const DEFAULT_TIMEOUT_MS = 5000;

/** Errors stay until dismissed; confirmations time out. Returns the toast key. */
export function showToast(content: ToastContent, timeout?: number): string {
  const ms = timeout ?? (content.tone === 'error' ? undefined : DEFAULT_TIMEOUT_MS);
  return toastQueue.add(content, ms === undefined ? {} : { timeout: ms });
}

export function ToastHost() {
  return (
    <AriaToastRegion queue={toastQueue} className="app-toast-region" aria-label="Notifications">
      {({ toast }) => (
        <AriaToast toast={toast} className="app-toast" data-tone={toast.content.tone ?? 'neutral'}>
          <Icon
            name={toast.content.tone === 'error' ? 'feedback.error' : 'feedback.info'}
            className="mt-0.5"
          />
          <AriaToastContent className="app-toast-body">
            <Text slot="title" className="app-toast-title">
              {toast.content.title}
            </Text>
            {toast.content.description !== undefined && (
              <Text slot="description">{toast.content.description}</Text>
            )}
          </AriaToastContent>
          <AriaButton slot="close" className="app-toast-close" aria-label="Dismiss">
            <Icon name="action.close" size={14} />
          </AriaButton>
        </AriaToast>
      )}
    </AriaToastRegion>
  );
}
