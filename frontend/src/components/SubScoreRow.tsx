interface Props {
  label: string;
  score: number;
  icon: React.ReactNode;
  color: string;
}

export function SubScoreRow({ label, score, icon, color }: Props) {
  const pct = Math.min(Math.max((score / 5) * 100, 0), 100);

  return (
    <div className="flex items-center gap-2">
      <span className="flex-shrink-0" style={{ color }}>
        {icon}
      </span>
      <span className="text-xs text-gray-400 w-20 flex-shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-gray-700 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-mono text-gray-300 w-8 text-right flex-shrink-0">
        {score.toFixed(1)}
      </span>
    </div>
  );
}
