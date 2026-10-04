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
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${BAND_STYLE[band]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {BAND_LABEL[band]}
    </span>
  );
}

export function Panel({ title, children, right }: { title?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="glass-panel rounded-2xl p-5 lg:p-6">
      {(title || right) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">{title}</h2>}
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
    <div className="glass-inset mb-5 flex items-start gap-3 rounded-xl px-4 py-3 text-sm text-review">
      <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-review-soft text-xs font-bold">i</span>
      <span>
        Demo mode: the API is not reachable, so this page shows bundled sample data (fast synthetic
        world). Actions are not saved.
      </span>
    </div>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-7">
      <div className="eyebrow mb-2">Integrity workspace</div>
      <h1 className="text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">{title}</h1>
      {subtitle && <p className="mt-2 max-w-3xl text-sm leading-6 text-muted sm:text-[15px]">{subtitle}</p>}
    </div>
  );
}
