/**
 * MonteCarloGuardrail — TP/SL Guardrail Fan Chart
 *
 * Runs Monte Carlo paths and overlays:
 * - A Take Profit (TP) line — green horizontal reference
 * - A Stop Loss (SL) line — red horizontal reference
 *
 * Shows:
 * - Fan chart of all paths with TP/SL guardrails
 * - % of paths that hit TP before SL
 * - % of paths that hit SL before TP
 * - % of paths that hit neither within the horizon
 * - Expected time to first TP/SL hit (median)
 * - Risk/Reward ratio
 */

import { useEffect, useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts';
import type { RatingRecord } from '../types';
import { RATING_COLORS } from '../utils/formatters';
import { fetchPrice } from '../api/client';

interface Props {
  record: RatingRecord;
}

// ─── GBM engine (same as MonteCarloPanel) ────────────────────────────────────

function boxMuller(): number {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

function runGBM(
  startPrice: number,
  drift: number,
  volatility: number,
  steps: number,
  paths: number,
): number[][] {
  const dt = 1 / 252;
  return Array.from({ length: paths }, () => {
    const path = [startPrice];
    let p = startPrice;
    for (let t = 0; t < steps; t++) {
      p = p * Math.exp((drift - 0.5 * volatility ** 2) * dt + volatility * Math.sqrt(dt) * boxMuller());
      path.push(p);
    }
    return path;
  });
}

// ─── Guardrail analysis ───────────────────────────────────────────────────────

interface GuardrailResult {
  tpHit: number;       // paths that hit TP first
  slHit: number;       // paths that hit SL first
  neither: number;     // paths that hit neither
  total: number;
  medianTpDay: number | null;  // median day TP was first hit
  medianSlDay: number | null;  // median day SL was first hit
}

function analyseGuardrails(
  paths: number[][],
  tp: number,
  sl: number,
): GuardrailResult {
  let tpHit = 0, slHit = 0, neither = 0;
  const tpDays: number[] = [];
  const slDays: number[] = [];

  for (const path of paths) {
    let hitTpDay: number | null = null;
    let hitSlDay: number | null = null;

    for (let t = 1; t < path.length; t++) {
      if (hitTpDay === null && path[t] >= tp) hitTpDay = t;
      if (hitSlDay === null && path[t] <= sl) hitSlDay = t;
      if (hitTpDay !== null && hitSlDay !== null) break;
    }

    if (hitTpDay !== null && (hitSlDay === null || hitTpDay <= hitSlDay)) {
      tpHit++;
      tpDays.push(hitTpDay);
    } else if (hitSlDay !== null && (hitTpDay === null || hitSlDay < hitTpDay)) {
      slHit++;
      slDays.push(hitSlDay);
    } else {
      neither++;
    }
  }

  const median = (arr: number[]) => {
    if (arr.length === 0) return null;
    const s = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[mid];
  };

  return {
    tpHit, slHit, neither,
    total: paths.length,
    medianTpDay: median(tpDays),
    medianSlDay: median(slDays),
  };
}

// ─── Chart data — sample paths + percentile bands ────────────────────────────

interface ChartPoint {
  day: number;
  p10: number; p25: number; p50: number; p75: number; p90: number;
}

function pct(arr: number[], p: number): number {
  const s = [...arr].sort((a, b) => a - b);
  const i = (p / 100) * (s.length - 1);
  const lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

function buildChart(paths: number[][], steps: number): ChartPoint[] {
  return Array.from({ length: steps + 1 }, (_, t) => {
    const vals = paths.map((p) => p[t]);
    return {
      day: t,
      p10: pct(vals, 10), p25: pct(vals, 25), p50: pct(vals, 50),
      p75: pct(vals, 75), p90: pct(vals, 90),
    };
  });
}

// ─── Decimal precision ────────────────────────────────────────────────────────

function decimals(assetClass: string, price: number): number {
  if (assetClass === 'Crypto') return price > 1000 ? 2 : 4;
  if (assetClass === 'FX') return 4;
  return 2;
}

function fmt(v: number, d: number) { return v.toFixed(d); }

// ─── Component ────────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937', border: '1px solid #374151',
  borderRadius: '8px', color: '#f9fafb', fontSize: '11px', padding: '8px 12px',
};

export function MonteCarloGuardrail({ record }: Props) {
  const [realPrice, setRealPrice] = useState<number | null>(null);
  const [priceLoading, setPriceLoading] = useState(true);
  const [horizon, setHorizon] = useState(30);
  const [simCount] = useState(200); // fixed at 200 for accuracy

  // TP/SL as % offset from start price
  const [tpPct, setTpPct] = useState(2.0);   // +2% default TP
  const [slPct, setSlPct] = useState(1.0);   // -1% default SL

  useEffect(() => {
    setPriceLoading(true);
    fetchPrice(record.security_id)
      .then((p) => setRealPrice(p))
      .catch(() => setRealPrice(null))
      .finally(() => setPriceLoading(false));
  }, [record.security_id]);

  const startPrice = realPrice ?? 100;
  const dec = decimals(record.asset_class, startPrice);
  const color = RATING_COLORS[record.rating]?.hex ?? '#10b981';

  // Derive GBM params
  const drift = ((record.composite_score - 2.5) / 2.5) * 0.40;
  const scores = [record.sentiment_score, record.orderflow_score, record.economic_score];
  const scoreMean = scores.reduce((a, b) => a + b, 0) / 3;
  const spread = Math.sqrt(scores.reduce((a, b) => a + (b - scoreMean) ** 2, 0) / 3);
  const volatility = 0.10 + (spread / 2.5) * 0.50;

  // Absolute TP/SL prices
  const tpPrice = startPrice * (1 + tpPct / 100);
  const slPrice = startPrice * (1 - slPct / 100);
  const rrRatio = tpPct / slPct;

  const { chartData, guardrail } = useMemo(() => {
    const paths = runGBM(startPrice, drift, volatility, horizon, simCount);
    return {
      chartData: buildChart(paths, horizon),
      guardrail: analyseGuardrails(paths, tpPrice, slPrice),
    };
  }, [startPrice, drift, volatility, horizon, simCount, tpPrice, slPrice]);

  const tpPct2 = ((guardrail.tpHit / guardrail.total) * 100).toFixed(1);
  const slPct2 = ((guardrail.slHit / guardrail.total) * 100).toFixed(1);
  const neitherPct = ((guardrail.neither / guardrail.total) * 100).toFixed(1);

  // Y domain with padding
  const allVals = chartData.flatMap((d) => [d.p10, d.p90]);
  const yMin = Math.min(...allVals, slPrice) * 0.998;
  const yMax = Math.max(...allVals, tpPrice) * 1.002;

  return (
    <div className="flex flex-col gap-4">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="text-xs text-gray-500 mb-0.5">Starting price</div>
          <div className="flex items-center gap-2">
            {priceLoading ? (
              <span className="text-xs text-gray-500">Loading...</span>
            ) : (
              <>
                <div className={`w-1.5 h-1.5 rounded-full ${realPrice !== null ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                <span className="text-lg font-bold font-mono text-white">{fmt(startPrice, dec)}</span>
                <span className="text-xs text-gray-500">{record.security_id}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Horizon</span>
          {[10, 20, 30, 60].map((d) => (
            <button key={d} onClick={() => setHorizon(d)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                horizon === d
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                  : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-gray-300'
              }`}>{d}d</button>
          ))}
        </div>
      </div>

      {/* TP/SL sliders */}
      <div className="grid grid-cols-2 gap-3">
        {/* Take Profit */}
        <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-emerald-400">Take Profit</span>
            <span className="text-sm font-bold font-mono text-emerald-400">+{tpPct.toFixed(1)}%</span>
          </div>
          <input
            type="range" min="0.5" max="10" step="0.1"
            value={tpPct}
            onChange={(e) => setTpPct(parseFloat(e.target.value))}
            className="w-full accent-emerald-500"
          />
          <div className="text-xs font-mono text-emerald-300 mt-1">{fmt(tpPrice, dec)}</div>
        </div>

        {/* Stop Loss */}
        <div className="p-3 rounded-xl bg-red-500/5 border border-red-500/20">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-red-400">Stop Loss</span>
            <span className="text-sm font-bold font-mono text-red-400">-{slPct.toFixed(1)}%</span>
          </div>
          <input
            type="range" min="0.5" max="10" step="0.1"
            value={slPct}
            onChange={(e) => setSlPct(parseFloat(e.target.value))}
            className="w-full accent-red-500"
          />
          <div className="text-xs font-mono text-red-300 mt-1">{fmt(slPrice, dec)}</div>
        </div>
      </div>

      {/* R:R ratio */}
      <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-800/60 border border-gray-700/50">
        <span className="text-xs text-gray-500">Risk/Reward Ratio</span>
        <span className={`text-sm font-bold font-mono ${rrRatio >= 1.5 ? 'text-emerald-400' : rrRatio >= 1 ? 'text-amber-400' : 'text-red-400'}`}>
          1 : {rrRatio.toFixed(2)}
        </span>
        <span className="text-xs text-gray-600">
          {rrRatio >= 2 ? '— Excellent' : rrRatio >= 1.5 ? '— Good' : rrRatio >= 1 ? '— Acceptable' : '— Poor'}
        </span>
      </div>

      {/* Fan chart with TP/SL guardrails */}
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 10, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />

            {/* Shaded zones */}
            <ReferenceArea y1={tpPrice} y2={yMax} fill="#10b981" fillOpacity={0.06} />
            <ReferenceArea y1={yMin} y2={slPrice} fill="#ef4444" fillOpacity={0.06} />

            <XAxis dataKey="day" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false}
              label={{ value: 'Days', position: 'insideBottomRight', offset: -5, fill: '#4b5563', fontSize: 10 }} />
            <YAxis domain={[yMin, yMax]} tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }}
              tickLine={false} tickFormatter={(v: number) => fmt(v, dec)} width={62} />

            {/* TP line */}
            <ReferenceLine y={tpPrice} stroke="#10b981" strokeWidth={2} strokeDasharray="6 3"
              label={{ value: `TP ${fmt(tpPrice, dec)}`, fill: '#10b981', fontSize: 10, position: 'insideTopRight' }} />

            {/* Start price line */}
            <ReferenceLine y={startPrice} stroke="#6b7280" strokeDasharray="4 4"
              label={{ value: `Entry ${fmt(startPrice, dec)}`, fill: '#6b7280', fontSize: 9, position: 'insideTopLeft' }} />

            {/* SL line */}
            <ReferenceLine y={slPrice} stroke="#ef4444" strokeWidth={2} strokeDasharray="6 3"
              label={{ value: `SL ${fmt(slPrice, dec)}`, fill: '#ef4444', fontSize: 10, position: 'insideBottomRight' }} />

            <Tooltip contentStyle={TOOLTIP_STYLE}
              formatter={(v: number, name: string) => {
                const labels: Record<string, string> = { p90: 'P90', p75: 'P75', p50: 'Median', p25: 'P25', p10: 'P10' };
                const chg = ((v - startPrice) / startPrice * 100);
                return [`${fmt(v, dec)} (${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%)`, labels[name] ?? name];
              }}
              labelFormatter={(l: number) => `Day ${l}`}
            />

            {/* Fan bands */}
            <Line type="monotone" dataKey="p90" stroke={color} strokeWidth={1} strokeDasharray="3 3" dot={false} opacity={0.3} />
            <Line type="monotone" dataKey="p75" stroke={color} strokeWidth={1.5} dot={false} opacity={0.5} />
            <Line type="monotone" dataKey="p50" stroke={color} strokeWidth={2.5} dot={false} opacity={1} />
            <Line type="monotone" dataKey="p25" stroke={color} strokeWidth={1.5} dot={false} opacity={0.5} />
            <Line type="monotone" dataKey="p10" stroke={color} strokeWidth={1} strokeDasharray="3 3" dot={false} opacity={0.3} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Outcome breakdown */}
      <div className="grid grid-cols-3 gap-2">
        <div className="p-3 rounded-xl bg-emerald-500/8 border border-emerald-500/25 text-center">
          <div className="text-xs text-emerald-400 font-medium mb-1">Hit TP First</div>
          <div className="text-2xl font-bold font-mono text-emerald-400">{tpPct2}%</div>
          <div className="text-xs text-gray-600 mt-1">{guardrail.tpHit} / {guardrail.total} paths</div>
          {guardrail.medianTpDay !== null && (
            <div className="text-xs text-emerald-600 mt-0.5">median day {guardrail.medianTpDay.toFixed(0)}</div>
          )}
        </div>
        <div className="p-3 rounded-xl bg-gray-800/40 border border-gray-700/50 text-center">
          <div className="text-xs text-gray-400 font-medium mb-1">Hit Neither</div>
          <div className="text-2xl font-bold font-mono text-gray-400">{neitherPct}%</div>
          <div className="text-xs text-gray-600 mt-1">{guardrail.neither} / {guardrail.total} paths</div>
          <div className="text-xs text-gray-600 mt-0.5">within {horizon}d</div>
        </div>
        <div className="p-3 rounded-xl bg-red-500/8 border border-red-500/25 text-center">
          <div className="text-xs text-red-400 font-medium mb-1">Hit SL First</div>
          <div className="text-2xl font-bold font-mono text-red-400">{slPct2}%</div>
          <div className="text-xs text-gray-600 mt-1">{guardrail.slHit} / {guardrail.total} paths</div>
          {guardrail.medianSlDay !== null && (
            <div className="text-xs text-red-600 mt-0.5">median day {guardrail.medianSlDay.toFixed(0)}</div>
          )}
        </div>
      </div>

      {/* Expected value bar */}
      <div className="p-3 rounded-xl bg-gray-800/60 border border-gray-700/50">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-gray-400 font-medium">Expected Value (per unit risk)</span>
          {(() => {
            const ev = (parseFloat(tpPct2) / 100) * tpPct - (parseFloat(slPct2) / 100) * slPct;
            return (
              <span className={`text-sm font-bold font-mono ${ev >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {ev >= 0 ? '+' : ''}{ev.toFixed(2)}%
              </span>
            );
          })()}
        </div>
        <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
          <div className="rounded-l-full" style={{ width: `${tpPct2}%`, backgroundColor: '#10b981', opacity: 0.8 }} />
          <div style={{ width: `${neitherPct}%`, backgroundColor: '#374151' }} />
          <div className="rounded-r-full" style={{ width: `${slPct2}%`, backgroundColor: '#ef4444', opacity: 0.8 }} />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-xs text-emerald-500">{tpPct2}% TP</span>
          <span className="text-xs text-gray-600">{neitherPct}% open</span>
          <span className="text-xs text-red-500">{slPct2}% SL</span>
        </div>
      </div>

      <p className="text-xs text-gray-600 leading-relaxed">
        {simCount} GBM paths · {horizon}d horizon · Drag sliders to adjust TP/SL levels ·
        Not financial advice.
      </p>
    </div>
  );
}
