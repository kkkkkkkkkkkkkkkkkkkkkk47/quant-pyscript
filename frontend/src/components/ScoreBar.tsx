interface Props {
  score: number; // 0–5
  showLabel?: boolean;
  height?: number;
}

export function ScoreBar({ score, showLabel = true, height = 8 }: Props) {
  const pct = Math.min(Math.max((score / 5) * 100, 0), 100);
  const markerSize = height + 8;

  return (
    <div className="w-full">
      {/* Extra vertical padding so the marker doesn't clip */}
      <div style={{ paddingTop: markerSize / 2, paddingBottom: markerSize / 2 }}>
        <div
          className="relative w-full rounded-full"
          style={{
            height: `${height}px`,
            background: 'linear-gradient(to right, #ef4444 0%, #6b7280 50%, #10b981 100%)',
          }}
        >
          {/* Marker dot */}
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 rounded-full border-2 border-white"
            style={{
              left: `${pct}%`,
              width: `${markerSize}px`,
              height: `${markerSize}px`,
              backgroundColor: '#fff',
              boxShadow: '0 0 0 2px rgba(0,0,0,0.4), 0 2px 6px rgba(0,0,0,0.6)',
              zIndex: 1,
            }}
          />
        </div>
      </div>
      {showLabel && (
        <div className="flex justify-between -mt-1">
          <span className="text-xs text-gray-600">0</span>
          <span className="text-xs font-semibold text-white tabular-nums">{score.toFixed(2)}</span>
          <span className="text-xs text-gray-600">5</span>
        </div>
      )}
    </div>
  );
}
