import { useEffect, useRef, useState } from 'react';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Tooltip as RechartTooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
} from 'recharts';
import type { RatingRecord } from '../types';
import { RATING_COLORS, formatDateTime, formatPct, formatScore } from '../utils/formatters';
import { RatingBadge } from './RatingBadge';
import { HistoryChart } from './HistoryChart';
import { CloseIcon, AlertTriangleIcon } from './icons';

interface Props {
  record: RatingRecord | null;
  onClose: () => void;
}

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: '8px',
  color: '#f9fafb',
  fontSize: '12px',
  padding: '8px 12px',
};

// ─── Inline Radar (no ResponsiveContainer — uses measured width) ─────────────
function InlineRadar({ record, color }: { record: RatingRecord; color: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    ro.observe(el);
    // Initial measurement
    setWidth(el.clientWidth || 320);
    return () => ro.disconnect();
  }, []);

  const data = [
    { subject: 'Sentiment',  value: parseFloat(record.sentiment_score.toFixed(2)),  fullMark: 5 },
    { subject: 'Order Flow', value: parseFloat(record.orderflow_score.toFixed(2)),  fullMark: 5 },
    { subject: 'Economic',   value: parseFloat(record.economic_score.toFixed(2)),   fullMark: 5 },
  ];

  const h = Math.min(width * 0.65, 240);

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      <RadarChart width={width} height={h} data={data} cx="50%" cy="50%" outerRadius={h * 0.35}>
        <PolarGrid stroke="#374151" strokeDasharray="3 3" />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: '#9ca3af', fontSize: 12, fontFamily: 'Inter, sans-serif' }}
          tickLine={false}
        />
        <PolarRadiusAxis angle={90} domain={[0, 5]} tick={{ fill: '#4b5563', fontSize: 9 }} tickCount={4} axisLine={false} />
        <Radar name="Score" dataKey="value" stroke={color} fill={color} fillOpacity={0.25} strokeWidth={2}
          dot={{ fill: color, r: 4, strokeWidth: 0 }} />
        <RechartTooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v: number) => [`${v.toFixed(2)} / 5.00`, 'Score']}
        />
      </RadarChart>
    </div>
  );
}

// ─── Sub-score bar chart ──────────────────────────────────────────────────────
function SubScoreBars({ record }: { record: RatingRecord }) {
  const data = [
    { name: 'Sentiment',  value: parseFloat(record.sentiment_score.toFixed(2)),  color: '#60a5fa' },
    { name: 'Order Flow', value: parseFloat(record.orderflow_score.toFixed(2)),  color: '#a78bfa' },
    { name: 'Economic',   value: parseFloat(record.economic_score.toFixed(2)),   color: '#fbbf24' },
    { name: 'Composite',  value: parseFloat(record.composite_score.toFixed(2)),  color: RATING_COLORS[record.rating]?.hex ?? '#6b7280' },
  ];

  return (
    <div style={{ width: '100%', height: 180 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: -15 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
          <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} />
          <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} />
          <RechartTooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v: number, name: string) => [`${v.toFixed(2)} / 5.00`, name]}
            cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          />
          <Bar dataKey="value" radius={[5, 5, 0, 0]} maxBarSize={52}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Main panel ───────────────────────────────────────────────────────────────
