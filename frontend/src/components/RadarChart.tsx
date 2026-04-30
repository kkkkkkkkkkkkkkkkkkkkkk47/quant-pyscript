import {
  RadarChart as RechartsRadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import type { RatingRecord } from '../types';
import { RATING_COLORS } from '../utils/formatters';

interface Props {
  record: RatingRecord;
}

export function RadarChartPanel({ record }: Props) {
  const color = RATING_COLORS[record.rating]?.hex ?? '#10b981';

  const data = [
    { subject: 'Sentiment', value: parseFloat(record.sentiment_score.toFixed(2)), fullMark: 5 },
    { subject: 'Order Flow', value: parseFloat(record.orderflow_score.toFixed(2)), fullMark: 5 },
    { subject: 'Economic', value: parseFloat(record.economic_score.toFixed(2)), fullMark: 5 },
  ];

  return (
    /*
     * ResponsiveContainer MUST have a parent with an explicit pixel height.
     * We set height on the wrapper div and let ResponsiveContainer fill it.
     * width="99%" avoids a known Recharts resize-loop bug.
     */
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer width="99%" height="100%">
        <RechartsRadarChart
          data={data}
          cx="50%"
          cy="50%"
          outerRadius="65%"
          margin={{ top: 10, right: 30, bottom: 10, left: 30 }}
        >
          <PolarGrid stroke="#374151" strokeDasharray="3 3" />
          <PolarAngleAxis
            dataKey="subject"
            tick={{ fill: '#9ca3af', fontSize: 12, fontFamily: 'Inter, sans-serif' }}
            tickLine={false}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 5]}
            tick={{ fill: '#4b5563', fontSize: 10 }}
            tickCount={4}
            axisLine={false}
          />
          <Radar
            name="Score"
            dataKey="value"
            stroke={color}
            fill={color}
            fillOpacity={0.25}
            strokeWidth={2}
            dot={{ fill: color, r: 4, strokeWidth: 0 }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
              color: '#f9fafb',
              fontSize: '12px',
              padding: '8px 12px',
            }}
            formatter={(value: number) => [`${value.toFixed(2)} / 5.00`, 'Score']}
          />
        </RechartsRadarChart>
      </ResponsiveContainer>
    </div>
  );
}
