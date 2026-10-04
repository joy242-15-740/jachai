import type { Band } from "@/lib/types";

// Radial view: the case shop in the middle, shops linked to it by payers who paid
// both on the same heavy day (past the daily limit across several shops) around it.
// Line thickness = how many such payers they share. Plain SVG, no graph library.

const FILL: Record<Band, string> = { high: "#b83232", review: "#b7791f", low: "#3e7c59" };

export function NetworkGraph({
  center,
  centerBand,
  links,
}: {
  center: string;
  centerBand: Band;
  links: { shop_id: string; shared_payers: number; band: Band }[];
}) {
  const size = 320;
  const c = size / 2;
  const r = 115;
  const maxShared = Math.max(1, ...links.map((l) => l.shared_payers));
  if (!links.length) {
    return (
      <p className="text-sm text-muted">
        No shops share heavy same-day payers with this one in the last 30 days.
      </p>
    );
  }
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto h-80 w-full max-w-sm" role="img" aria-label="Linked shops">
      {links.map((l, i) => {
        const a = (2 * Math.PI * i) / links.length - Math.PI / 2;
        const x = c + r * Math.cos(a);
        const y = c + r * Math.sin(a);
        return (
          <g key={l.shop_id}>
            <line x1={c} y1={c} x2={x} y2={y} stroke="currentColor" strokeOpacity={0.35} strokeWidth={1 + (4 * l.shared_payers) / maxShared} />
            <circle cx={x} cy={y} r={14} fill={FILL[l.band]} />
            <text x={x} y={y + 28} textAnchor="middle" className="fill-current text-[9px]">
              {l.shop_id.slice(0, 8)}
            </text>
            <text x={(c + x) / 2} y={(c + y) / 2 - 4} textAnchor="middle" className="fill-current text-[9px]">
              {l.shared_payers}
            </text>
          </g>
        );
      })}
      <circle cx={c} cy={c} r={20} fill={FILL[centerBand]} stroke="white" strokeWidth={3} />
      <text x={c} y={c + 36} textAnchor="middle" className="fill-current text-[10px] font-semibold">
        {center.slice(0, 8)}
      </text>
    </svg>
  );
}
