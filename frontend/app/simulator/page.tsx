"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageTitle, Panel, SourceNote } from "@/components/ui";
import { pct, postData, taka, type Source } from "@/lib/api";
import type { PolicyResult, SimulateGrid, SimulateResponse } from "@/lib/types";

const POLICY_LABEL: Record<string, { short: string; long: string }> = {
  A: { short: "A · Do nothing", long: "No monitoring." },
  B: { short: "B · Blanket limit", long: "Every shop capped at the same daily QR limit." },
  C: { short: "C · Rules only", long: "Analysts review shops flagged by fixed rules." },
  D: { short: "D · Jachai targeted", long: "Analysts review the highest Jachai risk first." },
  E: { short: "E · Jachai + convert", long: "As D, and high-demand cash-out shops are offered agent contracts." },
};

interface Sliders {
  misuse_scale: number;
  fee_per_1000: number; // taka per ৳ 1,000 (fee rate x 1000)
  analyst_capacity_per_day: number;
  limit_level: number;
}

const DEFAULTS: Sliders = { misuse_scale: 1, fee_per_1000: 18.5, analyst_capacity_per_day: 20, limit_level: 100000 };

const nearest = (values: number[], x: number) => values.reduce((a, b) => (Math.abs(b - x) < Math.abs(a - x) ? b : a));

/** Demo mode: nearest pre-computed run; fees recomputed exactly for the chosen fee rate. */
function fromGrid(grid: SimulateGrid, s: Sliders): SimulateResponse {
  const m = nearest(grid.axes.misuse_scale, s.misuse_scale);
  const c = nearest(grid.axes.analyst_capacity_per_day, s.analyst_capacity_per_day);
  const l = nearest(grid.axes.limit_level, s.limit_level);
  const run =
    grid.runs.find(
      (r) => r.params.misuse_scale === m && r.params.analyst_capacity_per_day === c && r.params.limit_level === l,
    ) ?? grid.runs[0];
  const rate = s.fee_per_1000 / 1000;
  const share = run.params.displaced_to_agents_share;
  return {
    ...run,
    results: run.results.map((r) => ({
      ...r,
      fee_rate: rate,
      fees_recaptured: rate * (r.misuse_taka_rerouted + share * r.misuse_taka_stopped),
    })),
  };
}

function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  show: (v: number) => string;
  onChange: (v: number) => void;
  hint: string;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">{props.label}</span>
        <span className="tabular-nums text-accent">{props.show(props.value)}</span>
      </div>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
        className="mt-2 w-full accent-[#2563EB]"
      />
      <div className="text-xs text-muted">{props.hint}</div>
    </label>
  );
}

