"use client";

import { useEffect, useState } from "react";
import { PageTitle, Panel, SourceNote } from "@/components/ui";
import { getData, type Source } from "@/lib/api";
import type { CaseDetail, CasesResponse } from "@/lib/types";

export default function NoticePage() {
  const [cases, setCases] = useState<CasesResponse | null>(null);
  const [caseId, setCaseId] = useState<string>("");
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [explanation, setExplanation] = useState("");
  const [channel, setChannel] = useState("app");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    getData<CasesResponse>("/cases?limit=25", "cases.json").then((r) => {
      setCases(r.data);
      setSource(r.source);
      setCaseId(r.data.cases[0]?.case_id ?? "");
    });
  }, []);

  useEffect(() => {
    if (!caseId) return;
    setSent(false);
    getData<CaseDetail>(`/cases/${caseId}`, `case-${caseId}.json`).then((r) => setDetail(r.data));
  }, [caseId]);

  return (
    <>
      <PageTitle
        title="Merchant notice preview"
        subtitle="What a shopkeeper would see if an analyst chooses to contact them. Polite, specific, and never an accusation."
      />
      <SourceNote source={source} />
      <label className="mb-4 block max-w-md text-sm">
        Case
        <select
          value={caseId}
          onChange={(e) => setCaseId(e.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-panel p-2"
        >
          {cases?.cases.slice(0, 25).map((c) => (
            <option key={c.case_id} value={c.case_id}>
              {c.case_id} · {c.category.replaceAll("_", " ")} · {c.area_type.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>

      {detail && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="বাংলা (notice)">
            <div className="bangla whitespace-pre-line text-[15px] leading-7">
              {detail.brief.merchant_notice_bn}
            </div>
            <p className="mt-3 text-xs text-muted">Source: local validated template. Never sent to an LLM.</p>
          </Panel>
          <Panel title="English analyst note">
            <div className="whitespace-pre-line text-sm leading-6">{detail.brief.analyst_note}</div>
            <p className="mt-3 text-xs text-muted">
              Source: {detail.brief.analyst_note_source === "llm" ? "validated LLM rewording" : "template fallback"}.
              The analyst, not the text generator, decides.
            </p>
          </Panel>
        </div>
      )}

      <div className="mt-4 max-w-2xl">
        <Panel title="আপিল / ব্যাখ্যা ফর্ম (appeal form)">
          {sent ? (
            <p className="bangla text-sm">
              ধন্যবাদ। আপনার ব্যাখ্যা গ্রহণ করা হয়েছে। (Preview only: nothing was sent.)
            </p>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setSent(true);
              }}
              className="space-y-3"
            >
              <label className="bangla block text-sm">
                আপনার ব্যাখ্যা (Your explanation)
                <textarea
                  required
                  minLength={10}
                  value={explanation}
                  onChange={(e) => setExplanation(e.target.value)}
                  rows={4}
                  placeholder="যেমন: আমি পাইকারি দোকান, তাই বড় অঙ্কের অর্ডার আসে।"
                  className="mt-1 w-full rounded-md border border-line bg-panel p-2"
                />
              </label>
              <label className="bangla block text-sm">
                উত্তর পেতে চান (Reply by)
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value)}
                  className="mt-1 w-full rounded-md border border-line bg-panel p-2"
                >
                  <option value="app">upay অ্যাপ নোটিফিকেশন (app notification)</option>
                  <option value="visit">এজেন্ট/প্রতিনিধির সাথে সাক্ষাৎ (visit by a representative)</option>
                </select>
              </label>
              <button className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white">
                জমা দিন (Submit)
              </button>
              <p className="text-xs text-muted">
                Preview only: this demo does not send or store appeals, and asks for no personal data.
              </p>
            </form>
          )}
        </Panel>
      </div>
    </>
  );
}
