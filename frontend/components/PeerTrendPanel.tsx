"use client";

import { useEffect, useState } from "react";
import { getData, type Source } from "@/lib/api";
import { Panel } from "@/components/ui";

// Compact case-page cue. Numbers come from GET /shops/{id}/peer-trend.
// A rising flag does not change the three scores and does not block the shop.

interface Percentile {
  metric: string;
  en: string;
  bn: string;
  value: number | null;
  percentile: number | null;
}

interface DayScore {
  day: string;
  score: number | null;
}

interface PeerTrend {
  available: boolean;
  shop_id: string;
  as_of?: string;
  peer_group?: { category: string; area_type: string; size_tier: string; shops: number | null };
  percentiles?: Percentile[];
  history?: DayScore[];
  forecast?: DayScore[];
  rising?: boolean;
  early_warning?: boolean;
  slope_per_day?: number | null;
  payment_threshold?: number;
  today_score?: number | null;
  reason_en?: string;
  note_en?: string;
  note_bn?: string;
}

function num(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

function Spark({ history, forecast }: { history: DayScore[]; forecast: DayScore[] }) {
  const points = [...history, ...forecast];
  const values = points.map((p) => p.score).filter((v): v is number => v !== null);
  if (values.length < 2) return <p className="text-xs text-muted">Not enough days to draw.</p>;
  const w = 280;
  const h = 64;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const span = max - min || 1;
  const coords = points.map((p, i) => {
    const x = (i / Math.max(points.length - 1, 1)) * (w - 8) + 4;
    const y = p.score === null ? null : h - 6 - ((p.score - min) / span) * (h - 16);
    return { x, y, forecast: i >= history.length };
  });
  const line = (forecast: boolean) =>
    coords
      .filter((p) => p.y !== null && p.forecast === forecast)
      .map((p) => `${p.x},${p.y}`)
      .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 h-16 w-full" role="img" aria-label="14-day score and 7-day line">
      <polyline fill="none" stroke="currentColor" strokeWidth="2" points={line(false)} className="text-accent" />
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="4 3"
        points={line(true)}
        className="text-review"
      />
    </svg>
  );
}

export function PeerTrendPanel({ shopId }: { shopId: string }) {
  const [data, setData] = useState<PeerTrend | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let live = true;
    getData<PeerTrend>(`/shops/${shopId}/peer-trend`, `peer-trend-${shopId}.json`)
      .then((result) => {
        if (!live) return;
        setData(result.data);
        setSource(result.source);
      })
      .catch(() => {
        if (live) setMissing(true);
      });
    return () => {
      live = false;
    };
  }, [shopId]);

  return (
    <Panel title="Peer and trend · সহপাঠী ও ধারা">
      {missing && (
        <p className="text-sm text-muted">
          This panel needs the live API. The bundled demo does not include a score series for this shop.
        </p>
      )}
      {!missing && !data && <p className="text-sm text-muted">Loading peer and trend…</p>}
      {data && !data.available && <p className="text-sm text-muted">{data.reason_en}</p>}
      {data?.available && (
        <div className="space-y-3 text-sm">
          <p className="text-xs text-muted">
            Similar shops ({data.peer_group?.shops ?? "—"}): {String(data.peer_group?.category).replaceAll("_", " ")} ·{" "}
            {String(data.peer_group?.area_type).replaceAll("_", " ")} · {data.peer_group?.size_tier}
            {source === "demo" ? " · demo file" : ""}
          </p>
          <ul className="space-y-2">
            {(data.percentiles ?? []).map((row) => (
              <li key={row.metric} className="flex items-baseline justify-between gap-3">
                <span>
                  <span className="block">{row.en}</span>
                  <span className="bangla block text-xs text-muted">{row.bn}</span>
                </span>
                <span className="shrink-0 text-right tabular-nums">
                  {row.percentile === null ? "—" : row.percentile.toFixed(0)}
                  <span className="block text-xs text-muted">percentile · শতাংশ</span>
                </span>
              </li>
            ))}
          </ul>
          {data.history && data.forecast && <Spark history={data.history} forecast={data.forecast} />}
          <p>
            <span className="font-medium">{data.rising ? "Rising risk" : "Not rising"}</span>
            <span className="bangla text-muted"> · {data.rising ? "ঝুঁকি বাড়ছে" : "ঝুঁকি বাড়ছে না"}</span>
            <span className="mt-1 block text-xs text-muted">
              Today {num(data.today_score)} · threshold {num(data.payment_threshold)} · slope/day{" "}
              {num(data.slope_per_day, 3)}
              {data.early_warning ? " · still under the threshold" : ""}
            </span>
          </p>
          <p className="text-xs leading-5 text-muted">{data.note_en}</p>
          <p className="bangla text-xs leading-5 text-muted">{data.note_bn}</p>
        </div>
      )}
    </Panel>
  );
}