function PolicyCard({ r, best }: { r: PolicyResult; best: boolean }) {
  const caught = r.misuse_taka_total ? (r.misuse_taka_stopped + r.misuse_taka_rerouted) / r.misuse_taka_total : 0;
  return (
    <div className={`relative overflow-hidden rounded-2xl border p-4 shadow-sm ${best ? "border-accent/50 bg-accent-soft" : "border-line bg-panel/50"}`}>
      {best && <div className="absolute right-3 top-3 rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">Top capture</div>}
      <div className="text-sm font-semibold">{POLICY_LABEL[r.policy].short}</div>
      <div className="mt-0.5 min-h-8 text-xs text-muted">{POLICY_LABEL[r.policy].long}</div>
      <div className="mt-3 text-3xl font-semibold tabular-nums">{pct(caught)}</div>
      <div className="text-xs text-muted">of misuse taka stopped or rerouted</div>
      <dl className="mt-3 space-y-1 text-xs">
        <div className="flex justify-between">
          <dt className="text-muted">Honest shops restricted</dt>
          <dd className={`tabular-nums font-medium ${r.honest_shops_restricted ? "text-high" : ""}`}>
            {r.honest_shops_restricted}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Genuine sales blocked</dt>
          <dd className="tabular-nums">{taka(r.blocked_genuine_sales)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Fees recaptured</dt>
          <dd className="tabular-nums">{taka(r.fees_recaptured)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Alerts per day</dt>
          <dd className="tabular-nums">{r.analyst_alerts_per_day.toFixed(1)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Agent leads / signed</dt>
          <dd className="tabular-nums">
            {r.agent_leads} / {r.agents_signed}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted">Genuine-commerce share</dt>
          <dd className="tabular-nums">{pct(r.genuine_commerce_share)}</dd>
        </div>
      </dl>
    </div>
  );
}

export default function SimulatorPage() {
  const [sliders, setSliders] = useState<Sliders>(DEFAULTS);
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [grid, setGrid] = useState<SimulateGrid | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setBusy(true);
      try {
        const live = await postData<SimulateResponse>("/simulate", {
          misuse_scale: sliders.misuse_scale,
          fee_rate: sliders.fee_per_1000 / 1000,
          analyst_capacity_per_day: sliders.analyst_capacity_per_day,
          limit_level: sliders.limit_level,
        });
        setResult(live);
        setSource("live");
      } catch {
        const g = grid ?? ((await (await fetch("/demo/simulate-grid.json")).json()) as SimulateGrid);
        setGrid(g);
        setResult(fromGrid(g, sliders));
        setSource("demo");
      } finally {
        setBusy(false);
      }
    }, 250);
  }, [sliders, grid]);

  const set = (k: keyof Sliders) => (v: number) => setSliders((s) => ({ ...s, [k]: v }));
  const results = useMemo(() => result?.results ?? [], [result]);
  const best = useMemo(() => {
    // Highlight: most misuse handled while restricting no honest shop.
    const ok = results.filter((r) => r.honest_shops_restricted === 0 && r.policy !== "A");
    return ok.sort((a, b) => b.misuse_taka_stopped + b.misuse_taka_rerouted - (a.misuse_taka_stopped + a.misuse_taka_rerouted))[0]?.policy;
  }, [results]);
  const chart = results.map((r) => ({
    name: r.policy,
    Stopped: r.misuse_taka_stopped,
    "Rerouted to agents": r.misuse_taka_rerouted,
    "Still flowing": r.misuse_taka_still_flowing,
    "Honest shops restricted": r.honest_shops_restricted,
    "Fees recaptured": r.fees_recaptured,
  }));

  return (
    <>
      <PageTitle
        title="Policy simulator"
        subtitle="The same synthetic month replayed under five policies. Move a slider and every policy is replayed with identical payments and identical analyst outcomes, so differences come only from the policy."
      />
      {source === "demo" && (
        <SourceNote source="demo" />
      )}
      <div className="space-y-6">
        <Panel title="Settings">
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <Slider label="Misuse share" value={sliders.misuse_scale} min={0.25} max={1} step={0.05}
              show={(v) => `${Math.round(v * 100)}% of misuse shops`} onChange={set("misuse_scale")}
              hint="Fewer or more shops running hidden cash-outs." />
            <Slider label="Cash-out fee" value={sliders.fee_per_1000} min={13} max={18.5} step={0.5}
              show={(v) => `৳ ${v.toFixed(2)} per ৳ 1,000`} onChange={set("fee_per_1000")}
              hint="Charge earned when cash-out goes through a licensed agent." />
            <Slider label="Analyst capacity" value={sliders.analyst_capacity_per_day} min={0} max={40} step={1}
              show={(v) => `${v} shops/day`} onChange={set("analyst_capacity_per_day")}
              hint="Reviews per day for policies C, D and E." />
            <Slider label="Blanket limit (policy B)" value={sliders.limit_level} min={25000} max={300000} step={25000}
              show={(v) => taka(v)} onChange={set("limit_level")}
              hint="Same daily QR cap for every shop." />
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button onClick={() => setSliders(DEFAULTS)} className="text-sm text-accent hover:underline">
              Reset
            </button>
            {source === "demo" && (
              <p className="text-xs text-muted">
                Demo mode uses the nearest of 48 pre-computed runs; fees follow the slider exactly.
              </p>
            )}
          </div>
        </Panel>

        <div className={`space-y-6 transition-opacity ${busy ? "opacity-60" : ""}`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {results.map((r) => (
              <PolicyCard key={r.policy} r={r} best={r.policy === best} />
            ))}
          </div>

          <Panel title="Where the misuse taka goes">
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeOpacity={0.15} vertical={false} />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={(v) => `${(v / 100000).toFixed(0)} lakh`} width={60} />
                  <Tooltip formatter={(v) => taka(Number(v))} />
                  <Legend />
                  <Bar dataKey="Stopped" stackId="a" fill="#2563EB" />
                  <Bar dataKey="Rerouted to agents" stackId="a" fill="#93B4F5" />
                  <Bar dataKey="Still flowing" stackId="a" fill="#DCE4F1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Panel>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel title="Honest shops restricted">
              <div className="h-48">
                <ResponsiveContainer>
                  <BarChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeOpacity={0.15} vertical={false} />
                    <XAxis dataKey="name" />
                    <YAxis allowDecimals={false} width={32} />
                    <Tooltip />
                    <Bar dataKey="Honest shops restricted" fill="#D33D48" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Fees recaptured">
              <div className="h-48">
                <ResponsiveContainer>
                  <BarChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                    <CartesianGrid strokeOpacity={0.15} vertical={false} />
                    <XAxis dataKey="name" />
                    <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} width={40} />
                    <Tooltip formatter={(v) => taka(Number(v))} />
                    <Bar dataKey="Fees recaptured" fill="#D08914" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
          </div>

          {result && (
            <p className="text-xs text-muted">
              Replay world seed {result.replay.seed}, last {result.results[0]?.days} days, misuse in the replayed period{" "}
              {taka(result.results[0]?.misuse_taka_total ?? 0)}. {result.note} Highlighted: the policy that handles
              the most misuse taka without restricting any honest shop.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
