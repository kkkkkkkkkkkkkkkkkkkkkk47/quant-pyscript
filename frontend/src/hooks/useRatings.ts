import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchAllLatest, fetchAssetClass } from '../api/client';
import type { AssetClass, RatingRecord } from '../types';

export function useRatings(activeClass: AssetClass | 'All', autoRefresh: boolean) {
  const [records, setRecords] = useState<RatingRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data =
        activeClass === 'All'
          ? await fetchAllLatest()
          : await fetchAssetClass(activeClass);
      setRecords(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [activeClass]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (autoRefresh) {
      intervalRef.current = setInterval(() => void load(), 30_000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, load]);

  return { records, loading, error, refetch: load };
}
