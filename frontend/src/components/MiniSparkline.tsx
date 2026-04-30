/**
 * MiniSparkline — a tiny SVG sparkline showing the three sub-scores
 * as a simple line, rendered inline on each RatingCard.
 */

interface Props {
  sentiment: number;
  orderflow: number;
  economic: number;
  composite: number;
  color: string;
  width?: number;
  height?: number;
}

export function MiniSparkline({ sentiment, orderflow, economic, composite, color, width = 80, height = 28 }: Props) {
  const scores = [sentiment, orderflow, economic, composite];
  const pad = 3;
  const w = width - pad * 2;
  const h = height - pad * 2;

  // Map score 0–5 to y coordinate (inverted — higher score = lower y)
  const toY = (s: number) => pad + h - (s / 5) * h;
  const toX = (i: number) => pad + (i / (scores.length - 1)) * w;

  const points = scores.map((s, i) => `${toX(i).toFixed(1)},${toY(s).toFixed(1)}`).join(' ');

  // Area fill path
  const areaPath = [
    `M ${toX(0).toFixed(1)} ${toY(scores[0]).toFixed(1)}`,
    ...scores.slice(1).map((s, i) => `L ${toX(i + 1).toFixed(1)} ${toY(s).toFixed(1)}`),
    `L ${toX(scores.length - 1).toFixed(1)} ${(pad + h).toFixed(1)}`,
    `L ${toX(0).toFixed(1)} ${(pad + h).toFixed(1)}`,
    'Z',
  ].join(' ');

  const gradId = `spark-${color.replace('#', '')}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} fill="none">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {/* Area fill */}
      <path d={areaPath} fill={`url(#${gradId})`} />
      {/* Line */}
      <polyline
        points={points}
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* End dot (composite score) */}
      <circle
        cx={toX(scores.length - 1).toFixed(1)}
        cy={toY(scores[scores.length - 1]).toFixed(1)}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}
