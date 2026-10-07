"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  ChevronRight,
  Download,
  Eye,
  Info,
  type LucideIcon,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Store,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CategoryIcon, categoryLabel } from "@/components/Brand";
import { BandBadge, SourceNote, SyntheticBadge } from "@/components/ui";
import { API_BASE, fmtDay, fmtStamp, getData, pct, postData, type Source, taka, takaCompact } from "@/lib/api";
import type { Band, Overview as OverviewData, PolicyResult, SimulateGrid, SimulateResponse } from "@/lib/types";

// The overview home. Every figure comes from GET /overview (or its exported demo
// JSON) and, for the simulator tile, POST /simulate (or the exported demo grid);
// the only things computed here are percentages and chart scales.

type BandFilter = "all" | Band;

const POLICY_NAME: Record<PolicyResult["policy"], string> = {
  A: "Do nothing",
  B: "Blanket limit",
  C: "Rules only",
  D: "Jachai targeted",
  E: "Jachai + convert",
};

/** Default-settings policy replay: live API, else the matching pre-computed demo run. */
async function loadPolicies(): Promise<PolicyResult[]> {
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

const handled = (r: PolicyResult) =>
  r.misuse_taka_total ? (r.misuse_taka_stopped + r.misuse_taka_rerouted) / r.misuse_taka_total : 0;

function greetingFor(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

/** Round axis: a 1 / 2 / 2.5 / 5 × 10^n step, about four steps up to the top. */
function niceAxis(max: number): { top: number; ticks: number[] } {
  if (max <= 0) return { top: 1, ticks: [0, 1] };
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = ([1, 2, 2.5, 5, 10].find((s) => s * power >= rough) ?? 10) * power;
  const top = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = 0; v <= top + step / 2; v += step) ticks.push(v);
  return { top, ticks };
}

function Delta({ value, suffix, onBlue = false }: { value: number | null; suffix: string; onBlue?: boolean }) {
  if (value === null) return <span className={`text-xs ${onBlue ? "text-white/70" : "text-muted"}`}>no earlier week to compare</span>;
  const up = value >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="flex items-center gap-2 text-xs">
      <span className={`chip ${onBlue ? "" : up ? "border-low/25 bg-low-soft text-low" : "border-high/25 bg-high-soft text-high"}`}>
        <Icon aria-hidden="true" className="h-3 w-3" />
        {up ? "+" : ""}
        {(value * 100).toFixed(1)}%
      </span>
      <span className={onBlue ? "text-white/75" : "text-muted"}>{suffix}</span>
    </span>
  );
}

