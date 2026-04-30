export interface WeightProfile {
  asset_class: string;
  sub_category: string | null;
  sentiment_pct: number;
  orderflow_pct: number;
  economic_pct: number;
}

export interface RatingRecord {
  record_id: string;
  security_id: string;
  asset_class: string;
  composite_score: number;
  rating: 'Strong Buy' | 'Buy' | 'Neutral' | 'Sell' | 'Strong Sell';
  sentiment_score: number;
  orderflow_score: number;
  economic_score: number;
  weight_profile: WeightProfile;
  data_deficient: boolean;
  computed_at: string;
}

export interface HealthStatus {
  last_successful_cycle_at: string | null;
  securities_rated: number;
  status: 'ok' | 'degraded';
}

export type AssetClass = 'FX' | 'Equity' | 'Index' | 'Commodity' | 'Crypto';
