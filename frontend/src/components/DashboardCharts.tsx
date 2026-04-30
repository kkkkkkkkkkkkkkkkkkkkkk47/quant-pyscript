/**
 * DashboardCharts — portfolio-level charts shown above the cards grid.
 *
 * Four panels:
 * 1. Composite Score Bar Chart — all securities ranked by composite score
 * 2. Rating Distribution Donut — count of each rating label
 * 3. Sub-Score Comparison — grouped bar chart (S / O / E per security)
 * 4. Score Heatmap — colour-coded table of all scores
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  PieChart,
  Pie,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { RatingRecord } from '../types';
import { RATING_COLORS } from '../utils/formatters';

interface Props {
  records: RatingRecord[];
}

// ─── helpers ────────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: '8px',
  color: '#f9fafb',
  fontSize: '12px',
  padding: '8px 12px',
};

const AXIS_TICK = { fill: '#6b7280', fontSize: 11, fontFamily: 'Inter, sans-serif' };
const AXIS_LINE = { stroke: '#1f2937' };

function scoreColor(score: number): string {
  if (score >= 4.5) return '#10b981';
  if (score >= 3.5) return '#34d399';
  if (score >= 2.5) return '#6b7280';
  if (score >= 1.5) return '#f87171';
  return '#ef4444';
}

function shortId(id: string): string {
  // Shorten long identifiers for axis labels
  return id.length > 8 ? id.slice(0, 7) + '…' : id;
}

// ─── 1. Composite Score Bar Chart ───────────────────────────────────────────

function CompositeScoreChart({ records }: Props) {
  const data = [...records]
    .sort((a, b) => b.composite_score - a.composite_score)
    .map((r) => ({
      id: shortId(r.security_id),
      fullId: r.security_id,
      score: parseFloat(r.composite_score.toFixed(2)),
      rating: r.rating,
      color: RATING_COLORS[r.rating]?.hex ?? '#6b7280',
    }));

  return (
    <div className="p-4 rounded-xl bg-[#111827] border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-200 mb-4">
        Composite Scores — All Securities
      </h3>
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: -15 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis dataKey="id" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} />
            <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} />
            {/* Reference lines at rating thresholds */}
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: number, _: string, props: { payload?: { fullId?: string; rating?: string } }) => [
                `${value.toFixed(2)} / 5.00`,
                props.payload?.fullId ?? '',
              ]}
              labelFormatter={() => ''}
            />
            <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={48}>
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.color} fillOpacity={0.85} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* Rating threshold legend */}
      <div className="flex items-center gap-3 mt-3 flex-wrap justify-center">
        {Object.entries(RATING_COLORS).map(([label, c]) => (
          <div key={label} className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: c.hex }} />
            <span className="text-xs text-gray-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── 2. Rating Distribution Donut ───────────────────────────────────────────

const RADIAN = Math.PI / 180;

interface LabelProps {
  cx: number;
  cy: number;
  midAngle: number;
  innerRadius: number;
  outerRadius: number;
  percent: number;
  name: string;
}

function renderCustomLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }: LabelProps) {
  if (percent < 0.08) return null;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={600}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

function RatingDistributionChart({ records }: Props) {
  const counts: Record<string, number> = {};
  for (const r of records) {
    counts[r.rating] = (counts[r.rating] ?? 0) + 1;
  }

  const data = Object.entries(counts)
    .map(([name, value]) => ({ name, value, color: RATING_COLORS[name]?.hex ?? '#6b7280' }))
    .sort((a, b) => b.value - a.value);

  if (data.length === 0) return null;

  return (
    <div className="p-4 rounded-xl bg-[#111827] border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-200 mb-4">Rating Distribution</h3>
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={85}
              paddingAngle={3}
              dataKey="value"
              labelLine={false}
              label={renderCustomLabel}
            >
              {data.map((entry, i) => (
                <Cell key={i} fill={entry.color} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: number, name: string) => [`${value} securities`, name]}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── 3. Sub-Score Grouped Bar Chart ─────────────────────────────────────────

function SubScoreComparisonChart({ records }: Props) {
  const data = records.map((r) => ({
    id: shortId(r.security_id),
    fullId: r.security_id,
    sentiment: parseFloat(r.sentiment_score.toFixed(2)),
    orderflow: parseFloat(r.orderflow_score.toFixed(2)),
    economic: parseFloat(r.economic_score.toFixed(2)),
  }));

  return (
    <div className="p-4 rounded-xl bg-[#111827] border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-200 mb-4">Sub-Score Comparison</h3>
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: -15 }} barCategoryGap="20%">
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis dataKey="id" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} />
            <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = { sentiment: 'Sentiment', orderflow: 'Order Flow', economic: 'Economic' };
                return [`${value.toFixed(2)} / 5.00`, labels[name] ?? name];
              }}
            />
            <Legend
              iconType="square"
              iconSize={8}
              wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }}
              formatter={(v: string) => ({ sentiment: 'Sentiment', orderflow: 'Order Flow', economic: 'Economic' }[v] ?? v)}
            />
            <Bar dataKey="sentiment" fill="#60a5fa" fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={20} />
            <Bar dataKey="orderflow" fill="#a78bfa" fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={20} />
            <Bar dataKey="economic" fill="#fbbf24" fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={20} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ─── 4. Score Heatmap Table ──────────────────────────────────────────────────