function VolumeCard({ data, source }: { data: OverviewData; source: Source | null }) {
  const days = data.daily.slice(-data.window_days);
  const { top, ticks } = niceAxis(Math.max(...days.map((d) => d.turnover)));
  const last = days[days.length - 1];
  const before = days[days.length - 2];
  const dayDelta = before && before.turnover ? (last.turnover - before.turnover) / before.turnover : null;
  const downloadHref = source === "live" ? `${API_BASE}/overview` : "/demo/overview.json";
  return (
    <section className="card-primary p-5 sm:p-6" aria-labelledby="volume-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="volume-title" className="flex items-center gap-1.5 text-[15px] font-medium text-white/90">
            Total payment volume
            <span
              title="Sum of QR payments received by all monitored shops. Synthetic world; the flagged part is above the payment model's review threshold."
              className="grid h-4 w-4 place-items-center rounded-full border border-white/40 text-white/80"
            >
              <Info aria-hidden="true" className="h-2.5 w-2.5" />
            </span>
          </h2>
          <div className="mt-2 text-[2.35rem] font-bold leading-none tracking-tight tabular-nums sm:text-[2.75rem]">
            {taka(data.volume.turnover_7d)}
          </div>
          <div className="mt-3">
            <Delta value={data.volume.delta_vs_previous} suffix={`vs previous ${data.window_days} days`} onBlue />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="chip">Last {data.window_days} days</span>
          <a
            href={downloadHref}
            download="jachai-overview.json"
            title="Download these figures as JSON"
            aria-label="Download these figures as JSON"
            className="grid h-8 w-8 place-items-center rounded-full border border-white/25 bg-white/15 text-white hover:bg-white/25"
          >
            <Download aria-hidden="true" className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-[2.6rem_1fr] gap-x-2">
        <div className="relative h-44 text-[10px] text-white/70">
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2 tabular-nums" style={{ top: `${(1 - t / top) * 100}%` }}>
              {t === 0 ? "0" : takaCompact(t).replace("৳ ", "")}
            </span>
          ))}
        </div>
        <div className="relative h-44">
          {ticks.map((t) => (
            <div key={t} className="absolute inset-x-0 border-t border-white/15" style={{ top: `${(1 - t / top) * 100}%` }} />
          ))}
          <ol className="absolute inset-0 grid items-end gap-2 sm:gap-3" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
            {days.map((d, i) => {
              const h = (d.turnover / top) * 100;
              const flagged = d.turnover ? (d.flagged_turnover / d.turnover) * 100 : 0;
              const isLast = i === days.length - 1;
              return (
                <li key={d.day} className="relative flex h-full items-end justify-center">
                  {isLast && (
                    <div className="absolute bottom-full left-1/2 z-10 mb-3 w-max -translate-x-1/2 rounded-xl bg-white px-3 py-2 text-left shadow-lg shadow-navy/20 sm:left-auto sm:right-0 sm:translate-x-0">
                      <div className="text-[10px] text-muted">{fmtDay(d.day, true)}</div>
                      <div className="flex items-center gap-2 text-sm font-semibold text-navy tabular-nums">
                        {taka(d.turnover)}
                        {dayDelta !== null && (
                          <span className={`chip px-1.5 py-0.5 text-[10px] ${dayDelta >= 0 ? "border-low/25 bg-low-soft text-low" : "border-high/25 bg-high-soft text-high"}`}>
                            {dayDelta >= 0 ? <ArrowUpRight className="h-2.5 w-2.5" aria-hidden="true" /> : <ArrowDownRight className="h-2.5 w-2.5" aria-hidden="true" />}
                            {(dayDelta * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-[10px] text-muted">
                        {d.flagged} of {d.payments.toLocaleString("en-US")} payments above threshold
                      </div>
                    </div>
                  )}
                  <div
                    className={`bar-grow relative w-full max-w-11 overflow-hidden rounded-t-md ${isLast ? "bg-white" : "bg-white/35"}`}
                    style={{ height: `${Math.max(h, 1.5)}%`, animationDelay: `${i * 60}ms` }}
                    title={`${fmtDay(d.day, true)} · ${taka(d.turnover)} from ${d.payments.toLocaleString("en-US")} payments · ${d.flagged} above threshold (${taka(d.flagged_turnover)})`}
                  >
                    <div className={`absolute inset-x-0 bottom-0 ${isLast ? "bg-navy/70" : "bg-navy/45"}`} style={{ height: `${flagged}%` }} />
                  </div>
                  {isLast && <span className="absolute inset-y-0 left-1/2 -z-0 border-l border-dashed border-white/50" />}
                </li>
              );
            })}
          </ol>
        </div>
        <div />
        <ol className="mt-2 grid text-center text-[11px] text-white/80" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
          {days.map((d) => (
            <li key={d.day}>{fmtDay(d.day)}</li>
          ))}
        </ol>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-white/75">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-white/60" /> QR turnover per day
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-navy/60" /> above the payment review threshold ({pct(data.volume.flagged_turnover_7d / Math.max(data.volume.turnover_7d, 1))} of the week)
        </span>
      </div>
    </section>
  );
}

function AlertsCard({ data, topCase }: { data: OverviewData; topCase: string | null }) {
  const [filter, setFilter] = useState<BandFilter>("all");
  const count = filter === "all" ? data.shops.alerts : filter === "high" ? data.shops.high : filter === "review" ? data.shops.review : data.shops.low;
  const queueHref = filter === "all" || filter === "low" ? "/queue" : `/queue?band=${filter}`;
  const actions: { href: string; label: string; icon: LucideIcon; disabled?: boolean }[] = [
    { href: queueHref, label: "View cases", icon: Eye },
    { href: topCase ? `/cases/${topCase}` : "/queue", label: "Investigate", icon: Search, disabled: !topCase },
    { href: "/simulator", label: "Run policy simulator", icon: SlidersHorizontal },
  ];
  return (
    <section className="card-primary flex flex-col p-5 sm:p-6" aria-labelledby="alerts-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 id="alerts-title" className="flex items-center gap-2 text-[15px] font-medium text-white/90">
          <span className="grid h-8 w-8 place-items-center rounded-full border border-white/25 bg-white/10">
            <ShieldCheck aria-hidden="true" className="h-4 w-4" />
          </span>
          Risk alerts
        </h2>
        <label className="chip cursor-pointer gap-1 pr-2">
          <span className="sr-only">Band</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as BandFilter)}
            className="!border-0 !bg-transparent !p-0 text-xs font-medium text-white !shadow-none [&>option]:text-ink"
          >
            <option value="all">All alert bands</option>
            <option value="high">High priority</option>
            <option value="review">Needs review</option>
            <option value="low">No action</option>
          </select>
        </label>
      </div>
      <div className="mt-3 text-[2.75rem] font-bold leading-none tabular-nums sm:text-[3.1rem]">{count}</div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        {data.shops.high > 0 && (
          <span className="chip !border-white/10 !bg-high/80">
            <TriangleAlert aria-hidden="true" className="h-3 w-3" />
            {data.shops.high} high priority
          </span>
        )}
        <span className="text-white/75">
          {filter === "low" ? "shops with no action needed" : "shops asking for an analyst's look"}
        </span>
        <span className="chip ml-auto">
          <Eye aria-hidden="true" className="h-3 w-3" />
          Pending review: {data.shops.review}
        </span>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-2">
        {actions.map(({ href, label, icon: Icon, disabled }) => (
          <Link
            key={label}
            href={href}
            aria-disabled={disabled}
            className={`flex flex-col items-center gap-1.5 rounded-2xl bg-white px-2 py-3 text-center text-[11px] font-semibold text-navy hover:bg-white/90 sm:text-xs ${disabled ? "pointer-events-none opacity-60" : ""}`}
          >
            <Icon aria-hidden="true" className="h-4 w-4 text-primary" />
            {label}
          </Link>
        ))}
      </div>

      <div className="mt-auto pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/20 bg-navy/30 px-4 py-3 text-xs">
          <span className="flex items-center gap-3">
            <span className="tracking-[0.2em] text-white/70">••••</span>
            <span className="font-mono text-[13px] tabular-nums" title="Payment model fingerprint">
              {data.model.payment_model_fingerprint.slice(-8)}
            </span>
            <span className="tabular-nums text-white/80" title="Payment review threshold">
              thr {data.model.payment_threshold.toFixed(2)}
            </span>
          </span>
          <span className="flex items-center gap-1.5 font-medium">
            <Waypoints aria-hidden="true" className="h-3.5 w-3.5" />
            {data.shops.ring_linked} ring-linked shops
          </span>
        </div>
      </div>
    </section>
  );
}

