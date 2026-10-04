// Shapes returned by the Jachai API (backend/app). Kept small on purpose.

export type Band = "low" | "review" | "high";

export interface Reason {
  code: string;
  en: string;
  bn: string;
  weight: number;
}

export interface CaseSummary {
  case_id: string;
  shop_id: string;
  category: string;
  size_tier: string;
  area_type: string;
  zone_id: string;
  risk: number;
  band: Band;
  status: string;
  top_reason: Reason | null;
}

export interface CasesResponse {
  as_of: string;
  count: number;
  cases: CaseSummary[];
}

export interface Decision {
  id: number;
  case_id: string;
  decision: string;
  reason: string;
  analyst: string;
  risk: number;
  band: string;
  created_at: string;
}

export interface TimelineDay {
  day: string;
  risk: number;
  band: Band;
  payments: number;
  turnover: number;
  flagged: number;
}

export interface CaseDetail {
  case_id: string;
  shop: Record<string, string | number>;
  scores: {
    as_of: string;
    risk: number;
    band: Band;
    status: string;
    components: Record<string, number | null>;
    expected_daily_turnover: number | null;
  };
  reasons: Reason[];
  riskiest_payments: { payment_id: string; ts: string; amount: number; score: number; reasons: Reason[] }[];
  neighbourhood: {
    community_size: number | null;
    ring_flag: boolean;
    linking_payers: number | null;
    linked_shops: { shop_id: string; shared_payers: number; category: string; band: Band; risk: number }[];
  };
  timeline: TimelineDay[];
  decisions: Decision[];
}
