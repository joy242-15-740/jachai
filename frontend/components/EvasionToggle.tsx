"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/ui";
import { getData } from "@/lib/api";

// Normal world vs evasion world (misuse amounts made non-round; system NOT
// retrained), for rules only and Jachai with rules. Means over the validation
// seeds, computed here from reports/validation_evaluation.json (via /metrics).

type Row = { group: string; variant: string; [metric: string]: number | string };
type Metrics = { reports: Record<string, { per_seed?: { shop_rows: Row[] }[] }> };

const SYSTEMS = [
  { label: "Rules only", normal: ["baseline", "rules_only"], evasion: ["evasion", "rules_only"] },
  { label: "Jachai with rules", normal: ["system", "fused_risk"], evasion: ["evasion", "fused_risk"] },
] as const;
const METRICS = [
  { key: "pr_auc", label: "Ranking (PR-AUC)" },
  { key: "bands_recall", label: "Misuse shops found at the same budget" },
  { key: "recall_limit_bypass", label: "Limit-bypass rings found" },
] as const;

export function mean(rows: Row[], group: string, variant: string, key: string): number | null {
  const xs = rows
    .filter((r) => r.group === group && r.variant === variant && typeof r[key] === "number")
    .map((r) => r[key] as number);
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
}

export function EvasionToggle() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [world, setWorld] = useState<"normal" | "evasion">("normal");

  useEffect(() => {
    getData<Metrics>("/metrics", "metrics.json")
      .then((r) => {
        const seeds = r.data.reports["validation_evaluation.json"]?.per_seed ?? [];
        setRows(seeds.flatMap((s) => s.shop_rows));
      })
      .catch(() => setRows([]));
  }, []);

  if (!rows) return <Panel title="When misusers adapt">Loading results…</Panel>;
  if (!rows.length) return <Panel title="When misusers adapt">Validation results are not available.</Panel>;
  const seeds = new Set(rows.map((r) => r.seed)).size;

  return (
    <div id="evasion">
      <Panel
        title="When misusers adapt (evasion test)"
        right={
          <div className="flex rounded-full border border-line p-0.5 text-sm" role="group" aria-label="World">
            {(["normal", "evasion"] as const).map((w) => (
              <button
                key={w}
                onClick={() => setWorld(w)}
                aria-pressed={world === w}
                className={`rounded-full px-3 py-1 ${world === w ? "bg-accent text-white" : "text-muted hover:text-ink"}`}
              >
                {w === "normal" ? "Normal world" : "Evasion world"}
              </button>
            ))}
          </div>
        }
      >
        <p className="mb-4 text-sm text-muted">
          Evasion world: misuse payments lowered by Tk 1–99 so none is round, and the system is <strong>not</strong>{" "}
          retrained. Mean over {seeds} validation seeds, from reports/validation_evaluation.md. Synthetic data.
        </p>
        <div className="grid gap-4 md:grid-cols-3">
          {METRICS.map((m) => (
            <div key={m.key} className="glass-inset rounded-2xl p-4">
              <div className="text-xs uppercase tracking-wide text-muted">{m.label}</div>
              {SYSTEMS.map((s) => {
                const normal = mean(rows, s.normal[0], s.normal[1], m.key);
                const [g, v] = world === "normal" ? s.normal : s.evasion;
                const now = mean(rows, g, v, m.key);
                const drop = world === "evasion" && normal != null && now != null ? now - normal : null;
                return (
                  <div key={s.label} className="mt-3">
                    <div className="flex items-baseline justify-between text-sm">
                      <span>{s.label}</span>
                      <span className="text-lg font-semibold tabular-nums">{now == null ? "—" : now.toFixed(2)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded bg-line">
                      <div className="h-1.5 rounded bg-accent" style={{ width: `${Math.round((now ?? 0) * 100)}%` }} />
                    </div>
                    {drop != null && (
                      <div className={`mt-0.5 text-xs tabular-nums ${drop < -0.05 ? "text-high" : "text-muted"}`}>
                        {drop >= 0 ? "+" : ""}
                        {drop.toFixed(2)} vs normal world
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs text-muted">
          On the normal world the rules rank better (they were written from the same typologies as the synthetic
          world; see the circularity note). When amounts stop being round, the rules lose most ring detection while
          Jachai keeps more of it.
        </p>
      </Panel>
    </div>
  );
}
