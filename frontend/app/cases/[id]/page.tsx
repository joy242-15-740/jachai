"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { NetworkGraph } from "@/components/NetworkGraph";
import { Timeline } from "@/components/Timeline";
import { BandBadge, PageTitle, Panel, SourceNote } from "@/components/ui";
import { getData, pct, postData, taka, type Source } from "@/lib/api";
import type { CaseDetail, Decision } from "@/lib/types";

const DECISIONS = [
  { id: "clear", label: "Clear", hint: "Genuine business; no action." },
  { id: "monitor", label: "Monitor", hint: "Keep watching for a while." },
  { id: "educate", label: "Educate", hint: "Explain the QR rules to the owner." },
  { id: "convert", label: "Offer agent contract", hint: "Invite the shop to become a licensed agent." },
  { id: "restrict", label: "Restrict", hint: "Recorded for the operations team to act on." },
  { id: "escalate", label: "Escalate", hint: "Send to a senior analyst or compliance." },
] as const;

function fmt(x: number | null | undefined, digits = 2) {
  return x === null || x === undefined ? "—" : x.toFixed(digits);
}

function ScoreCard({ title, value, lines }: { title: string; value: string; lines: string[] }) {
  return (
    <div className="rounded-lg border border-line p-4">
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
      })
      .catch(() => setError("This case is not available (in demo mode only the top 25 cases are bundled)."));
  }, [id]);
  useEffect(load, [load]);

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
      setDecision("");
      load();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (error) return <p className="text-high">{error}</p>;
  if (!data) return <p className="text-muted">Loading…</p>;
  const c = data.scores.components;
  const n = data.neighbourhood;
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

      <div className="grid gap-4 lg:grid-cols-3">
        <ScoreCard
          title="Payment score"
          value={fmt(c.payment_top3_7d)}
          lines={[
            "Riskiest recent payments (0–1), last 7 days",
            `Flagged share: ${c.payment_flag_share_7d == null ? "—" : pct(c.payment_flag_share_7d)}`,
            `Rule flags, last 30 days: ${fmt(c.rules_flags_30d, 0)}`,
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
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Why it needs review (top 3)">
          <ol className="space-y-3">
            {data.reasons.map((r) => (
              <li key={r.code} className="rounded-lg bg-page p-3">
                <div className="text-sm">{r.en}</div>
                <div className="bangla mt-1 text-sm text-muted">{r.bn}</div>
              </li>
            ))}
          </ol>
        </Panel>
        <Panel title="Linked shops">
          <NetworkGraph center={data.case_id} centerBand={data.scores.band} links={n.linked_shops} />
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Last 30 days: turnover (bars) and risk (line)">
          <Timeline days={data.timeline} />
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
          </ul>
        </Panel>

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
                className={`rounded-md border px-3 py-2 text-left text-sm ${decision === d.id ? "border-accent bg-accent-soft" : "border-line hover:bg-page"}`}
              >
                <div className="font-medium">{d.label}</div>
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
          {message && <p className="mt-2 text-sm text-muted">{message}</p>}
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
    </>
  );
}