function RecentPayments({ data }: { data: OverviewData }) {
  return (
    <section className="card p-5 sm:p-6" aria-labelledby="recent-title">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="recent-title" className="text-lg font-semibold text-navy">
            Recent flagged payments
          </h2>
          <p className="mt-0.5 text-xs text-muted">
            Above the payment review threshold ({data.model.payment_threshold.toFixed(2)}) at shops now in an alert band · last {data.window_days} days
          </p>
        </div>
        <Link href="/queue" className="shrink-0 text-sm font-medium text-primary hover:underline">
          View all
        </Link>
      </div>
      <ul className="mt-4 space-y-2">
        {data.recent_flagged_payments.map((p) => (
          <li key={p.payment_id}>
            <Link
              href={`/cases/${p.shop_id}`}
              className="card-inset grid grid-cols-[2.5rem_1fr_auto] items-center gap-3 px-3 py-2.5 hover:border-primary/50 sm:grid-cols-[2.5rem_1.4fr_auto_auto_auto_1rem]"
            >
              <span className="grid h-10 w-10 place-items-center rounded-full bg-surface text-primary ring-1 ring-border">
                <CategoryIcon category={p.category} className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-ink">
                  Shop {p.shop_id} <span className="font-normal text-muted">· {categoryLabel(p.category)}</span>
                </span>
                <span className="block text-xs text-muted">{fmtStamp(p.ts)}</span>
              </span>
              <span className="hidden sm:block">
                <BandBadge band={p.band} />
              </span>
              <span className="hidden text-xs text-muted tabular-nums sm:block" title={`Payment ${p.payment_id}`}>
                •••• {p.payment_id.slice(-4)}
              </span>
              <span className="text-right text-sm font-semibold text-ink tabular-nums">
                {taka(p.amount)}
                <span className="block text-[10px] font-normal text-muted">score {p.score.toFixed(2)}</span>
              </span>
              <ChevronRight aria-hidden="true" className="hidden h-4 w-4 text-muted sm:block" />
            </Link>
          </li>
        ))}
        {data.recent_flagged_payments.length === 0 && (
          <li className="text-sm text-muted">No payments above the threshold at alert-band shops in the last {data.window_days} days.</li>
        )}
      </ul>
      <p className="mt-3 text-[11px] text-muted">A flagged payment asks for a look at the shop; it is not a finding against the payer or the shop.</p>
    </section>
  );
}

