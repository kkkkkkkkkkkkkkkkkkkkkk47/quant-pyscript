import type { RatingRecord } from '../types';
import { RATING_COLORS, timeAgo, formatPct } from '../utils/formatters';
import { RatingBadge } from './RatingBadge';
import { ScoreBar } from './ScoreBar';
import { SubScoreRow } from './SubScoreRow';
import { MiniSparkline } from './MiniSparkline';
import { AlertTriangleIcon, BrainIcon, ChartBarIcon, GlobeIcon } from './icons';

interface Props {
  record: RatingRecord;
  onClick: (record: RatingRecord) => void;
}

export function RatingCard({ record, onClick }: Props) {
  const colors = RATING_COLORS[record.rating] ?? RATING_COLORS['Neutral'];

  return (
    <div
      onClick={() => onClick(record)}
      className="group relative flex flex-col gap-3 p-4 rounded-xl cursor-pointer
        bg-[#111827] border border-gray-800 hover:border-gray-600
        transition-all duration-200 hover:shadow-xl hover:shadow-black/40
        hover:-translate-y-0.5"
      style={{ borderLeft: `4px solid ${colors.hex}` }}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-lg font-bold text-white truncate leading-tight">
            {record.security_id}
          </h3>
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            <span className="text-xs px-2 py-0.5 rounded bg-gray-700/60 text-gray-400 font-medium">
              {record.asset_class}
            </span>
            {record.weight_profile.sub_category && (
              <span className="text-xs px-2 py-0.5 rounded bg-gray-700/40 text-gray-500">
                {record.weight_profile.sub_category}
              </span>
            )}
          </div>
        </div>
        <RatingBadge rating={record.rating} size="sm" />
      </div>

      {/* Composite score bar */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-gray-500 font-medium">Composite Score</span>
        </div>
        <ScoreBar score={record.composite_score} showLabel={true} height={8} />
      </div>

      {/* Sub-scores */}
      <div className="flex flex-col gap-2">
        <SubScoreRow
          label="Sentiment"
          score={record.sentiment_score}
          icon={<BrainIcon size={14} />}
          color="#60a5fa"
        />
        <SubScoreRow
          label="Order Flow"
          score={record.orderflow_score}
          icon={<ChartBarIcon size={14} />}
          color="#a78bfa"
        />
        <SubScoreRow
          label="Economic"
          score={record.economic_score}
          icon={<GlobeIcon size={14} />}
          color="#fbbf24"
        />
      </div>

      {/* Weight pills */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-gray-600">Weights:</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
          S {formatPct(record.weight_profile.sentiment_pct)}
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
          O {formatPct(record.weight_profile.orderflow_pct)}
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
          E {formatPct(record.weight_profile.economic_pct)}
        </span>
      </div>

      {/* Data deficient warning */}
      {record.data_deficient && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <AlertTriangleIcon size={14} className="text-amber-400 flex-shrink-0" />
          <span className="text-xs text-amber-400">Data deficient — scores may be unreliable</span>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-gray-800/60">
        <span className="text-xs text-gray-600">
          {timeAgo(record.computed_at)}
        </span>
        <div className="flex items-center gap-2">
          <MiniSparkline
            sentiment={record.sentiment_score}
            orderflow={record.orderflow_score}
            economic={record.economic_score}
            composite={record.composite_score}
            color={colors.hex}
            width={72}
            height={24}
          />
          <span className="text-xs text-gray-600 group-hover:text-gray-400 transition-colors">
            →
          </span>
        </div>
      </div>
    </div>
  );
}
