"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CaseView } from "@/components/CaseView";
import { taka } from "@/lib/api";
import { type ExampleKey, loadExample, loadManifest, type ReferenceManifest } from "@/lib/reference";
import type { CaseDetail } from "@/lib/types";

export default function ExamplePage() {
  const { key } = useParams<{ key: ExampleKey }>();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [manifest, setManifest] = useState<ReferenceManifest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([loadExample(key), loadManifest()])
      .then(([d, m]) => {
        setData(d);
        setManifest(m);
      })
      .catch((e: Error) => setError(e.message));
  }, [key]);

  if (error) return <p className="text-high">{error}</p>;
  if (!data || !manifest) return <p className="text-muted">Loading example…</p>;
  const ex = manifest.examples[key];
  const demand = data.recommendation?.estimated_cash_out_demand_30d ?? 0;
  const banner = (
    <div className="mb-4 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm">
      <div className="font-medium">Reference-world example · read-only</div>
      <div className="mt-1 text-muted">
        From the {manifest.world}, as of {manifest.as_of}. Why this shop: {ex.why_chosen}{" "}
        ({manifest.selection}.)
      </div>
      {key === "convert_lead" && (
        <div className="mt-2">
          Licensed agents nearby: <strong>{ex.agents_in_zone}</strong> in the same zone, nearest about{" "}
          <strong>{ex.nearest_agent_km ?? "—"} km</strong> away. Agent cash-out fees that went around them,
          estimated from this shop&apos;s flagged payments: about{" "}
          <strong>{taka(demand * manifest.agent_cash_out_fee_rate)}</strong> in 30 days (fee rate Tk{" "}
          {(manifest.agent_cash_out_fee_rate * 1000).toFixed(2)} per Tk 1,000).
        </div>
      )}
    </div>
  );
  return <CaseView id={ex.shop_id} data={data} source={null} banner={banner} readOnly />;
}
