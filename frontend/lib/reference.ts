// Reference-world walkthrough examples (frontend/public/demo/reference/, made by
// `make demo-reference`). Static, read-only, and labelled with the world they come from.

import type { CaseDetail } from "@/lib/types";

export type ExampleKey = "ring" | "honest_lookalike" | "cash_desk" | "convert_lead";

export interface ReferenceManifest {
  world: string;
  as_of: string;
  selection: string;
  agent_cash_out_fee_rate: number;
  examples: Record<
    ExampleKey,
    {
      shop_id: string;
      why_chosen: string;
      band: string;
      recommended_action: string;
      agents_in_zone: number;
      nearest_agent_km: number | null;
    }
  >;
}

export async function loadManifest(): Promise<ReferenceManifest> {
  const r = await fetch("/demo/reference/manifest.json");
  if (!r.ok) throw new Error("reference examples are missing: run `make demo-reference`");
  return (await r.json()) as ReferenceManifest;
}

export async function loadExample(key: string): Promise<CaseDetail> {
  const r = await fetch(`/demo/reference/${key}.json`);
  if (!r.ok) throw new Error(`no reference example "${key}"`);
  return (await r.json()) as CaseDetail;
}
