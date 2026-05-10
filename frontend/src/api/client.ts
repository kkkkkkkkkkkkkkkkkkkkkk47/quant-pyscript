import type { HealthStatus, RatingRecord } from '../types';

// When served via Vite dev server, use /api (proxied to localhost:8000).
// When served directly from FastAPI (production/tunnel), use empty base.
const BASE = import.meta.env.DEV ? '/api' : '';

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchAssetClass(ac: string): Promise<RatingRecord[]> {
  return request<RatingRecord[]>(`/ratings/asset-class/${encodeURIComponent(ac)}/latest`);
}

export async function fetchAllLatest(): Promise<RatingRecord[]> {
  // Fetch all known asset classes in parallel and merge
  const classes = ['FX', 'Equity', 'Index', 'Commodity', 'Crypto'];
  const results = await Promise.allSettled(classes.map((c) => fetchAssetClass(c)));
  const records: RatingRecord[] = [];
  for (const r of results) {
    if (r.status === 'fulfilled') {
      records.push(...r.value);
    }
  }
  return records;
}

export async function fetchLatest(securityId: string): Promise<RatingRecord> {
  return request<RatingRecord>(`/ratings/${encodeURIComponent(securityId)}/latest`);
}

export async function fetchHistory(
  securityId: string,
  days = 7,
): Promise<RatingRecord[]> {
  const to = new Date();
  const from = new Date(Date.now() - days * 86_400_000);
  const params = new URLSearchParams({
    from_dt: from.toISOString(),
    to_dt: to.toISOString(),
  });
  return request<RatingRecord[]>(
    `/ratings/${encodeURIComponent(securityId)}/history?${params.toString()}`,
  );
}

export async function fetchHealth(): Promise<HealthStatus> {
  return request<HealthStatus>('/health');
}

export async function fetchPrice(securityId: string): Promise<number | null> {
  try {
    const data = await request<{ security_id: string; price: number | null; source: string }>(
      `/price/${encodeURIComponent(securityId)}`,
    );
    return data.price;
  } catch {
    return null;
  }
}
