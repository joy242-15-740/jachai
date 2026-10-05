"use client";

import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TimelineDay } from "@/lib/types";

export function Timeline({ days }: { days: TimelineDay[] }) {
  const data = days.map((d) => ({ ...d, label: d.day.slice(5) }));
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeOpacity={0.15} vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis yAxisId="tk" tick={{ fontSize: 11 }} tickFormatter={(v) => `${Math.round(v / 1000)}k`} width={40} />
          <YAxis yAxisId="risk" orientation="right" domain={[0, 1]} tick={{ fontSize: 11 }} width={32} />
          <Tooltip
            formatter={(value, name) =>
              name === "risk" ? Number(value).toFixed(2) : `Tk ${Math.round(Number(value)).toLocaleString("en-US")}`
            }
          />
          <Bar isAnimationActive={false} yAxisId="tk" dataKey="turnover" name="turnover" fill="#0b6e4f" fillOpacity={0.35} radius={[3, 3, 0, 0]} />
          <Line isAnimationActive={false} yAxisId="risk" dataKey="risk" name="risk" stroke="#b83232" strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
