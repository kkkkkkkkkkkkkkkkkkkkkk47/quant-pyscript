export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatScore(score: number): string {
  return score.toFixed(2);
}

export function formatPct(pct: number): string {
  // pct is already a percentage value (e.g. 20.0 means 20%), just add the % sign
  return `${Math.round(pct)}%`;
}

export const RATING_COLORS: Record<
  string,
  { bg: string; text: string; hex: string; border: string }
> = {
  'Strong Buy': {
    bg: 'bg-emerald-500',
    text: 'text-emerald-500',
    hex: '#10b981',
    border: 'border-emerald-500',
  },
  Buy: {
    bg: 'bg-emerald-400',
    text: 'text-emerald-400',
    hex: '#34d399',
    border: 'border-emerald-400',
  },
  Neutral: {
    bg: 'bg-gray-500',
    text: 'text-gray-400',
    hex: '#6b7280',
    border: 'border-gray-500',
  },
  Sell: {
    bg: 'bg-red-400',
    text: 'text-red-400',
    hex: '#f87171',
    border: 'border-red-400',
  },
  'Strong Sell': {
    bg: 'bg-red-500',
    text: 'text-red-500',
    hex: '#ef4444',
    border: 'border-red-500',
  },
};
