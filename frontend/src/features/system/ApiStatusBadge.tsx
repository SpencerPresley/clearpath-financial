import { useHealth } from '../../api/generated';

export function ApiStatusBadge() {
  const { data, isPending, isError } = useHealth({ query: { retry: false } });

  if (isPending) {
    return <span className="badge badge-ghost badge-sm">API: checking…</span>;
  }
  if (isError || data.status !== 'ok') {
    return <span className="badge badge-error badge-sm">API: unavailable</span>;
  }
  return <span className="badge badge-success badge-sm">API: online</span>;
}
