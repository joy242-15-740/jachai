"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { NetworkGraph } from "@/components/NetworkGraph";
import { Timeline } from "@/components/Timeline";
import { BandBadge, PageTitle, Panel, SourceNote } from "@/components/ui";
import { getData, pct, postData, taka, type Source } from "@/lib/api";
import type { CaseDetail, Decision, TimelineDay } from "@/lib/types";

// The case page answers three questions, in order:
//   1. What happened?  plain-language facts computed from the shop's own timeline
//   2. Why risky?      top-3 reasons (English + Bangla) and the separate scores
//   3. What next?      the configured recommendation, the agent option, the decision
// Every number shown comes from the API (live) or its exported demo JSON.

const DECISIONS = [
  { id: "clear", label: "Clear", hint: "Genuine business; no action." },
  { id: "monitor", label: "Monitor", hint: "Keep watching for a while." },
  { id: "educate", label: "Educate", hint: "Explain the QR rules to the owner." },
  { id: "convert", label: "Offer agent contract", hint: "Invite the shop to become a licensed agent." },
  { id: "restrict", label: "Restrict", hint: "Recorded for the operations team to act on." },
  { id: "escalate", label: "Escalate", hint: "Send to a senior analyst or compliance." },
] as const;

const ACTION_LABEL: Record<string, string> = Object.fromEntries(DECISIONS.map((d) => [d.id, d.label]));

function fmt(x: number | null | undefined, digits = 2) {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}

/** Plain-language facts from the 30-day timeline (all computed here, nothing typed). */
function whatHappened(days: TimelineDay[], expectedDaily: number | null): string[] {
  if (!days.length) return ["No QR activity is available for this shop in the last 30 days."];
  const payments = days.reduce((a, d) => a + d.payments, 0);
  const turnover = days.reduce((a, d) => a + d.turnover, 0);
  const flagged = days.reduce((a, d) => a + d.flagged, 0);
  const peak = days.reduce((a, d) => (d.turnover > a.turnover ? d : a), days[0]);
  const firstAlert = days.find((d) => d.band !== "low");
  const avg = turnover / days.length;
  const lines = [
    `In the last ${days.length} days the shop received ${payments.toLocaleString("en-US")} QR payments worth ${taka(turnover)} (about ${taka(avg)} a day).`,
  ];
  if (expectedDaily) {
    const ratio = avg / expectedDaily;
    lines.push(
      `A shop of this type, size and area usually takes about ${taka(expectedDaily)} a day, so over these ${days.length} days it ran at ${ratio.toFixed(1)}× the usual level (the shop score below looks at the last 7 days only).`,
    );
  }
  lines.push(`The busiest day was ${peak.day} with ${taka(peak.turnover)}.`);
  lines.push(
    flagged
      ? `${flagged.toLocaleString("en-US")} of its payments were above the payment model's review threshold.`
      : "None of its payments were above the payment model's review threshold.",
  );
  lines.push(
    firstAlert
      ? `It first entered the ${firstAlert.band} band on ${firstAlert.day}.`
      : "It stayed in the low band throughout.",
  );
  return lines;
}

