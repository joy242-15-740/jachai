"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { mean } from "@/components/EvasionToggle";
import { getData, taka } from "@/lib/api";
import { type ExampleKey, loadExample, loadManifest, type ReferenceManifest } from "@/lib/reference";
import type { CaseDetail, SimulateGrid } from "@/lib/types";

// A guided six-step product demo. Every number in an "expected" line is read
// from the data the step opens (reference examples, simulator run, validation
// report); nothing is typed by hand.

type Row = { group: string; variant: string; [k: string]: number | string };
type Metrics = { reports: Record<string, { per_seed?: { shop_rows: Row[] }[] }> };
const KEY = "jachai-walkthrough-open";

interface Facts {
  manifest: ReferenceManifest;
  cases: Partial<Record<ExampleKey, CaseDetail>>;
  blanketHonest: number | null;
  jachaiHonest: number | null;
  rulesRing: [number | null, number | null];
  jachaiRing: [number | null, number | null];
}

async function loadFacts(): Promise<Facts> {
  const manifest = await loadManifest();
  const keys: ExampleKey[] = ["ring", "honest_lookalike", "cash_desk", "convert_lead"];
  const cases = Object.fromEntries(
    await Promise.all(keys.map(async (k) => [k, await loadExample(k)] as const)),
  ) as Facts["cases"];
  const grid = (await (await fetch("/demo/simulate-grid.json")).json()) as SimulateGrid;
  const base = grid.runs.find(
    (r) => r.params.misuse_scale === 1 && r.params.analyst_capacity_per_day === 20 && r.params.limit_level === 100000,
  );
  const policy = (p: string) => base?.results.find((r) => r.policy === p)?.honest_shops_restricted ?? null;
  const metrics = await getData<Metrics>("/metrics", "metrics.json").catch(() => null);
  const rows = (metrics?.data.reports["validation_evaluation.json"]?.per_seed ?? []).flatMap((s) => s.shop_rows);
  const ring = (g: string, v: string) => mean(rows, g, v, "recall_limit_bypass");
  return {
    manifest,
    cases,
    blanketHonest: policy("B"),
    jachaiHonest: policy("D"),
    rulesRing: [ring("baseline", "rules_only"), ring("evasion", "rules_only")],
    jachaiRing: [ring("system", "fused_risk"), ring("evasion", "fused_risk")],
  };
}

const fmt2 = (x: number | null) => (x == null ? "—" : x.toFixed(2));

function steps(f: Facts) {
  const ring = f.cases.ring;
  const honest = f.cases.honest_lookalike;
  const desk = f.cases.cash_desk;
  const lead = f.cases.convert_lead;
  const demand = lead?.recommendation?.estimated_cash_out_demand_30d ?? 0;
  const ex = f.manifest.examples;
  return [
    {
      title: "A ring of shops sharing payers",
      href: "/examples/ring",
      cta: "Open the ring case",
      expected: ring
        ? `${ring.neighbourhood.linking_payers ?? 0} payers link it to a group of ${ring.neighbourhood.community_size ?? 0} nearby shops; band "${ring.scores.band}", recommended: escalate the whole group. No agent offer is shown to a ring.`
        : "",
    },
    {
      title: "An honest shop that looks suspicious, correctly not flagged",
      href: "/examples/honest_lookalike",
      cta: "Open the electronics shop",
      expected: honest
        ? `Large round sales, but band "${honest.scores.band}" with fused risk ${honest.scores.risk.toFixed(2)}: recommended "clear". Peer comparison spares genuine big-ticket sellers.`
        : "",
    },
    {
      title: "A disguised cash-out shop: Bangla notice and appeal",
      href: "/notice?example=cash_desk",
      cta: "Open the merchant notice",
      expected: desk
        ? `Band "${desk.scores.band}". A polite Bangla notice lists this shop's own reasons and says no decision has been made; the shopkeeper can explain through the appeal form.`
        : "",
    },
    {
      title: "The agents who lost business, and the convert lead",
      href: "/examples/convert_lead",
      cta: "Open the convert lead",
      expected: lead
        ? `About ${taka(demand)} of flagged payments in 30 days went around ${ex.convert_lead.agents_in_zone} licensed agents in its zone (about ${taka(demand * f.manifest.agent_cash_out_fee_rate)} in fees). Recommended: offer an agent contract.`
        : "",
    },
    {
      title: "Blanket limit vs Jachai",
      href: "/simulator?preset=blanket-vs-jachai",
      cta: "Open the simulator preset",
      expected: `Same month, same analysts: a ৳ 1 lakh blanket limit restricts ${f.blanketHonest ?? "—"} honest shops; Jachai-targeted review restricts ${f.jachaiHonest ?? "—"} (fast demo world).`,
    },
    {
      title: "Evasion: rules drop while Jachai holds",
      href: "/trust#evasion",
      cta: "Open the evasion toggle",
      expected: `When amounts stop being round, ring recall for rules goes ${fmt2(f.rulesRing[0])} → ${fmt2(f.rulesRing[1])}; for Jachai ${fmt2(f.jachaiRing[0])} → ${fmt2(f.jachaiRing[1])} (3 validation seeds). On the normal world rules rank better; the toggle shows both.`,
    },
  ];
}

