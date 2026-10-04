"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BandBadge, PageTitle, Panel, SourceNote } from "@/components/ui";
import { getData, type Source } from "@/lib/api";
import type { CasesResponse } from "@/lib/types";

type Filter = "all" | "high" | "review";

export default function QueuePage() {
  const [data, setData] = useState<CasesResponse | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [bangla, setBangla] = useState(false);

  useEffect(() => {
    getData<CasesResponse>("/cases?limit=200", "cases.json")
      .then((r) => {
        setData(r.data);
        setSource(r.source);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

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
        title={data ? `${rows.length} shops · as of ${data.as_of}` : "Loading…"}
        right={
          <div className="flex items-center gap-2 text-sm">
            {(["all", "high", "review"] as Filter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-md px-3 py-1 ${filter === f ? "bg-accent text-white" : "text-muted hover:bg-accent-soft"}`}
              >
                {f === "all" ? "All alerts" : f === "high" ? "High priority" : "Review"}
              </button>
            ))}
            <button
              onClick={() => setBangla((b) => !b)}
              className="ml-2 rounded-md border border-line px-3 py-1 text-muted hover:text-ink"
            >
              {bangla ? "English" : "বাংলা"}
            </button>
          </div>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-muted">
              <tr className="border-b border-line">
                <th className="py-2 pr-3">Shop</th>
                <th className="py-2 pr-3">Type</th>
                <th className="py-2 pr-3">Area</th>
                <th className="py-2 pr-3">Risk</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2">Main reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.case_id} className="border-b border-line/60 align-top hover:bg-page">
                  <td className="py-2 pr-3 font-mono text-xs">
                    <Link href={`/cases/${c.case_id}`} className="text-accent hover:underline">
                      {c.case_id}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">{c.category.replaceAll("_", " ")}</td>
                  <td className="py-2 pr-3">{c.area_type.replaceAll("_", " ")}</td>
                  <td className="py-2 pr-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded bg-line">
                        <div className="h-1.5 rounded bg-accent" style={{ width: `${Math.round(c.risk * 100)}%` }} />
                      </div>
                      <span className="tabular-nums">{c.risk.toFixed(2)}</span>
                    </div>
                  </td>
                  <td className="py-2 pr-3">
                    <BandBadge band={c.band} />
                  </td>
                  <td className={`py-2 ${bangla ? "bangla" : ""}`}>
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
