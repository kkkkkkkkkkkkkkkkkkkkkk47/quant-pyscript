import { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { fetchHistory } from '../api/client';
import type { RatingRecord } from '../types';

interface ChartPoint {
  time: string;
  composite: number;
  sentiment: number;
  orderflow: number;
  economic: number;
}

interface Props {
  securityId: string;
}

const LINE_COLORS = {
  composite: '#10b981',
  sentiment: '#60a5fa',
  orderflow: '#a78bfa',
  economic: '#fbbf24',
};

const LABELS: Record<string, string> = {
  composite: 'Composite',
  sentiment: 'Sentiment',
  orderflow: 'Order Flow',
  economic: 'Economic',
};

const TOOLTIP_STYLE = {
  backgroundColor: '#1f2937',
  border: '1px solid #374151',
  borderRadius: '8px',
  color: '#f9fafb',
  fontSize: '12px',
  padding: '8px 12px',
};

export function HistoryChart({ securityId }: Props) {
  const [data, setData] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchHistory(securityId, 7)
      .then((records: RatingRecord[]) => {
        const sorted = [...records].sort(
          (a, b) => new Date(a.computed_at).getTime() - new Date(b.computed_at).getTime(),
        );
        setData(
          sorted.map((r) => ({
            time: new Date(r.computed_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            }),
            composite: parseFloat(r.composite_score.toFixed(2)),
            sentiment: parseFloat(r.sentiment_score.toFixed(2)),
            orderflow: parseFloat(r.orderflow_score.toFixed(2)),
            economic: parseFloat(r.economic_score.toFixed(2)),
          })),
        );
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : 'Failed to load history');
      })
      .finally(() => setLoading(false));
  }, [securityId]);

  if (loading) {
    return (
      <div className="h-56 flex items-center justify-center">
        <div className="flex items-center gap-2 text-gray-500 text-sm">
          <svg className="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
            <path d="M21 3v5h-5" />
          </svg>
          Loading history...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-56 flex items-center justify-center text-red-400 text-sm">
        {error}
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="h-56 flex flex-col items-center justify-center gap-2 text-gray-500">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-40">
          <path d="M3 3v18h18" />
          <path d="m19 9-5 5-4-4-3 3" />
        </svg>
        <span className="text-sm">No history available yet</span>
        <span className="text-xs text-gray-600">Run more rating cycles to build history</span>
      </div>
    );
  }

  // Single data point — show a bar chart of the current scores instead of a line chart
  if (data.length === 1) {
    const point = data[0];
    const barData = [
      { name: 'Composite', value: point.composite, color: LINE_COLORS.composite },
      { name: 'Sentiment', value: point.sentiment, color: LINE_COLORS.sentiment },
      { name: 'Order Flow', value: point.orderflow, color: LINE_COLORS.orderflow },
      { name: 'Economic', value: point.economic, color: LINE_COLORS.economic },
    ];

    return (
      <div>
        <p className="text-xs text-gray-500 mb-3 text-center">
          Single snapshot — {point.time}
        </p>
        <div style={{ width: '100%', height: 180 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={{ stroke: '#1f2937' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 5]}
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={{ stroke: '#1f2937' }}
                tickLine={false}
                ticks={[0, 1, 2, 3, 4, 5]}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value: number) => [`${value.toFixed(2)} / 5.00`, 'Score']}
                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {barData.map((entry, index) => (
                  <Cell key={index} fill={entry.color} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // Multiple points — line chart
  return (
    <div style={{ width: '100%', height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: -10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="time"
            tick={{ fill: '#6b7280', fontSize: 10, fontFamily: 'Inter, sans-serif' }}
            axisLine={{ stroke: '#1f2937' }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 5]}
            ticks={[0, 1, 2, 3, 4, 5]}
            tick={{ fill: '#6b7280', fontSize: 11 }}
            axisLine={{ stroke: '#1f2937' }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: number, name: string) => [
              `${value.toFixed(2)} / 5.00`,
              LABELS[name] ?? name,
            ]}
          />
          <Legend
            wrapperStyle={{ fontSize: '11px', color: '#9ca3af', paddingTop: '8px' }}
            formatter={(value: string) => LABELS[value] ?? value}
          />
          <Line type="monotone" dataKey="composite" stroke={LINE_COLORS.composite} strokeWidth={2.5} dot={{ r: 3, fill: LINE_COLORS.composite }} activeDot={{ r: 5 }} />
          <Line type="monotone" dataKey="sentiment" stroke={LINE_COLORS.sentiment} strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
          <Line type="monotone" dataKey="orderflow" stroke={LINE_COLORS.orderflow} strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
          <Line type="monotone" dataKey="economic" stroke={LINE_COLORS.economic} strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
