import { RATING_COLORS } from '../utils/formatters';
import type { RatingRecord } from '../types';

interface Props {
  rating: RatingRecord['rating'];
  size?: 'sm' | 'md' | 'lg';
}

export function RatingBadge({ rating, size = 'md' }: Props) {
  const colors = RATING_COLORS[rating] ?? RATING_COLORS['Neutral'];

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-3 py-1',
    lg: 'text-base px-4 py-1.5',
  };

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full ${sizeClasses[size]}`}
      style={{
        backgroundColor: `${colors.hex}20`,
        color: colors.hex,
        border: `1px solid ${colors.hex}40`,
      }}
    >
      {rating}
    </span>
  );
}
