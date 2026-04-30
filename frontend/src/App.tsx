import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AssetClass, RatingRecord } from './types';
import { useRatings } from './hooks/useRatings';
import { useHealth } from './hooks/useHealth';
import { Header } from './components/Header';
import { AssetClassTabs } from './components/AssetClassTabs';
import { RatingCard } from './components/RatingCard';
import { DetailPanel } from './components/DetailPanel';
import { EmptyState } from './components/EmptyState';
import { DashboardCharts } from './components/DashboardCharts';
import { RefreshIcon } from './components/icons';
import { fetchAllLatest } from './api/client';

type Tab = AssetClass | 'All';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('All');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<RatingRecord | null>(null);
  // All records (for tab counts) — fetched once and kept separate from filtered view
  const [allRecords, setAllRecords] = useState<RatingRecord[]>([]);
  const allRecordsRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const data = await fetchAllLatest();
      setAllRecords(data);
    } catch {
      // silently ignore — individual tab fetch will show the error
    }
  }, []);

  useEffect(() => { void loadAll(); }, [loadAll]);

  useEffect(() => {
    if (allRecordsRef.current) clearInterval(allRecordsRef.current);
    if (autoRefresh) {
      allRecordsRef.current = setInterval(() => void loadAll(), 30_000);
    }
    return () => { if (allRecordsRef.current) clearInterval(allRecordsRef.current); };
  }, [autoRefresh, loadAll]);

  const { records, loading, error, refetch } = useRatings(activeTab, autoRefresh);
  const { health, refetch: refetchHealth } = useHealth(autoRefresh);

  const handleRefresh = () => {
    void refetch();
    void refetchHealth();
    void loadAll();
  };

  // Tab counts always from all records
  const counts = useMemo(() => {
    const c: Partial<Record<Tab, number>> = { All: allRecords.length };
    for (const r of allRecords) {
      const ac = r.asset_class as AssetClass;
      c[ac] = (c[ac] ?? 0) + 1;
    }
    return c;
  }, [allRecords]);

  return (
    <div className="min-h-screen bg-[#0a0e1a] font-sans">
      <Header
        health={health}
        loading={loading}
        autoRefresh={autoRefresh}
        onToggleAutoRefresh={() => setAutoRefresh((v) => !v)}
        onRefresh={handleRefresh}
      />

      <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
        {/* Tab bar */}
        <div className="mb-6">
          <AssetClassTabs
            active={activeTab}
            onChange={setActiveTab}
            counts={counts}
          />
        </div>

        {/* Error state */}
        {error && (
          <div className="mb-6 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 8v4M12 16h.01" />
            </svg>
            <span>Failed to load ratings: {error}</span>
            <button
              onClick={handleRefresh}
              className="ml-auto text-xs underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && records.length === 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="h-64 rounded-xl bg-gray-800/40 border border-gray-800 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* Loading overlay on existing data */}
        {loading && records.length > 0 && (
          <div className="flex items-center gap-2 mb-4 text-sm text-gray-500">
            <RefreshIcon size={14} className="animate-spin" />
            Refreshing...
          </div>
        )}

        {/* Empty state */}
        {!loading && records.length === 0 && !error && (
          <EmptyState message={`No ratings found for ${activeTab === 'All' ? 'any asset class' : activeTab}`} />
        )}

        {/* Dashboard charts — shown above the cards */}
        {records.length > 0 && (
          <DashboardCharts records={records} />
        )}

        {/* Cards grid */}
        {records.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {records.map((record) => (
              <RatingCard
                key={record.record_id}
                record={record}
                onClick={setSelectedRecord}
              />
            ))}
          </div>
        )}
      </main>

      {/* Detail panel */}
      <DetailPanel
        record={selectedRecord}
        onClose={() => setSelectedRecord(null)}
      />
    </div>
  );
}
