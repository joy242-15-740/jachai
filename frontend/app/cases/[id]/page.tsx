"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { CaseView } from "@/components/CaseView";
import { getData, type Source } from "@/lib/api";
import type { CaseDetail } from "@/lib/types";

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CaseDetail | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getData<CaseDetail>(`/cases/${id}`, `case-${id}.json`)
      .then((r) => {
        setData(r.data);
        setSource(r.source);
      })
      .catch(() => setError("This case is not available (in demo mode only the top 25 cases are bundled)."));
  }, [id]);
  useEffect(load, [load]);

  if (error) return <p className="text-high">{error}</p>;
  if (!data) return <p className="text-muted">Loading case…</p>;
  return <CaseView id={id} data={data} source={source} onChanged={load} />;
}