/** One bar split into labelled parts (e.g. bands); parts sum to the total. */
function SegmentBar({ parts, total }: { parts: { label: string; value: number; className: string }[]; total: number }) {
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-border" role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(", ")}>
        {parts.map((p) => (
          <div key={p.label} className={`metric-bar h-full ${p.className}`} style={{ width: `${total ? (p.value / total) * 100 : 0}%` }} />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted">
        {parts.map((p) => (
          <span key={p.label} className="flex items-center gap-1">
            <span className={`h-1.5 w-1.5 rounded-full ${p.className}`} />
            {p.label} {p.value.toLocaleString("en-US")}
          </span>
        ))}
      </div>
    </div>
  );
}

function PolicyBars({ rows }: { rows: PolicyResult[] }) {
  if (!rows.length) return <div className="shimmer h-12 rounded-lg" />;
  const best = rows.filter((r) => r.policy !== "A" && r.honest_shops_restricted === 0).sort((a, b) => handled(b) - handled(a))[0];
  return (
    <div>
      <div className="flex h-12 items-end gap-1.5" role="img" aria-label={rows.map((r) => `${POLICY_NAME[r.policy]} ${pct(handled(r))}`).join(", ")}>
        {rows.map((r, i) => (
          <div
            key={r.policy}
            title={`${POLICY_NAME[r.policy]}: ${pct(handled(r))} of misuse taka stopped or rerouted · ${r.honest_shops_restricted} honest shops restricted`}
            className={`bar-grow flex-1 rounded-t-sm ${r.policy === best?.policy ? "bg-primary" : r.honest_shops_restricted ? "bg-high/60" : "bg-primary/30"}`}
            style={{ height: `${Math.max(handled(r) * 100, 3)}%`, animationDelay: `${i * 50}ms` }}
          />
        ))}
      </div>
      <div className="mt-1 grid grid-cols-5 text-center text-[10px] text-muted">
        {rows.map((r) => (
          <span key={r.policy} className={r.policy === best?.policy ? "font-semibold text-primary" : ""}>
            {r.policy}
          </span>
        ))}
      </div>
      <div className="mt-1.5 text-[10px] text-muted">
        {best ? `${POLICY_NAME[best.policy]} handles ${pct(handled(best))} of misuse taka with no honest shop restricted` : "misuse taka handled per policy"}
      </div>
    </div>
  );
}

function Tile({
  href,
  icon: Icon,
  title,
  value,
  sub,
  children,
}: {
  href: string;
  icon: LucideIcon;
  title: string;
  value: string;
  sub: string;
  children?: React.ReactNode;
}) {
  return (
    <Link href={href} className="card group flex flex-col p-5 hover:border-primary/50">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent-soft text-primary">
          <Icon aria-hidden="true" className="h-4 w-4" />
        </span>
        <span className="text-sm font-medium text-ink">{title}</span>
        <ChevronRight aria-hidden="true" className="ml-auto h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5" />
      </div>
      <div className="mt-4 text-[1.9rem] font-bold leading-none text-navy tabular-nums">{value}</div>
      <div className="mt-2 text-xs text-muted">{sub}</div>
      {children && <div className="mt-auto pt-4">{children}</div>}
    </Link>
  );
}

export function Overview() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [topCase, setTopCase] = useState<string | null>(null);
  const [policies, setPolicies] = useState<PolicyResult[]>([]);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [greeting, setGreeting] = useState("Welcome back");

  useEffect(() => {
    setGreeting(greetingFor(new Date().getHours()));
    loadPolicies().then(setPolicies);
    getData<OverviewData>("/overview", "overview.json")
      .then((r) => {
        setData(r.data);
        setSource(r.source);
      })
      .catch((e: Error) => setError(e.message));
    getData<{ cases: { case_id: string }[] }>("/cases?limit=1", "cases.json")
      .then((r) => setTopCase(r.data.cases[0]?.case_id ?? null))
      .catch(() => setTopCase(null));
  }, []);

  const range = useMemo(
    () => (data ? `${fmtDay(data.window.start)} – ${fmtDay(data.window.end, true)}` : null),
    [data],
  );

  return (
    <>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium text-primary">
            AI-powered merchant risk &amp; transaction integrity for Bangla QR
          </p>
          <h1 className="display mt-2 text-4xl font-semibold text-navy sm:text-5xl">
            {greeting}, <span className="text-primary">Analyst!</span>
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SyntheticBadge />
          <span className="chip h-10 px-3.5 text-[13px]">
            <CalendarDays aria-hidden="true" className="h-4 w-4 text-primary" />
            {range ?? "Loading range…"}
          </span>
        </div>
      </div>

      <div className="mt-6">
        <SourceNote source={source} />
      </div>
      {error && <p className="text-sm text-high">{error}</p>}

      {!data ? (
        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="shimmer h-80 rounded-[1.25rem]" />
          <div className="shimmer h-80 rounded-[1.25rem]" />
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
            <VolumeCard data={data} source={source} />
            <AlertsCard data={data} topCase={topCase} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
            <RecentPayments data={data} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Tile
                href="/queue"
                icon={Store}
                title="Shops monitored"
                value={data.shops.monitored.toLocaleString("en-US")}
                sub={`scored as of ${fmtDay(data.as_of)} · mean fused risk ${data.shops.mean_risk.toFixed(2)}`}
              >
                <SegmentBar
                  total={data.shops.monitored}
                  parts={[
                    { label: "No action", value: data.shops.low, className: "bg-low" },
                    { label: "Review", value: data.shops.review, className: "bg-warning" },
                    { label: "High", value: data.shops.high, className: "bg-danger" },
                  ]}
                />
              </Tile>
              <Tile
                href="/queue"
                icon={TriangleAlert}
                title="Shops needing review"
                value={data.shops.alerts.toLocaleString("en-US")}
                sub={`${pct(data.shops.alerts / Math.max(data.shops.monitored, 1))} of monitored shops ask for a look`}
              >
                <SegmentBar
                  total={data.shops.alerts}
                  parts={[
                    { label: "High priority", value: data.shops.high, className: "bg-danger" },
                    { label: "Needs review", value: data.shops.review, className: "bg-warning" },
                  ]}
                />
              </Tile>
              <Tile
                href={topCase ? `/cases/${topCase}` : "/queue"}
                icon={Waypoints}
                title="Network signals"
                value={data.shops.ring_linked.toLocaleString("en-US")}
                sub={`ring-linked shops · ${data.shops.with_linking_payers} share heavy-day payers`}
              >
                <SegmentBar
                  total={data.shops.alerts}
                  parts={[
                    { label: "Ring-linked alerts", value: data.shops.ring_linked_alerts, className: "bg-primary" },
                    { label: "Other alerts", value: data.shops.alerts - data.shops.ring_linked_alerts, className: "bg-primary/25" },
                  ]}
                />
              </Tile>
              <Tile
                href="/simulator"
                icon={SlidersHorizontal}
                title="Policy simulator"
                value="Compare"
                sub="blanket limit vs rules vs Jachai, same month and analysts"
              >
                <PolicyBars rows={policies} />
              </Tile>
            </div>
          </div>

          <p className="mt-5 text-[11px] leading-5 text-muted">
            Payment model {data.model.payment_model_fingerprint} · review threshold {data.model.payment_threshold.toFixed(2)} ·
            evidence as of {fmtDay(data.model.evidence_timestamp, true)} · {data.volume.payments_7d.toLocaleString("en-US")} payments scored this week,{" "}
            {data.volume.flagged_7d.toLocaleString("en-US")} above threshold. {data.note}
          </p>
        </>
      )}
    </>
  );
}
