import { useId, useState } from 'react';
import { Input, Label, TextField } from 'react-aria-components';

import { useFetchCopyFromUrl } from '../../api/generated/items/items';
import { FetchCopyFromUrlBody } from '../../api/generated/items/items.zod';
import type { FetchedCopyOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { apiErrorBody, apiErrorMessage } from '../../ui/forms/apiErrors';

function fetchErrorText(error: unknown): string {
  // The endpoint is a contract stub until the page fetcher ships; say so and point at the other path.
  return apiErrorBody(error)?.code === 'not_implemented'
    ? "Fetching from a URL isn't available yet. Paste the copy instead."
    : apiErrorMessage(error);
}

/**
 * "Fetch from a URL" beside the copy editor. A field of its own (not part of the submission form), so Enter
 * here fetches instead of submitting the item.
 */
export function FetchFromUrl({ onFetched }: { onFetched: (copy: FetchedCopyOut) => void }) {
  const [url, setUrl] = useState('');
  const [invalid, setInvalid] = useState<string | null>(null);
  const errorId = useId();
  const fetchCopy = useFetchCopyFromUrl({ mutation: { onSuccess: onFetched } });

  const run = () => {
    const parsed = FetchCopyFromUrlBody.safeParse({ url: url.trim() });
    if (!parsed.success) {
      setInvalid('Enter the full address, starting with https://');
      return;
    }
    setInvalid(null);
    fetchCopy.mutate({ data: parsed.data });
  };

  const message = invalid ?? (fetchCopy.isError ? fetchErrorText(fetchCopy.error) : null);

  return (
    <div className="app-fetch-url">
      <TextField
        value={url}
        onChange={(next) => {
          setUrl(next);
          setInvalid(null);
          fetchCopy.reset();
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            run();
          }
        }}
        type="url"
        className="app-fetch-url-field"
        aria-describedby={message === null ? undefined : errorId}
      >
        <Label className="app-field-label">Fetch from a URL</Label>
        <div className="app-fetch-url-row">
          <Input className="app-input" placeholder="https://" />
          <Button onPress={run} isPending={fetchCopy.isPending}>
            {fetchCopy.isPending ? 'Fetching…' : 'Fetch'}
          </Button>
        </div>
      </TextField>
      {message !== null && (
        <p id={errorId} className="app-field-description" role="status">
          {message}
        </p>
      )}
    </div>
  );
}
