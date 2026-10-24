import { useId, useState } from 'react';
import { Input, Label, TextField } from 'react-aria-components';

import { useFetchCopyFromUrl } from '../../api/generated/items/items';
import { FetchCopyFromUrlBody } from '../../api/generated/items/items.zod';
import type { FetchedCopyOut } from '../../api/generated/model';
import { Button } from '../../ui/Button';
import { apiErrorMessage } from '../../ui/forms/apiErrors';

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * "Fetch from a URL" beside the copy editor. A field of its own (not part of the submission form), so Enter
 * here fetches instead of submitting the item. The server reads static HTML only; a refusal (private address,
 * not a web page, no readable text) comes back as a plain sentence and is shown as is.
 */
export function FetchFromUrl({ onFetched }: { onFetched: (copy: FetchedCopyOut) => void }) {
  const [url, setUrl] = useState('');
  const [invalid, setInvalid] = useState<string | null>(null);
  const [filledFrom, setFilledFrom] = useState<string | null>(null);
  const messageId = useId();
  const fetchCopy = useFetchCopyFromUrl({
    mutation: {
      onSuccess: (copy) => {
        setFilledFrom(hostOf(copy.url));
        onFetched(copy);
      },
    },
  });

  const run = () => {
    const parsed = FetchCopyFromUrlBody.safeParse({ url: url.trim() });
    if (!parsed.success) {
      setInvalid('Enter the full address, starting with https://');
      return;
    }
    setInvalid(null);
    setFilledFrom(null);
    fetchCopy.mutate({ data: parsed.data });
  };

  const error = invalid ?? (fetchCopy.isError ? apiErrorMessage(fetchCopy.error) : null);
  const message =
    error ??
    (filledFrom === null
      ? null
      : `Copy filled from ${filledFrom}. Check it before you submit: page text around the ad may have come along.`);

  return (
    <div className="app-fetch-url">
      <TextField
        value={url}
        onChange={(next) => {
          setUrl(next);
          setInvalid(null);
          setFilledFrom(null);
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
        isInvalid={error !== null}
        aria-describedby={message === null ? undefined : messageId}
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
        <p
          id={messageId}
          className={error === null ? 'app-field-description' : 'app-field-error'}
          role={error === null ? 'status' : 'alert'}
        >
          {message}
        </p>
      )}
    </div>
  );
}
