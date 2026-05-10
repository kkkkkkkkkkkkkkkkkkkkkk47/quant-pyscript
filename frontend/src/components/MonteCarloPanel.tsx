/**
 * MonteCarloPanel — Monte Carlo price path simulation using real market prices.
 *
 * - Fetches the real current price from /price/{security_id}
 * - Uses composite score as drift, sub-score spread as volatility
 * - Runs N Geometric Brownian Motion paths in the browser
 * - Shows a fan chart with P10/P25/P50/P75/P90 bands
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
} from 'recharts';
import type { RatingRecord } from '../types';
import { RATING_COLORS } from '../utils/formatters';
import { fetchPrice } from '../api/client';

interface Props {
  record: RatingRecord;
}

// ─── GBM engine ──────────────────────────────────────────────────────────────

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

function pct(arr: number[], p: number): number {
  const s = [...arr].sort((a, b) => a - b);
  const i = (p / 100) * (s.length - 1);
  const lo = Math.floor(i), hi = Math.ceil(i);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

// ─── Decimal precision per asset class ───────────────────────────────────────

function pricePrecision(assetClass: string, price: number): number {
  if (assetClass === 'Crypto') return price > 1000 ? 2 : 4;
  if (assetClass === 'FX') return 4;
  return 2;
}

function fmtPrice(price: number, decimals: number): string {
  return price.toFixed(decimals);
}

// ─── Chart data ───────────────────────────────────────────────────────────────

interface ChartPoint {
  day: number;
  p10: number; p25: number; p50: number; p75: number; p90: number; mean: number;
}

function buildChart(paths: number[][], steps: number): ChartPoint[] {
  return Array.from({ length: steps + 1 }, (_, t) => {
    const vals = paths.map((p) => p[t]);
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    return {
      day: t,
      p10: pct(vals, 10), p25: pct(vals, 25), p50: pct(vals, 50),
      p75: pct(vals, 75), p90: pct(vals, 90), mean,
    };
  });
}

// ─── Component ────────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937', border: '1px solid #374151',
  borderRadius: '8px', color: '#f9fafb', fontSize: '11px', padding: '8px 12px',
};

export function MonteCarloPanel({ record }: Props) {
  const [simCount, setSimCount] = useState(50);
  const [horizon, setHorizon] = useState(30);
  const [realPrice, setRealPrice] = useState<number | null>(null);
  const [priceLoading, setPriceLoading] = useState(true);
  const [priceSource, setPriceSource] = useState<string>('');

  // Fetch real market price
  useEffect(() => {
    setPriceLoading(true);
    setRealPrice(null);
    fetchPrice(record.security_id)
      .then((p) => {
        setRealPrice(p);
        setPriceSource(p !== null ? 'live' : 'normalised');
      })
      .catch(() => setPriceSource('normalised'))
      .finally(() => setPriceLoading(false));
  }, [record.security_id]);

  const startPrice = realPrice ?? 100;
  const decimals = pricePrecision(record.asset_class, startPrice);
  const color = RATING_COLORS[record.rating]?.hex ?? '#10b981';

  // Derive drift and volatility from scores
  const drift = ((record.composite_score - 2.5) / 2.5) * 0.40;
  const scores = [record.sentiment_score, record.orderflow_score, record.economic_score];
  const scoreMean = scores.reduce((a, b) => a + b, 0) / 3;
  const spread = Math.sqrt(scores.reduce((a, b) => a + (b - scoreMean) ** 2, 0) / 3);
  const volatility = 0.10 + (spread / 2.5) * 0.50;

  const { chartData, finalStats } = useMemo(() => {
    const paths = runGBM(startPrice, drift, volatility, horizon, simCount);
    const cd = buildChart(paths, horizon);
    const finals = paths.map((p) => p[p.length - 1]);
    return {
      chartData: cd,
      finalStats: {
        p10: pct(finals, 10), p50: pct(finals, 50), p90: pct(finals, 90),
        bullish: finals.filter((v) => v > startPrice).length,
        bearish: finals.filter((v) => v <= startPrice).length,
      },
    };
  }, [startPrice, drift, volatility, horizon, simCount]);

  const driftPct = (drift * 100).toFixed(1);
  const volPct = (volatility * 100).toFixed(1);
  const bullPct = ((finalStats.bullish / simCount) * 100).toFixed(0);
  const bearPct = ((finalStats.bearish / simCount) * 100).toFixed(0);

  // Y-axis formatter — show real price values
  const yFmt = (v: number) => fmtPrice(v, decimals);

  // Tooltip formatter
  const ttFmt = (value: number, name: string) => {
    const labels: Record<string, string> = {
      p90: 'P90', p75: 'P75', p50: 'Median', mean: 'Mean', p25: 'P25', p10: 'P10',
    };
    const chg = ((value - startPrice) / startPrice * 100);
    return [`${fmtPrice(value, decimals)} (${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%)`, labels[name] ?? name];
  };

  return (
    <div className="flex flex-col gap-4">

      {/* Current price badge */}
      <div className="flex items-center gap-3 flex-wrap">
        {priceLoading ? (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <svg className="animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
              <path d="M21 3v5h-5"/>
            </svg>
            Fetching live price...
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="px-3 py-1.5 rounded-lg bg-gray-800/60 border border-gray-700/50 flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full ${realPrice !== null ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              <span className="text-xs text-gray-400">
                {realPrice !== null ? 'Live price:' : 'Normalised:'}
              </span>
              <span className="text-sm font-bold font-mono text-white">
                {fmtPrice(startPrice, decimals)}
              </span>
              {realPrice !== null && (
                <span className="text-xs text-gray-600">{record.security_id}</span>
              )}
            </div>
            {realPrice === null && (
              <span className="text-xs text-amber-400">Live price unavailable — using 100 as base</span>
            )}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Paths</span>
          {[20, 50, 100, 200].map((n) => (
            <button key={n} onClick={() => setSimCount(n)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                simCount === n
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                  : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-gray-300'
              }`}>{n}</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Horizon</span>
          {[10, 30, 60, 90].map((d) => (
            <button key={d} onClick={() => setHorizon(d)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-all ${
                horizon === d
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                  : 'bg-gray-800 text-gray-500 border border-gray-700 hover:text-gray-300'
              }`}>{d}d</button>
          ))}
        </div>
      </div>

      {/* Drift / Vol params */}
      <div className="grid grid-cols-2 gap-2">
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
          <div className="text-xs text-gray-500 mb-1">Annualised Drift</div>
          <div className={`text-lg font-bold font-mono ${parseFloat(driftPct) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {parseFloat(driftPct) >= 0 ? '+' : ''}{driftPct}%
          </div>
          <div className="text-xs text-gray-600 mt-0.5">composite {record.composite_score.toFixed(2)}/5.00</div>
        </div>
        <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
          <div className="text-xs text-gray-500 mb-1">Annualised Volatility</div>
          <div className="text-lg font-bold font-mono text-amber-400">{volPct}%</div>
          <div className="text-xs text-gray-600 mt-0.5">from sub-score spread</div>
        </div>
      </div>

      {/* Fan chart */}
      <div style={{ width: '100%', height: 230 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="day" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false}
              label={{ value: 'Days', position: 'insideBottomRight', offset: -5, fill: '#4b5563', fontSize: 10 }} />
            <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false}
              tickFormatter={yFmt} width={60} />
            <ReferenceLine y={startPrice} stroke="#374151" strokeDasharray="4 4"
              label={{ value: `Start ${fmtPrice(startPrice, decimals)}`, fill: '#4b5563', fontSize: 9, position: 'insideTopLeft' }} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={ttFmt} labelFormatter={(l: number) => `Day ${l}`} />
            <Line type="monotone" dataKey="p90" stroke={color} strokeWidth={1} strokeDasharray="3 3" dot={false} opacity={0.35} />
            <Line type="monotone" dataKey="p75" stroke={color} strokeWidth={1.5} dot={false} opacity={0.55} />
            <Line type="monotone" dataKey="p50" stroke={color} strokeWidth={2.5} dot={false} opacity={1} />
            <Line type="monotone" dataKey="mean" stroke="#f9fafb" strokeWidth={1.5} strokeDasharray="5 3" dot={false} opacity={0.45} />
            <Line type="monotone" dataKey="p25" stroke={color} strokeWidth={1.5} dot={false} opacity={0.55} />
            <Line type="monotone" dataKey="p10" stroke={color} strokeWidth={1} strokeDasharray="3 3" dot={false} opacity={0.35} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 flex-wrap text-xs text-gray-500">
        {[
          { label: 'Median (P50)', opacity: 1, width: 2.5 },
          { label: 'P25–P75', opacity: 0.55, width: 1.5 },
          { label: 'P10–P90', opacity: 0.35, width: 1 },
        ].map(({ label, opacity }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-6 h-0.5 rounded" style={{ backgroundColor: color, opacity }} />
            <span>{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <div className="w-6 h-0.5 rounded bg-white opacity-45" />
          <span>Mean</span>
        </div>
      </div>

      {/* Outcome stats — real prices */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'P10 (bear)', val: finalStats.p10 },
          { label: 'Median',    val: finalStats.p50 },
          { label: 'P90 (bull)', val: finalStats.p90 },
        ].map(({ label, val }) => {
          const chgPct = ((val - startPrice) / startPrice * 100);
          return (
            <div key={label} className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50 text-center">
              <div className="text-xs text-gray-500 mb-1">{label}</div>
              <div className="text-sm font-bold font-mono text-white">{fmtPrice(val, decimals)}</div>
              <div className={`text-xs font-mono mt-0.5 ${chgPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {chgPct >= 0 ? '+' : ''}{chgPct.toFixed(2)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Bull/Bear bar */}
      <div className="p-3 rounded-lg bg-gray-800/60 border border-gray-700/50">
        <div className="text-xs text-gray-500 mb-2">{simCount} paths · {horizon}d horizon</div>
        <div className="flex h-4 rounded-full overflow-hidden gap-0.5">
          <div className="flex items-center justify-center text-xs font-bold text-emerald-100 rounded-l-full"
            style={{ width: `${bullPct}%`, backgroundColor: '#10b981' }}>
            {parseInt(bullPct) > 15 ? `${bullPct}%` : ''}
          </div>
          <div className="flex items-center justify-center text-xs font-bold text-red-100 rounded-r-full"
            style={{ width: `${bearPct}%`, backgroundColor: '#ef4444' }}>
            {parseInt(bearPct) > 15 ? `${bearPct}%` : ''}
          </div>
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-xs text-emerald-400">{bullPct}% above {fmtPrice(startPrice, decimals)}</span>
          <span className="text-xs text-red-400">{bearPct}% below {fmtPrice(startPrice, decimals)}</span>
        </div>
      </div>

      <p className="text-xs text-gray-600 leading-relaxed">
        Geometric Brownian Motion · {priceSource === 'live' ? 'Live price from Twelve Data' : 'Normalised base (live price unavailable)'} ·
        Drift from composite score · Volatility from sub-score dispersion · Not financial advice.
      </p>
    </div>
  );
}
