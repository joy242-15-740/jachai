"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CategoryIcon, categoryLabel } from "@/components/Brand";
import { BandBadge, PageTitle, Panel, SourceNote } from "@/components/ui";
import { fmtDay, getData, type Source } from "@/lib/api";
import type { CasesResponse } from "@/lib/types";

type Filter = "all" | "high" | "review";
const FILTERS: Filter[] = ["all", "high", "review"];
const FILTER_LABEL: Record<Filter, string> = { all: "All alerts", high: "High priority", review: "Needs review" };

export default function QueuePage() {
  const [data, setData] = useState<CasesResponse | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [bangla, setBangla] = useState(false);

  useEffect(() => {
    // ?band=high|review makes a filtered queue shareable (PRD 6.3: URL state).
    const band = new URLSearchParams(window.location.search).get("band");
    if (band === "high" || band === "review") setFilter(band);
    getData<CasesResponse>("/cases?limit=200", "cases.json")
      .then((r) => {
        setData(r.data);
        setSource(r.source);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  function choose(next: Filter) {
    setFilter(next);
    const url = new URL(window.location.href);
    if (next === "all") url.searchParams.delete("band");
    else url.searchParams.set("band", next);
    window.history.replaceState(null, "", url);
  }

  const rows = useMemo(
    () => (data?.cases ?? []).filter((c) => filter === "all" || c.band === filter),
    [data, filter],
  );

  return (
    <>
      <PageTitle
        title="Alert queue"
        subtitle="Shops that need review, highest risk first. A place in this queue is a request for an analyst to look, not a finding."
      />
      <SourceNote source={source} />
      {error && <p className="text-high">{error}</p>}
      <Panel
        title={data ? `${rows.length} shops · as of ${fmtDay(data.as_of, true)}` : "Loading…"}
        right={
          <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
            <div className="flex rounded-full border border-border bg-canvas p-0.5" role="group" aria-label="Band filter">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  onClick={() => choose(f)}
                  aria-pressed={filter === f}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold ${filter === f ? "bg-primary text-white" : "text-muted hover:text-navy"}`}
                >
                  {FILTER_LABEL[f]}
                </button>
              ))}
            </div>
            <button
              onClick={() => setBangla((b) => !b)}
              className="chip h-8 font-semibold text-muted hover:text-navy"
            >
              {bangla ? "English" : "বাংলা"}
            </button>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="sticky top-0 bg-surface text-[11px] uppercase tracking-wide text-muted">
              <tr className="border-b border-border">
                <th className="py-2 pr-3 font-semibold">Shop</th>
                <th className="py-2 pr-3 font-semibold">Area</th>
                <th className="py-2 pr-3 font-semibold">Fused risk</th>
                <th className="py-2 pr-3 font-semibold">Band</th>
                <th className="py-2 font-semibold">Main reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.case_id} className="border-b border-border/70 align-middle hover:bg-canvas">
                  <td className="py-2.5 pr-3">
                    <Link href={`/cases/${c.case_id}`} className="flex items-center gap-2.5 text-navy hover:text-primary">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-accent-soft text-primary">
                        <CategoryIcon category={c.category} className="h-3.5 w-3.5" />
                      </span>
                      <span>
                        <span className="block font-mono text-xs font-semibold">{c.case_id}</span>
                        <span className="block text-xs text-muted">{categoryLabel(c.category)} · {c.size_tier}</span>
                      </span>
                    </Link>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{c.area_type.replaceAll("_", " ")}</td>
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded-full bg-border">
                        <div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.round(c.risk * 100)}%` }} />
                      </div>
                      <span className="tabular-nums">{c.risk.toFixed(2)}</span>
                    </div>
                  </td>
                  <td className="py-2.5 pr-3">
                    <BandBadge band={c.band} />
                  </td>
                  <td className={`py-2.5 text-ink ${bangla ? "bangla" : ""}`}>
                    {c.top_reason ? (bangla ? c.top_reason.bn : c.top_reason.en) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