function ScoreHeatmap({ records }: Props) {
  const sorted = [...records].sort((a, b) => b.composite_score - a.composite_score);

  function cellBg(score: number): string {
    if (score >= 4.5) return 'rgba(16,185,129,0.35)';
    if (score >= 3.5) return 'rgba(52,211,153,0.25)';
    if (score >= 2.5) return 'rgba(107,114,128,0.20)';
    if (score >= 1.5) return 'rgba(248,113,113,0.25)';
    return 'rgba(239,68,68,0.35)';
  }

  return (
    <div className="p-4 rounded-xl bg-[#111827] border border-gray-800">
      <h3 className="text-sm font-semibold text-gray-200 mb-4">Score Heatmap</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left py-2 pr-3 text-gray-500 font-medium w-24">Security</th>
              <th className="text-center py-2 px-2 text-gray-500 font-medium">Rating</th>
              <th className="text-center py-2 px-2 text-blue-400 font-medium">Sentiment</th>
              <th className="text-center py-2 px-2 text-purple-400 font-medium">Order Flow</th>
              <th className="text-center py-2 px-2 text-amber-400 font-medium">Economic</th>
              <th className="text-center py-2 px-2 text-gray-300 font-medium">Composite</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const ratingColor = RATING_COLORS[r.rating]?.hex ?? '#6b7280';
              return (
                <tr key={r.record_id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="py-2 pr-3 font-semibold text-white truncate max-w-[96px]">
                    {r.security_id}
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-semibold"
                      style={{ backgroundColor: `${ratingColor}20`, color: ratingColor, border: `1px solid ${ratingColor}40` }}
                    >
                      {r.rating}
                    </span>
                  </td>
                  {[r.sentiment_score, r.orderflow_score, r.economic_score, r.composite_score].map((score, i) => (
                    <td
                      key={i}
                      className="py-2 px-2 text-center font-mono font-semibold rounded"
                      style={{ backgroundColor: cellBg(score), color: scoreColor(score) }}
                    >
                      {score.toFixed(2)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* Heatmap legend */}
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <span className="text-xs text-gray-600">Scale:</span>
        {[
          { label: '≥4.5', bg: 'rgba(16,185,129,0.35)', color: '#10b981' },
          { label: '≥3.5', bg: 'rgba(52,211,153,0.25)', color: '#34d399' },
          { label: '≥2.5', bg: 'rgba(107,114,128,0.20)', color: '#9ca3af' },
          { label: '≥1.5', bg: 'rgba(248,113,113,0.25)', color: '#f87171' },
          { label: '<1.5', bg: 'rgba(239,68,68,0.35)', color: '#ef4444' },
        ].map(({ label, bg, color }) => (
          <div key={label} className="flex items-center gap-1">
            <div className="w-5 h-3 rounded-sm" style={{ backgroundColor: bg, border: `1px solid ${color}40` }} />
            <span className="text-xs text-gray-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main export ─────────────────────────────────────────────────────────────

export function DashboardCharts({ records }: Props) {
  if (records.length === 0) return null;

  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 mb-4">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 3v18h18" />
          <path d="m19 9-5 5-4-4-3 3" />
        </svg>
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">Portfolio Overview</h2>
        <div className="flex-1 h-px bg-gray-800" />
        <span className="text-xs text-gray-600">{records.length} securities</span>
      </div>

      {/* Top row: composite scores + distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div className="lg:col-span-2">
          <CompositeScoreChart records={records} />
        </div>
        <div>
          <RatingDistributionChart records={records} />
        </div>
      </div>

      {/* Bottom row: sub-score comparison + heatmap */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SubScoreComparisonChart records={records} />
        <ScoreHeatmap records={records} />
      </div>
    </div>
  );
}
