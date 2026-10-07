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
  brief: {
    analyst_note: string;
    analyst_note_source: "template" | "llm";
    merchant_notice_bn: string;
    merchant_notice_source: "template";
    llm_output_rejected: string[] | null;
  };
  recommendation?: {
    action: "clear" | "monitor" | "educate" | "convert" | "restrict" | "escalate";
    en: string;
    bn: string;
    estimated_cash_out_demand_30d: number;
    convert_eligible: boolean;
    convert_offer: "recommended" | "secondary" | "none";
    note: string;
  };
  decisions: Decision[];
}

export interface PolicyResult {
  policy: "A" | "B" | "C" | "D" | "E";
  name: string;
  days: number;
  misuse_taka_total: number;
  misuse_taka_stopped: number;
  misuse_taka_rerouted: number;
  misuse_taka_still_flowing: number;
  fees_recaptured: number;
  honest_shops_restricted: number;
  blocked_genuine_sales: number;
  blocked_sales_at_misuse_shops: number;
  analyst_alerts_per_day: number;
  agent_leads: number;
  agents_signed: number;
  genuine_commerce_share: number;
  fee_rate: number;
}

export interface SimulateResponse {
  params: Record<string, number | number[] | string[] | null> & {
    misuse_scale: number;
    analyst_capacity_per_day: number;
    limit_level: number;
    displaced_to_agents_share: number;
  };
  replay: { seed: number; days: number };
  results: PolicyResult[];
  note: string;
}

export interface OverviewDay {
  day: string;
  payments: number;
  turnover: number;
  flagged: number;
  flagged_turnover: number;
}

export interface Overview {
  as_of: string;
  window_days: number;
  window: { start: string; end: string; previous_start: string };
  volume: {
    turnover_7d: number;
    turnover_previous_7d: number;
    delta_vs_previous: number | null;
    payments_7d: number;
    flagged_7d: number;
    flagged_turnover_7d: number;
  };
  daily: OverviewDay[];
  shops: {
    monitored: number;
    high: number;
    review: number;
    low: number;
    alerts: number;
    ring_linked: number;
    ring_linked_alerts: number;
    with_linking_payers: number;
    mean_risk: number;
  };
  recent_flagged_payments: {
    payment_id: string;
    shop_id: string;
    category: string;
    ts: string;
    amount: number;
    score: number;
    band: Band;
    status: string;
  }[];
  model: {
    payment_model_fingerprint: string;
    payment_threshold: number;
    fusion_weights: Record<string, number>;
    evidence_timestamp: string;
  };
  note: string;
}

export interface SimulateGrid {
  axes: { misuse_scale: number[]; analyst_capacity_per_day: number[]; limit_level: number[] };
  runs: SimulateResponse[];
}
