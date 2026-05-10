/**
 * MonteCarloPanel — runs N Monte Carlo price path simulations in the browser
 * using the composite score as drift and sub-score spread as volatility.
 *
 * Displayed inside the DetailPanel when a card is clicked.
 */

import { useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { RatingRecord } from '../types';
import { RATING_COLORS } from '../utils/formatters';

interface Props {
  record: RatingRecord;
}

// ─── Monte Carlo engine (pure JS, runs in browser) ───────────────────────────

interface SimParams {
  drift: number;       // annualised drift (from composite score)
  volatility: number;  // annualised volatility (from sub-score spread)
  steps: number;       // number of time steps (days)
  paths: number;       // number of simulated paths
  startPrice: number;  // normalised starting price (100)
}

function boxMullerRandom(): number {
  // Box-Muller transform for standard normal random variable
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

function runMonteCarlo({ drift, volatility, steps, paths, startPrice }: SimParams): number[][] {
  const dt = 1 / 252; // daily time step (trading days)
  const allPaths: number[][] = [];

  for (let p = 0; p < paths; p++) {
    const path: number[] = [startPrice];
    let price = startPrice;
    for (let t = 0; t < steps; t++) {
      const z = boxMullerRandom();
      // Geometric Brownian Motion: S(t+dt) = S(t) * exp((μ - σ²/2)*dt + σ*√dt*Z)
      const ret = (drift - 0.5 * volatility * volatility) * dt + volatility * Math.sqrt(dt) * z;
      price = price * Math.exp(ret);
      path.push(parseFloat(price.toFixed(4)));
    }
    allPaths.push(path);
  }
  return allPaths;
}

function deriveParams(record: RatingRecord): SimParams {
  // Map composite score (0–5) to annualised drift
  // Score 2.5 = neutral (0% drift), 5.0 = +40% drift, 0.0 = -40% drift
  const drift = ((record.composite_score - 2.5) / 2.5) * 0.40;

  // Volatility from sub-score spread — wider spread = more uncertainty
  const scores = [record.sentiment_score, record.orderflow_score, record.economic_score];
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const variance = scores.reduce((a, b) => a + (b - mean) ** 2, 0) / scores.length;
  const spread = Math.sqrt(variance);
  // Map spread (0–2.5) to volatility (10%–60%)
  const volatility = 0.10 + (spread / 2.5) * 0.50;

  return { drift, volatility, steps: 30, paths: 50, startPrice: 100 };
}

// ─── Percentile helpers ───────────────────────────────────────────────────────

function percentile(arr: number[], p: number): number {
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

// ─── Chart data builder ───────────────────────────────────────────────────────

interface ChartPoint {
  day: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  mean: number;
}

function buildChartData(paths: number[][], steps: number): ChartPoint[] {
  const points: ChartPoint[] = [];
  for (let t = 0; t <= steps; t++) {
    const vals = paths.map((p) => p[t]);
    points.push({
      day: t,
      p10: parseFloat(percentile(vals, 10).toFixed(2)),
      p25: parseFloat(percentile(vals, 25).toFixed(2)),
      p50: parseFloat(percentile(vals, 50).toFixed(2)),
      p75: parseFloat(percentile(vals, 75).toFixed(2)),
      p90: parseFloat(percentile(vals, 90).toFixed(2)),
      mean: parseFloat((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)),
    });
  }
  return points;
}

// ─── Component ────────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: '8px',
  color: '#f9fafb',
  fontSize: '11px',
  padding: '8px 12px',
};

export function MonteCarloPanel({ record }: Props) {
  const [simCount, setSimCount] = useState(50);
  const [horizon, setHorizon] = useState(30);

  const color = RATING_COLORS[record.rating]?.hex ?? '#10b981';

  const { params, chartData, finalStats } = useMemo(() => {
    const p = deriveParams(record);
    p.paths = simCount;
    p.steps = horizon;
    const ps = runMonteCarlo(p);
    const cd = buildChartData(ps, horizon);
    const finals = ps.map((path) => path[path.length - 1]);
    const stats = {
      mean: parseFloat((finals.reduce((a, b) => a + b, 0) / finals.length).toFixed(2)),
      p10: parseFloat(percentile(finals, 10).toFixed(2)),
      p50: parseFloat(percentile(finals, 50).toFixed(2)),
      p90: parseFloat(percentile(finals, 90).toFixed(2)),
      bullish: finals.filter((v) => v > 100).length,
      bearish: finals.filter((v) => v < 100).length,
    };
    return { params: p, chartData: cd, finalStats: stats };
  }, [record, simCount, horizon]);

  const driftPct = (params.drift * 100).toFixed(1);
  const volPct = (params.volatility * 100).toFixed(1);
  const bullPct = ((finalStats.bullish / simCount) * 100).toFixed(0);
  const bearPct = ((finalStats.bearish / simCount) * 100).toFixed(0);

  return (
    <div className="flex flex-col gap-4">
      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Simulations</span>
          {[20, 50, 100, 200].map((n) => (
            <button
              key={n}
              onClick={() => setSimCount(n)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                simCount === n
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                  : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-gray-300'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Horizon</span>
          {[10, 30, 60, 90].map((d) => (
            <button
              key={d}
              onClick={() => setHorizon(d)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                horizon === d
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                  : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-gray-300'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Derived parameters */}
      <div className="grid grid-cols-2 gap-2">
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
          <div className="text-xs text-gray-500 mb-1">Annualised Drift</div>
          <div className={`text-lg font-bold font-mono ${parseFloat(driftPct) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {parseFloat(driftPct) >= 0 ? '+' : ''}{driftPct}%
          </div>
          <div className="text-xs text-gray-600 mt-0.5">from composite {record.composite_score.toFixed(2)}</div>
        </div>
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
          <div className="text-xs text-gray-500 mb-1">Annualised Volatility</div>
          <div className="text-lg font-bold font-mono text-amber-400">{volPct}%</div>
          <div className="text-xs text-gray-600 mt-0.5">from sub-score spread</div>
        </div>
      </div>

      {/* Fan chart */}
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="day"
              tick={{ fill: '#6b7280', fontSize: 10 }}
              axisLine={{ stroke: '#1f2937' }}
              tickLine={false}
              label={{ value: 'Days', position: 'insideBottomRight', offset: -5, fill: '#4b5563', fontSize: 10 }}
            />
            <YAxis
              tick={{ fill: '#6b7280', fontSize: 10 }}
              axisLine={{ stroke: '#1f2937' }}
              tickLine={false}
              tickFormatter={(v: number) => `${v.toFixed(0)}`}
            />
            <ReferenceLine y={100} stroke="#374151" strokeDasharray="4 4" label={{ value: 'Start', fill: '#4b5563', fontSize: 9 }} />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(value: number, name: string) => {
                const labels: Record<string, string> = {
                  p90: '90th pct', p75: '75th pct', p50: 'Median',
                  mean: 'Mean', p25: '25th pct', p10: '10th pct',
                };
                return [`${value.toFixed(2)}`, labels[name] ?? name];
              }}
              labelFormatter={(label: number) => `Day ${label}`}
            />
            {/* Fan bands — outer to inner */}
            <Line type="monotone" dataKey="p90" stroke={color} strokeWidth={1} strokeDasharray="3 3" dot={false} opacity={0.4} />
            <Line type="monotone" dataKey="p75" stroke={color} strokeWidth={1.5} dot={false} opacity={0.6} />
            <Line type="monotone" dataKey="p50" stroke={color} strokeWidth={2.5} dot={false} opacity={1} />
            <Line type="monotone" dataKey="mean" stroke="#f9fafb" strokeWidth={1.5} strokeDasharray="5 3" dot={false} opacity={0.5} />
            <Line type="monotone" dataKey="p25" stroke={color} strokeWidth={1.5} dot={false} opacity={0.6} />
            <Line type="monotone" dataKey="p10" stroke={color} strokeWidth={1} strokeDasharray="3 3" dot={false} opacity={0.4} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 flex-wrap text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <div className="w-6 h-0.5 rounded" style={{ backgroundColor: color, opacity: 1 }} />
          <span>Median (P50)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-6 h-0.5 rounded" style={{ backgroundColor: color, opacity: 0.6 }} />
          <span>P25–P75</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-6 h-0.5 rounded" style={{ backgroundColor: color, opacity: 0.4 }} />
          <span>P10–P90</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-6 h-0.5 rounded bg-white opacity-50" />
          <span>Mean</span>
        </div>
      </div>

      {/* Final distribution stats */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'P10 outcome', value: `${finalStats.p10.toFixed(1)}`, sub: `${(finalStats.p10 - 100).toFixed(1)}%` },
          { label: 'Median outcome', value: `${finalStats.p50.toFixed(1)}`, sub: `${(finalStats.p50 - 100).toFixed(1)}%` },
          { label: 'P90 outcome', value: `${finalStats.p90.toFixed(1)}`, sub: `${(finalStats.p90 - 100).toFixed(1)}%` },
        ].map(({ label, value, sub }) => {
          const change = parseFloat(sub);
          return (
            <div key={label} className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50 text-center">
              <div className="text-xs text-gray-500 mb-1">{label}</div>
              <div className="text-base font-bold font-mono text-white">{value}</div>
              <div className={`text-xs font-mono mt-0.5 ${change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {change >= 0 ? '+' : ''}{sub}
              </div>
            </div>
          );
        })}
      </div>

      {/* Bull/Bear split */}
      <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-500">Outcome distribution ({simCount} paths, {horizon}d)</span>
        </div>
        <div className="flex h-4 rounded-full overflow-hidden gap-0.5">
          <div
            className="flex items-center justify-center text-xs font-bold text-emerald-100 rounded-l-full transition-all"
            style={{ width: `${bullPct}%`, backgroundColor: '#10b981' }}
          >
            {parseInt(bullPct) > 15 ? `${bullPct}%` : ''}
          </div>
          <div
            className="flex items-center justify-center text-xs font-bold text-red-100 rounded-r-full transition-all"
            style={{ width: `${bearPct}%`, backgroundColor: '#ef4444' }}
          >
            {parseInt(bearPct) > 15 ? `${bearPct}%` : ''}
          </div>
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-xs text-emerald-400">{bullPct}% bullish paths</span>
          <span className="text-xs text-red-400">{bearPct}% bearish paths</span>
        </div>
      </div>

      <p className="text-xs text-gray-600 leading-relaxed">
        Geometric Brownian Motion simulation. Drift derived from composite score ({record.composite_score.toFixed(2)}/5.00).
        Volatility derived from sub-score dispersion. For illustrative purposes only — not financial advice.
      </p>
    </div>
  );
}
