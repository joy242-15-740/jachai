"use client";

import { useEffect, useMemo, useState } from "react";
import { getData, postData, type Source } from "@/lib/api";
import type { CasesResponse, PolicyResult, SimulateGrid, SimulateResponse } from "@/lib/types";

const GROUPS: Record<string, { label: string; codes: string[]; tone: string }> = {
  payment: {
    label: "Payment evidence",
    codes: ["PAYMENT_RISK", "FLAGGED_SHARE", "RULES_FLAGS"],
    tone: "from-sky-400 to-cyan-300",
  },
  shop: {
    label: "Shop evidence",
    codes: ["TURNOVER_IMPLAUSIBLE", "PEER_ANOMALY"],
    tone: "from-violet-400 to-fuchsia-300",
  },
  network: {
    label: "Network evidence",
    codes: ["LINKING_PAYERS", "RING"],
    tone: "from-emerald-400 to-teal-300",
  },
};

const POLICY_NAME: Record<PolicyResult["policy"], string> = {
  A: "Do nothing",
  B: "Blanket limit",
  C: "Rules only",
  D: "Jachai targeted",
  E: "Jachai + convert",
};

async function policies(): Promise<PolicyResult[]> {
  try {
    return (await postData<SimulateResponse>("/simulate", {})).results;
  } catch {
    const response = await fetch("/demo/simulate-grid.json");
    if (!response.ok) return [];
    const grid = (await response.json()) as SimulateGrid;
    const preferred = grid.runs.find(
      (run) =>
        run.params.misuse_scale === 1 &&
        run.params.analyst_capacity_per_day === 20 &&
        run.params.limit_level === 100000,
    );
    return (preferred ?? grid.runs[0])?.results ?? [];
  }
}

function Bar({ width, tone, delay = 0 }: { width: number; tone: string; delay?: number }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-line/70">
      <div
        className={`metric-bar h-full rounded-full bg-gradient-to-r ${tone}`}
        style={{ width: `${Math.max(width, 1)}%`, animationDelay: `${delay}ms` }}
      />
    </div>
  );
}

function LoadingBars() {
  return (
    <div className="space-y-4 py-2">
      {["w-4/5", "w-2/3", "w-1/2"].map((width) => (
        <div key={width} className="space-y-2">
          <div className={`shimmer h-3 rounded-full ${width}`} />
          <div className="shimmer h-2 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export function HomeInfographics() {
  const [cases, setCases] = useState<CasesResponse | null>(null);
  const [policyRows, setPolicyRows] = useState<PolicyResult[]>([]);
  const [source, setSource] = useState<Source | null>(null);

  useEffect(() => {
    getData<CasesResponse>("/cases?limit=200", "cases.json").then((result) => {
      setCases(result.data);
      setSource(result.source);
    });
    policies().then(setPolicyRows);
  }, []);

  const evidence = useMemo(() => {
    const codes = cases?.cases.map((item) => item.top_reason?.code).filter(Boolean) ?? [];
    return Object.entries(GROUPS).map(([key, group]) => ({
      key,
      ...group,
      count: codes.filter((code) => group.codes.includes(code!)).length,
    }));
  }, [cases]);
  const evidenceMax = Math.max(...evidence.map((row) => row.count), 1);
  const high = cases?.cases.filter((item) => item.band === "high").length ?? 0;
  const review = cases?.cases.filter((item) => item.band === "review").length ?? 0;
  const alertMax = Math.max(high, review, 1);

  return (
    <section className="mt-6 grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
      <div className="glass-panel rounded-[1.75rem] p-6 sm:p-7">
        <div className="mb-7 flex items-start justify-between gap-4">
          <div>
            <div className="eyebrow">Current queue</div>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">Attention, clearly prioritized</h2>
          </div>
          <span className="flex shrink-0 items-center gap-2 rounded-full border border-line bg-panel/50 px-3 py-1 text-[11px] text-muted">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-accent" />
            {source === "live" ? "Live API" : source === "demo" ? "Fast demo" : "Loading"}
          </span>
        </div>
        {!cases ? (
          <LoadingBars />
        ) : (
          <div className="space-y-6">
            {[
              { label: "High priority", value: high, tone: "from-rose-500 to-orange-400" },
              { label: "Needs review", value: review, tone: "from-amber-400 to-yellow-300" },
            ].map((row, index) => (
              <div key={row.label}>
                <div className="mb-2 flex items-end justify-between">
                  <span className="text-sm font-medium">{row.label}</span>
                  <span className="text-2xl font-semibold tabular-nums">{row.value}</span>
                </div>
                <Bar width={(row.value / alertMax) * 100} tone={row.tone} delay={index * 120} />
              </div>
            ))}
            <div className="glass-inset rounded-xl px-4 py-3 text-xs leading-5 text-muted">
              Ranked by fused risk. A place in this queue requests review; it is not a finding.
            </div>
          </div>
        )}
      </div>

      <div className="glass-panel rounded-[1.75rem] p-6 sm:p-7">
        <div className="mb-7">
          <div className="eyebrow">Evidence mix</div>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">Why shops rise to the top</h2>
          <p className="mt-1 text-xs text-muted">Top reason across the current synthetic alert queue</p>
        </div>
        {!cases ? (
          <LoadingBars />
        ) : (
          <div className="space-y-5">
            {evidence.map((row, index) => (
              <div key={row.key}>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-medium">{row.label}</span>
                  <span className="tabular-nums text-muted">{row.count} alerts</span>
                </div>
                <Bar width={(row.count / evidenceMax) * 100} tone={row.tone} delay={160 + index * 120} />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="glass-panel rounded-[1.75rem] p-6 sm:p-7 lg:col-span-2">
        <div className="mb-7 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="eyebrow">Policy replay</div>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">Compare intervention, not just detection</h2>
          </div>
          <p className="max-w-md text-xs leading-5 text-muted">
            Misuse value stopped or rerouted in the fast synthetic replay. Demo output, not a forecast.
          </p>
        </div>
        {policyRows.length === 0 ? (
          <LoadingBars />
        ) : (
          <div className="grid gap-5 md:grid-cols-5">
            {policyRows.map((row, index) => {
              const caught =
                row.misuse_taka_total === 0
                  ? 0
                  : (row.misuse_taka_stopped + row.misuse_taka_rerouted) / row.misuse_taka_total;
              return (
                <div key={row.policy} className="group">
                  <div className="mb-3 flex items-baseline justify-between gap-2">
                    <span className="text-xs font-medium text-muted">{row.policy}</span>
                    <span className="text-xl font-semibold tabular-nums">{Math.round(caught * 100)}%</span>
                  </div>
                  <Bar
                    width={caught * 100}
                    tone={index < 2 ? "from-slate-500 to-slate-300" : "from-accent to-sky-400"}
                    delay={240 + index * 100}
                  />
                  <div className="mt-3 text-sm font-medium">{POLICY_NAME[row.policy]}</div>
                  <div className="mt-1 text-[11px] text-muted">
                    {row.honest_shops_restricted} honest shops restricted
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
