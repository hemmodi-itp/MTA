"use client";

import { Area, Bar, CartesianGrid, ComposedChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartReveal, useChartAnimation } from "@/components/motion/chart-reveal";

const tick = { fontSize: 11, fill: "var(--muted-foreground)" };

/** 14-day portfolio compliance (line) over evaluation volume (bars); both draw progressively on mount. */
export function ComplianceTrend({ data }: { data: { day: string; level: number | null; score: number | null; runs: number }[] }) {
  const chart = useChartAnimation();
  const rows = data.map((d) => ({ ...d, label: new Date(d.day).toLocaleDateString([], { month: "short", day: "numeric" }) }));
  return (
    <ChartReveal className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 4, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--chart-2)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="trend-stroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="var(--chart-1)" />
              <stop offset="100%" stopColor="var(--chart-2)" />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 6" />
          <XAxis dataKey="label" tick={tick} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={18} />
          <YAxis yAxisId="score" domain={[0, 100]} tick={tick} axisLine={false} tickLine={false} />
          <YAxis yAxisId="runs" orientation="right" hide allowDecimals={false} />
          <Tooltip
            cursor={{ stroke: "var(--border)" }}
            contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 12, fontSize: 12, boxShadow: "var(--elev-popover)", color: "var(--popover-foreground)" }}
            labelStyle={{ color: "var(--muted-foreground)" }}
            formatter={(v, name) => (name === "runs" ? [v, "evaluations"] : [v == null ? "—" : `${v}/100`, "compliance"])}
          />
          <Bar yAxisId="runs" dataKey="runs" fill="var(--chart-2)" fillOpacity={0.18} radius={[4, 4, 0, 0]} barSize={10}
            {...chart} />
          <Area yAxisId="score" type="monotone" dataKey="level" stroke="url(#trend-stroke)" strokeWidth={2.5} fill="url(#trend-fill)"
            connectNulls dot={false} activeDot={{ r: 4 }} {...chart} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartReveal>
  );
}