export function JudgeWalkthrough() {
  const [open, setOpen] = useState(false);
  const [facts, setFacts] = useState<Facts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<number[]>([]);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    try {
      setOpen(localStorage.getItem(KEY) === "1");
    } catch {
      // storage unavailable: start closed
    }
  }, []);
  useEffect(() => {
    if (open && !facts) loadFacts().then(setFacts).catch((e: Error) => setError(e.message));
  }, [open, facts]);

  const setOpenSaved = (value: boolean) => {
    setOpen(value);
    try {
      localStorage.setItem(KEY, value ? "1" : "0");
    } catch {
      // storage unavailable: keep it in memory only
    }
  };
  const next = [0, 1, 2, 3, 4, 5].find((i) => !done.includes(i));
  const tourSteps = facts ? steps(facts) : [];
  const currentStep = tourSteps[activeStep];
  const toggle = () => {
    if (!open) setActiveStep(next ?? 0);
    setOpenSaved(!open);
  };

  return (
    <div className="fixed bottom-4 right-4 z-[60] w-[min(26rem,calc(100vw-2rem))]">
      {open && (
        <section
          aria-label="Demo walkthrough"
          className="card mb-2 w-full p-4 shadow-xl shadow-navy/10"
        >
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">Demo walkthrough · 6 steps</h2>
            <span className="text-xs text-muted">
              {activeStep + 1}/6 · {done.length}/6 done
            </span>
          </div>
          {error && <p className="text-sm text-high">{error}</p>}
          {!facts && !error && <p className="text-sm text-muted">Loading the examples…</p>}
          {currentStep && (
            <article className={`rounded-xl p-3 ${done.includes(activeStep) ? "bg-accent-soft" : "bg-page"}`}>
              <div className="text-sm font-medium">
                {activeStep + 1}. {currentStep.title}
              </div>
              <Link
                href={currentStep.href}
                onClick={() => {
                  // Close the panel so the selected page is fully visible.
                  setDone((d) => (d.includes(activeStep) ? d : [...d, activeStep]));
                  setOpenSaved(false);
                }}
                className="mt-1.5 inline-block rounded-md bg-accent px-3 py-1 text-xs font-medium text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                {currentStep.cta} →
              </Link>
              <p className="mt-1.5 text-xs leading-5 text-muted">
                <span className="font-medium text-ink">Expected: </span>
                {currentStep.expected}
              </p>
            </article>
          )}
          {facts && (
            <div className="mt-3 flex items-center justify-between gap-2">
              <button
                onClick={() => setActiveStep((step) => Math.max(0, step - 1))}
                disabled={activeStep === 0}
                className="rounded-md border border-line px-3 py-1.5 text-xs font-medium text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <button
                onClick={() => setActiveStep((step) => Math.min(tourSteps.length - 1, step + 1))}
                disabled={activeStep === tourSteps.length - 1}
                className="rounded-md border border-line px-3 py-1.5 text-xs font-medium text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
          {facts && (
            <p className="mt-3 text-[11px] leading-4 text-muted">
              Steps 1–4: {facts.manifest.world}, chosen from validation shops only. All data is synthetic.
            </p>
          )}
        </section>
      )}
      <button
        onClick={toggle}
        aria-expanded={open}
        className="btn-primary ml-auto shadow-lg shadow-primary/25"
      >
        {open
          ? "Close walkthrough"
          : done.length === 0
            ? "Demo walkthrough"
            : next === undefined
              ? "Walkthrough · all 6 done"
              : `Walkthrough · next: step ${next + 1}`}
      </button>
    </div>
  );
}
