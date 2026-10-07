import { Check, Eye, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { Source } from "@/lib/api";
import type { Band } from "@/lib/types";

// Risk chip: icon + label, never colour alone, never the word "fraud".
const BAND: Record<Band, { label: string; className: string; Icon: typeof Eye }> = {
  high: { label: "High priority", className: "bg-high-soft text-high border-high/25", Icon: TriangleAlert },
  review: { label: "Needs review", className: "bg-review-soft text-review border-review/25", Icon: Eye },
  low: { label: "No action", className: "bg-low-soft text-low border-low/25", Icon: Check },
};

export function BandBadge({ band }: { band: Band }) {
  const { label, className, Icon } = BAND[band];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${className}`}>
      <Icon aria-hidden="true" className="h-3 w-3" />
      {label}
    </span>
  );
}

export function Panel({
  title,
  children,
  right,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-5 lg:p-6 ${className}`}>
      {(title || right) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-navy">{title}</h2>}
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
    <div className="card-inset mb-5 flex items-start gap-3 px-4 py-3 text-sm text-ink" role="status">
      <Info aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <span>
        <span className="font-semibold">Demo mode.</span> The API is not reachable, so this page shows
        bundled sample data from the fast synthetic world. Actions are not saved.
      </span>
    </div>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-7">
      <div className="eyebrow mb-2">Integrity workspace</div>
      <h1 className="display text-3xl font-semibold text-navy sm:text-4xl">{title}</h1>
      {subtitle && <p className="mt-2 max-w-3xl text-sm leading-6 text-muted sm:text-[15px]">{subtitle}</p>}
    </div>
  );
}

/** Small "Synthetic demo data" marker (PRD 8.1): shown wherever numbers appear. */
export function SyntheticBadge({ className = "" }: { className?: string }) {
  return (
    <span className={`chip text-muted ${className}`} title="Every number on this page comes from a generated world">
      <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-primary" />
      Synthetic demo data
    </span>
  );
}
