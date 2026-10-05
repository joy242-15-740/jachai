"use client";

import { useEffect, useState } from "react";
import { PageTitle, Panel, SourceNote } from "@/components/ui";
import { EvasionToggle } from "@/components/EvasionToggle";
import { getData, pct, type Source } from "@/lib/api";

interface FairnessRow {
  group: string;
  honest_shops: number;
  false_alarms: number;
  false_alarm_rate: number | null;
  small_sample: boolean;
}

interface Fairness {
  evaluated_on: string;
  overall: FairnessRow;
  by_area_type: FairnessRow[];
  by_size_tier: FairnessRow[];
  by_category: FairnessRow[];
  note: string;
}

function Slice({ title, rows }: { title: string; rows: FairnessRow[] }) {
  return (
    <Panel title={title}>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.group}>
            <div className="mb-1 flex items-center justify-between gap-4 text-sm">
              <span className="capitalize">{row.group.replaceAll("_", " ")}</span>
              <span className="tabular-nums text-muted">
                {row.false_alarm_rate == null ? "—" : pct(row.false_alarm_rate)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-line">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${Math.max(1, (row.false_alarm_rate ?? 0) * 100)}%` }}
              />
            </div>
            <div className="mt-1 text-[11px] text-muted">
              {row.false_alarms} false alerts among {row.honest_shops} honest shops
              {row.small_sample && " · small sample"}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export default function TrustPage() {
  const [fairness, setFairness] = useState<Fairness | null>(null);
  const [source, setSource] = useState<Source | null>(null);

  useEffect(() => {
    getData<Fairness>("/fairness", "fairness.json").then((result) => {
      setFairness(result.data);
      setSource(result.source);
    });
  }, []);

  return (
    <>
      <PageTitle
        title="Trust center"
        subtitle="What the evidence supports, what remains uncertain, and where a human must stay in control."
      />
      <SourceNote source={source} />

      <div className="mb-5 grid gap-4 md:grid-cols-3">
        <div className="glass-panel rounded-2xl border-l-2 border-l-review p-5">
          <div className="eyebrow text-review">Validation · 3 seeds · criteria partly met</div>
          <h2 className="mt-2 font-semibold">Current fusion · multi-seed</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            Evasion and ring criteria met; normal-world criterion not met (PR-AUC 0.774 vs rules
            0.899). Matched-budget, evasion and label-source evidence is in reports/.
          </p>
        </div>
        <div className="glass-panel rounded-2xl border-l-2 border-l-review p-5">
          <div className="eyebrow text-review">Final test · single access</div>
          <h2 className="mt-2 font-semibold">Rules were stronger</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            Jachai PR-AUC 0.584 vs rules 0.843. No tuning follows this result.
          </p>
        </div>
        <div className="glass-panel rounded-2xl border-l-2 border-l-high p-5">
          <div className="eyebrow text-high">Not available</div>
          <h2 className="mt-2 font-semibold">Real-world performance</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            No deployment data. Synthetic results prove the workflow, not real accuracy or impact.
          </p>
        </div>
      </div>

      {fairness && (
        <>
          <Panel title="Validation false-alert snapshot">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="text-4xl font-semibold tracking-tight tabular-nums">
                  {fairness.overall.false_alarm_rate == null ? "—" : pct(fairness.overall.false_alarm_rate)}
                </div>
                <p className="mt-1 text-sm text-muted">
                  {fairness.overall.false_alarms} false alerts among {fairness.overall.honest_shops} honest shops
                </p>
              </div>
              <p className="max-w-xl text-xs leading-5 text-muted">
                {fairness.evaluated_on}. Synthetic groups and small samples cannot establish real-world fairness.
              </p>
            </div>
          </Panel>
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Slice title="By area type" rows={fairness.by_area_type} />
            <Slice title="By shop size" rows={fairness.by_size_tier} />
            <Slice title="By category" rows={fairness.by_category} />
          </div>
        </>
      )}

      <div className="mt-4">
        <EvasionToggle />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Circularity note">
          <p className="text-sm leading-6 text-muted">
            The synthetic patterns and fixed rules share the same typology definitions. That makes
            the normal synthetic world unusually friendly to rules. Evasion and ring checks reduce,
            but do not remove, this circularity.
          </p>
        </Panel>
        <Panel title="Human control">
          <p className="text-sm leading-6 text-muted">
            A score only changes review priority. Merchant communication is non-accusatory, decisions
            need a written reason, and no restriction or conversion happens automatically.
          </p>
        </Panel>
      </div>
    </>
  );
}
