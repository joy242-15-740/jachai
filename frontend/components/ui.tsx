import type { Band } from "@/lib/types";
import type { Source } from "@/lib/api";
import type { ReactNode } from "react";

const BAND_STYLE: Record<Band, string> = {
  high: "bg-high-soft text-high border-high/30",
  review: "bg-review-soft text-review border-review/30",
  low: "bg-low-soft text-low border-low/30",
};
// Wording: "needs review", never a verdict.
const BAND_LABEL: Record<Band, string> = {
  high: "Needs review (high priority)",
  review: "Needs review",
  low: "No action",
};

export function BandBadge({ band }: { band: Band }) {
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${BAND_STYLE[band]}`}>
      {BAND_LABEL[band]}
    </span>
  );
}

export function Panel({ title, children, right }: { title?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-panel p-5 shadow-sm">
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function SourceNote({ source }: { source: Source | null }) {
  if (source !== "demo") return null;
  return (
    <div className="mb-4 rounded-lg border border-review/30 bg-review-soft px-4 py-2 text-sm text-review">
      Demo mode: the API is not reachable, so this page shows bundled sample data (fast synthetic
      world). Actions are not saved.
    </div>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
    </div>
  );
}