export function DetailPanel({ record, onClose }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (record) {
      requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
    } else {
      setVisible(false);
    }
  }, [record]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  useEffect(() => {
    document.body.style.overflow = record ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [record]);

  if (!record) return null;

  const colors = RATING_COLORS[record.rating] ?? RATING_COLORS['Neutral'];
  const wp = record.weight_profile;
  const total = wp.sentiment_pct + wp.orderflow_pct + wp.economic_pct || 100;
  const sW = (wp.sentiment_pct / total) * 100;
  const oW = (wp.orderflow_pct / total) * 100;
  const eW = (wp.economic_pct / total) * 100;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm transition-opacity duration-300"
        style={{ opacity: visible ? 1 : 0 }}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className="fixed right-0 top-0 bottom-0 z-50 flex flex-col bg-[#0d1117] border-l border-gray-800 shadow-2xl overflow-y-auto transition-transform duration-300 ease-out"
        style={{
          width: 'min(560px, 100vw)',
          transform: visible ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        {/* ── Header ── */}
        <div
          className="flex items-start justify-between p-5 border-b border-gray-800 flex-shrink-0 sticky top-0 bg-[#0d1117] z-10"
          style={{ borderLeft: `4px solid ${colors.hex}` }}
        >
          <div className="min-w-0">
            <h2 className="text-2xl font-bold text-white">{record.security_id}</h2>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <RatingBadge rating={record.rating} size="md" />
              <span className="text-xs px-2 py-1 rounded bg-gray-700/60 text-gray-400">{record.asset_class}</span>
              {wp.sub_category && (
                <span className="text-xs px-2 py-1 rounded bg-gray-700/40 text-gray-500">{wp.sub_category}</span>
              )}
              {record.data_deficient && (
                <span className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                  <AlertTriangleIcon size={11} />
                  Data deficient
                </span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-all duration-200 flex-shrink-0 ml-3"
          >
            <CloseIcon size={20} />
          </button>
        </div>

        <div className="flex-1 p-5 flex flex-col gap-5">

          {/* ── Composite score gauge ── */}
          <div className="p-4 rounded-xl bg-gray-800/40 border border-gray-700/50">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-300">Composite Score</span>
              <span className="text-3xl font-bold font-mono tabular-nums" style={{ color: colors.hex }}>
                {formatScore(record.composite_score)}
                <span className="text-sm text-gray-500 font-normal"> / 5.00</span>
              </span>
            </div>
            <div style={{ padding: '6px 0' }}>
              <div className="relative w-full rounded-full" style={{ height: 12, background: 'linear-gradient(to right, #ef4444 0%, #6b7280 50%, #10b981 100%)' }}>
                <div
                  className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-full border-2 border-white"
                  style={{
                    left: `${(record.composite_score / 5) * 100}%`,
                    width: 20, height: 20,
                    backgroundColor: colors.hex,
                    boxShadow: `0 0 0 3px ${colors.hex}40, 0 2px 8px rgba(0,0,0,0.7)`,
                  }}
                />
              </div>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-xs text-gray-600">0 — Strong Sell</span>
              <span className="text-xs text-gray-600">5 — Strong Buy</span>
            </div>
          </div>

          {/* ── Score bar chart ── */}
          <div className="p-4 rounded-xl bg-gray-800/40 border border-gray-700/50">
            <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2"><rect x="3" y="12" width="4" height="9" rx="1"/><rect x="10" y="7" width="4" height="14" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/></svg>
              Score Breakdown
            </h3>
            <SubScoreBars record={record} />
          </div>

          {/* ── Radar chart ── */}
          <div className="p-4 rounded-xl bg-gray-800/40 border border-gray-700/50">
            <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/><line x1="12" y1="2" x2="12" y2="22"/><line x1="2" y1="8.5" x2="22" y2="8.5"/><line x1="2" y1="15.5" x2="22" y2="15.5"/></svg>
              Score Radar
            </h3>
            <InlineRadar record={record} color={colors.hex} />
          </div>

          {/* ── History chart ── */}
          <div className="p-4 rounded-xl bg-gray-800/40 border border-gray-700/50">
            <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
              7-Day History
            </h3>
            <HistoryChart securityId={record.security_id} />
          </div>

          {/* ── Weight profile ── */}
          <div className="p-4 rounded-xl bg-gray-800/40 border border-gray-700/50">
            <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20"/><path d="M2 12h20"/></svg>
              Weight Profile
            </h3>
            <div className="flex h-8 rounded-lg overflow-hidden gap-0.5">
              {[
                { w: sW, pct: wp.sentiment_pct, color: '#3b82f6', label: 'S' },
                { w: oW, pct: wp.orderflow_pct, color: '#8b5cf6', label: 'O' },
                { w: eW, pct: wp.economic_pct,  color: '#f59e0b', label: 'E' },
              ].map(({ w, pct, color, label }) => (
                <div
                  key={label}
                  className="flex items-center justify-center text-xs font-bold text-white/90 transition-all"
                  style={{ width: `${w}%`, backgroundColor: color }}
                >
                  {w > 10 ? `${label} ${formatPct(pct)}` : ''}
                </div>
              ))}
            </div>
            <div className="flex items-center gap-4 mt-3 flex-wrap">
              {[
                { label: 'Sentiment',  pct: wp.sentiment_pct, color: '#3b82f6' },
                { label: 'Order Flow', pct: wp.orderflow_pct, color: '#8b5cf6' },
                { label: 'Economic',   pct: wp.economic_pct,  color: '#f59e0b' },
              ].map(({ label, pct, color }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
                  <span className="text-xs text-gray-400">{label} {formatPct(pct)}</span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Metadata ── */}
          <div className="rounded-xl bg-gray-800/40 border border-gray-700/50 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-700/50">
              <h3 className="text-sm font-semibold text-gray-200">Metadata</h3>
            </div>
            <table className="w-full text-xs">
              <tbody>
                {[
                  ['Record ID',     record.record_id],
                  ['Security',      record.security_id],
                  ['Asset Class',   record.asset_class],
                  ['Sub-Category',  wp.sub_category ?? '—'],
                  ['Computed At',   formatDateTime(record.computed_at)],
                  ['Data Deficient',record.data_deficient ? 'Yes' : 'No'],
                ].map(([label, value], i) => (
                  <tr key={label} className={i % 2 === 0 ? 'bg-gray-800/20' : ''}>
                    <td className="px-4 py-2.5 text-gray-500 font-medium w-32">{label}</td>
                    <td className="px-4 py-2.5 text-gray-300 font-mono break-all">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </div>
      </div>
    </>
  );
}