function ScoreCard({ title, value, lines, tone }: { title: string; value: string; lines: string[]; tone?: string }) {
  return (
    <div className={`glass-inset rounded-2xl p-4 ${tone ?? ""}`}>
      <div className="text-xs uppercase tracking-wide text-muted">{title}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      <ul className="mt-2 space-y-0.5 text-xs text-muted">
        {lines.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8" aria-labelledby={`step-${n}`}>
      <h2 id={`step-${n}`} className="mb-3 flex items-center gap-3 text-lg font-semibold">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-sm text-white">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<string>("");
  const [reason, setReason] = useState("");
  const [analyst, setAnalyst] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    getData<CaseDetail>(`/cases/${id}`, `case-${id}.json`)
      .then((r) => {
        setData(r.data);
        setSource(r.source);
        if (r.data.recommendation) setDecision((d) => d || r.data.recommendation!.action);
      })
      .catch(() => setError("This case is not available (in demo mode only the top 25 cases are bundled)."));
  }, [id]);
  useEffect(load, [load]);

  const facts = useMemo(
    () => (data ? whatHappened(data.timeline, data.scores.expected_daily_turnover) : []),
    [data],
  );

  async function submit() {
    setSaving(true);
    setMessage(null);
    try {
      const row = await postData<Decision & { note: string }>(`/cases/${id}/decision`, {
        decision,
        reason,
        analyst,
      });
      setMessage(row.note);
      setReason("");
      load();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (error) return <p className="text-high">{error}</p>;
  if (!data) return <p className="text-muted">Loading case…</p>;
  const c = data.scores.components;
  const n = data.neighbourhood;
  const rec = data.recommendation;
  const canSubmit = source === "live" && decision && reason.trim().length >= 10 && analyst.trim();

  return (
    <>
      <Link href="/queue" className="text-sm text-accent hover:underline">
        ← Alert queue
      </Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <PageTitle
          title={`Shop ${data.case_id}`}
          subtitle={`${String(data.shop.category).replaceAll("_", " ")} · ${String(data.shop.size_tier)} · ${String(data.shop.area_type).replaceAll("_", " ")} · zone ${data.shop.zone_id} · ${data.shop.n_qr_codes} QR codes · scores as of ${data.scores.as_of}`}
        />
        <div className="text-right">
          <BandBadge band={data.scores.band} />
          <div className="mt-1 text-sm text-muted">
            Fused risk <span className="font-semibold text-ink tabular-nums">{data.scores.risk.toFixed(2)}</span>
          </div>
        </div>
      </div>
      <SourceNote source={source} />

      {/* 1. What happened */}
      <Step n={1} title="What happened">
        <div className="grid gap-4 lg:grid-cols-[2fr_3fr]">
          <Panel title="In plain words">
            <ul className="space-y-2 text-sm leading-6">
              {facts.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </Panel>
          <Panel title="Last 30 days: turnover (bars) and risk (line)">
            <Timeline days={data.timeline} />
          </Panel>
        </div>
      </Step>

      {/* 2. Why risky */}
      <Step n={2} title="Why it needs review">
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Top 3 reasons (evidence from this shop's data)">
            <ol className="space-y-3">
              {data.reasons.map((r) => (
                <li key={r.code} className="rounded-lg bg-page p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm">{r.en}</div>
                    <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-xs tabular-nums text-accent">
                      {data.scores.risk ? pct(r.weight / data.scores.risk) : "—"} of risk
                    </span>
                  </div>
                  <div className="bangla mt-1 text-sm text-muted">{r.bn}</div>
                </li>
              ))}
            </ol>
          </Panel>
          <Panel title="Linked shops (payers shared on heavy days)">
            <NetworkGraph center={data.case_id} centerBand={data.scores.band} links={n.linked_shops} />
          </Panel>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <ScoreCard
            title="Payment score"
            value={fmt(c.payment_top3_7d)}
            lines={[
              "Riskiest recent payments (0–1), last 7 days",
              `Flagged share: ${c.payment_flag_share_7d == null ? "—" : pct(c.payment_flag_share_7d)}`,
            ]}
          />
          <ScoreCard
            title="Shop score"
            value={fmt(c.turnover_z, 1)}
            lines={[
              "Turnover vs a shop like this (z-score)",
              `Expected about ${data.scores.expected_daily_turnover == null ? "—" : taka(data.scores.expected_daily_turnover)}/day`,
              `Unusual among peers: ${fmt(c.peer_anomaly)}`,
            ]}
          />
          <ScoreCard
            title="Network score"
            value={String(n.linking_payers ?? 0)}
            lines={[
              "Payers linking it to other shops on heavy days",
              `Group size: ${n.community_size ?? 1} · ring pattern: ${n.ring_flag ? "yes" : "no"}`,
              `Payers living far away: ${c.distant_payer_share == null ? "—" : pct(c.distant_payer_share)}`,
            ]}
          />
          <ScoreCard
            title="Rules flag (separate)"
            value={fmt(c.rules_flags_30d, 0)}
            lines={["Payments the fixed rules flagged, last 30 days", "Shown on its own: rules are one input, not the verdict"]}
          />
        </div>
        <div className="mt-4">
          <Panel title="Riskiest recent payments">
            <ul className="divide-y divide-line text-sm">
              {data.riskiest_payments.map((p) => (
                <li key={p.payment_id} className="py-2">
                  <div className="flex justify-between">
                    <span className="tabular-nums">{taka(p.amount)}</span>
                    <span className="text-muted">
                      {p.ts.replace("T", " ").slice(0, 16)} · score {p.score.toFixed(2)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-muted">{p.reasons.map((r) => r.en).join(" ")}</div>
                </li>
              ))}
              {!data.riskiest_payments.length && <li className="py-2 text-muted">No payments in the last 30 days.</li>}
            </ul>
          </Panel>
        </div>
      </Step>

      {/* 3. What next */}
      <Step n={3} title="What next">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            {rec && (
              <Panel title="Recommended next step">
                <div className="text-lg font-semibold">{ACTION_LABEL[rec.action] ?? rec.action}</div>
                <p className="mt-1 text-sm leading-6">{rec.en}</p>
                <p className="bangla mt-1 text-sm text-muted">{rec.bn}</p>
                <p className="mt-2 text-xs text-muted">{rec.note}</p>
              </Panel>
            )}
            {rec && rec.convert_offer !== "none" && (
              <Panel
                title={
                  rec.convert_offer === "recommended"
                    ? "Turn the leak into a licensed agent"
                    : "Possible agent lead, not the recommendation"
                }
              >
                <p className="text-sm leading-6">
                  Estimated cash-out demand at this shop: about <strong>{taka(rec.estimated_cash_out_demand_30d)}</strong> of
                  flagged payments in 30 days. If the analyst confirms cash-out, an agent contract moves that demand into
                  a licensed, fee-earning channel instead of shutting it down.
                </p>
                <button
                  onClick={() => setDecision("convert")}
                  className="mt-3 rounded-md border border-accent px-3 py-1.5 text-sm text-accent hover:bg-accent-soft"
                >
                  Choose “Offer agent contract”
                </button>
              </Panel>
            )}
            <Panel title="Analyst case note">
              <div className="whitespace-pre-line text-sm leading-6">{data.brief.analyst_note}</div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span className="rounded-full bg-page px-2 py-1">
                  Source: {data.brief.analyst_note_source === "llm" ? "LLM rewording" : "validated template"}
                </span>
                <span>Evidence only · no automatic decision</span>
              </div>
            </Panel>
          </div>

          <Panel title="Decision">
            {source !== "live" && (
              <p className="mb-3 text-sm text-review">Decisions need the live API (demo mode is read-only).</p>
            )}
            <div className="grid grid-cols-2 gap-2">
              {DECISIONS.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setDecision(d.id)}
                  title={d.hint}
                  aria-pressed={decision === d.id}
                  className={`rounded-md border px-3 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-accent ${decision === d.id ? "border-accent bg-accent-soft" : "border-line hover:bg-page"}`}
                >
                  <div className="font-medium">
                    {d.label}
                    {rec?.action === d.id && <span className="ml-1 text-xs text-accent">(recommended)</span>}
                  </div>
                  <div className="text-xs text-muted">{d.hint}</div>
                </button>
              ))}
            </div>
            <label className="mt-3 block text-sm">
              Reason (required, at least 10 characters)
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                className="mt-1 w-full rounded-md border border-line bg-panel p-2 text-sm"
              />
            </label>
            <label className="mt-2 block text-sm">
              Analyst ID
              <input
                value={analyst}
                onChange={(e) => setAnalyst(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-panel p-2 text-sm"
              />
            </label>
            <button
              disabled={!canSubmit || saving}
              onClick={submit}
              className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {saving ? "Saving…" : "Record decision"}
            </button>
            {message && <p className="mt-2 text-sm text-muted" role="status">{message}</p>}
            <p className="mt-2 text-xs text-muted">
              Decisions are kept in an append-only log. No decision blocks anything automatically.
            </p>

            <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-muted">History</h3>
            {data.decisions.length === 0 ? (
              <p className="text-sm text-muted">No decisions yet.</p>
            ) : (
              <ul className="mt-1 space-y-2 text-sm">
                {data.decisions.map((d) => (
                  <li key={d.id} className="rounded-md bg-page p-2">
                    <span className="font-medium">{d.decision}</span> by {d.analyst} ·{" "}
                    <span className="text-muted">{d.created_at.replace("T", " ").slice(0, 16)}</span>
                    <div className="text-muted">{d.reason}</div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </Step>
    </>
  );
}
