"use client";
import * as React from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { formatDate, formatMoney, formatPct, toNum, type MoneyStr } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

export const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)", "var(--chart-7)", "var(--chart-8)"];

function TooltipCard({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-line bg-card/95 px-3 py-2 text-[12px] shadow-pop backdrop-blur">{children}</div>;
}

const axisTick = { fill: "var(--faint)", fontSize: 11 };

function useCompactTick(currency: string) {
  const hidden = useUi((s) => s.privacy);
  return (v: number) => (hidden ? "" : formatMoney(String(v), currency, { compact: true }));
}

function dateTick(range: string) {
  return (v: string) => formatDate(v, range === "1M" ? "d MMM" : range === "ALL" || range === "1Y" ? "MMM yy" : "d MMM");
}

/** Hero net-worth area chart: hover/touch reveals exact value for each date. */
export function NetWorthArea({ points, currency, range, onHover, height = 220 }: {
  points: { date: string; net_worth: MoneyStr }[]; currency: string; range: string; height?: number;
  onHover?: (p: { date: string; value: MoneyStr } | null) => void;
}) {
  const hidden = useUi((s) => s.privacy);
  const data = React.useMemo(() => points.map((p) => ({ date: p.date, v: toNum(p.net_worth), raw: p.net_worth })), [points]);
  const up = data.length > 1 ? data[data.length - 1].v >= data[0].v : true;
  const color = up ? "var(--chart-1)" : "var(--neg)";
  const id = up ? "nwgrad-up" : "nwgrad-down";
  return (
    <div style={{ height }} className="-mx-1">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}
          onMouseMove={(s) => { const i = s?.activeTooltipIndex; if (onHover && typeof i === "number" && data[i]) onHover({ date: data[i].date, value: data[i].raw }); }}
          onMouseLeave={() => onHover?.(null)}>
          <defs>
            <linearGradient id={`nw-${id}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tickFormatter={dateTick(range)} tick={axisTick} axisLine={false} tickLine={false} minTickGap={48} dy={6} />
          <YAxis hide domain={["dataMin - 1000", "dataMax + 1000"]} />
          <Tooltip cursor={{ stroke: "var(--line-strong)", strokeDasharray: "3 3" }}
            content={({ active, payload }) => active && payload?.[0] ? (
              <TooltipCard>
                <p className="text-muted">{formatDate(payload[0].payload.date, "EEE, d MMM yyyy")}</p>
                <p className="mt-0.5 text-[13px] font-semibold tabular text-ink">{formatMoney(payload[0].payload.raw, currency, { hidden })}</p>
              </TooltipCard>
            ) : null} />
          <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#nw-${id})`} isAnimationActive={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)", fill: color }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function WealthLines({ points, currency, range, series }: {
  points: { date: string; net_worth: MoneyStr; assets: MoneyStr; liabilities: MoneyStr }[]; currency: string; range: string;
  series: { key: "net_worth" | "assets" | "liabilities"; label: string; color: string; on: boolean }[];
}) {
  const hidden = useUi((s) => s.privacy);
  const tick = useCompactTick(currency);
  const data = React.useMemo(() => points.map((p) => ({ date: p.date, net_worth: toNum(p.net_worth), assets: toNum(p.assets), liabilities: toNum(p.liabilities), raw: p })), [points]);
  return (
    <div className="h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="date" tickFormatter={dateTick(range)} tick={axisTick} axisLine={false} tickLine={false} minTickGap={48} dy={6} />
          <YAxis tickFormatter={tick} tick={axisTick} axisLine={false} tickLine={false} width={64} />
          <Tooltip cursor={{ stroke: "var(--line-strong)", strokeDasharray: "3 3" }}
            content={({ active, payload }) => active && payload?.length ? (
              <TooltipCard>
                <p className="mb-1 text-muted">{formatDate(payload[0].payload.date, "d MMM yyyy")}</p>
                {series.filter((s) => s.on).map((s) => (
                  <p key={s.key} className="flex items-center justify-between gap-6 tabular">
                    <span className="flex items-center gap-1.5 text-ink-2"><span className="size-2 rounded-full" style={{ background: s.color }} />{s.label}</span>
                    <span className="font-medium text-ink">{formatMoney(payload[0].payload.raw[s.key], currency, { hidden })}</span>
                  </p>
                ))}
              </TooltipCard>
            ) : null} />
          {series.filter((s) => s.on).map((s) => (
            <Line key={s.key} type="monotone" dataKey={s.key} stroke={s.color} strokeWidth={s.key === "net_worth" ? 2.25 : 1.75}
              strokeDasharray={s.key === "liabilities" ? "5 4" : undefined} dot={false} activeDot={{ r: 3.5 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Donut({ data, currency, centerLabel, centerValue, onSelect, selected, size = 220 }: {
  data: { key: string; label: string; value: MoneyStr; share: MoneyStr; color?: string }[]; currency: string;
  centerLabel: string; centerValue: MoneyStr; onSelect?: (key: string | null) => void; selected?: string | null; size?: number;
}) {
  const hidden = useUi((s) => s.privacy);
  const [hover, setHover] = React.useState<number | null>(null);
  const rows = data.filter((d) => toNum(d.value) > 0).map((d, i) => ({ ...d, v: toNum(d.value), color: d.color ?? PALETTE[i % PALETTE.length] }));
  const activeIdx = hover ?? (selected ? rows.findIndex((r) => r.key === selected) : -1);
  const active = activeIdx >= 0 ? rows[activeIdx] : null;
  return (
    <div className="relative mx-auto" style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={rows} dataKey="v" nameKey="label" innerRadius="68%" outerRadius="92%" paddingAngle={1.5} cornerRadius={4}
            stroke="none" animationDuration={600}
            onMouseEnter={(_, i) => setHover(i)} onMouseLeave={() => setHover(null)}
            onClick={(_, i) => onSelect?.(rows[i].key === selected ? null : rows[i].key)}
            className={cn(onSelect && "cursor-pointer")}>
            {rows.map((r) => <Cell key={r.key} fill={r.color} opacity={activeIdx >= 0 && rows[activeIdx].key !== r.key ? 0.45 : 1} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
        <p className="max-w-[60%] truncate text-[11px] font-medium uppercase tracking-wider text-muted">{active ? active.label : centerLabel}</p>
        <p className="mt-0.5 text-lg font-semibold tabular text-ink">{formatMoney(active ? active.value : centerValue, currency, { hidden, decimals: 0 })}</p>
        {active && <p className="text-[12px] tabular text-muted">{formatPct(active.share, { decimals: 1 })}</p>}
      </div>
    </div>
  );
}

export function CashflowBars({ months, currency, height = 280 }: {
  months: { month: string; income: MoneyStr; expenses: MoneyStr; net: MoneyStr; partial?: boolean }[]; currency: string; height?: number;
}) {
  const hidden = useUi((s) => s.privacy);
  const tick = useCompactTick(currency);
  const data = months.map((m) => ({ ...m, i: toNum(m.income), e: toNum(m.expenses), n: toNum(m.net) }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }} barGap={3}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="month" tickFormatter={(v) => formatDate(`${v}-01`, "MMM")} tick={axisTick} axisLine={false} tickLine={false} dy={6} />
          <YAxis tickFormatter={tick} tick={axisTick} axisLine={false} tickLine={false} width={60} />
          <ReferenceLine y={0} stroke="var(--line-strong)" />
          <Tooltip cursor={{ fill: "var(--bg-subtle)" }}
            content={({ active, payload }) => active && payload?.length ? (
              <TooltipCard>
                <p className="mb-1 text-muted">{formatDate(`${payload[0].payload.month}-01`, "MMMM yyyy")}{payload[0].payload.partial ? " (month to date)" : ""}</p>
                {([["Income", "income", "var(--chart-1)"], ["Expenses", "expenses", "var(--chart-4)"], ["Net cash flow", "net", "var(--ink)"]] as const).map(([l, k, c]) => (
                  <p key={k} className="flex items-center justify-between gap-6 tabular">
                    <span className="flex items-center gap-1.5 text-ink-2"><span className="size-2 rounded-full" style={{ background: c }} />{l}</span>
                    <span className="font-medium text-ink">{formatMoney(payload[0].payload[k], currency, { hidden, signed: k === "net" })}</span>
                  </p>
                ))}
              </TooltipCard>
            ) : null} />
          <Legend verticalAlign="top" align="right" height={28} iconType="circle" iconSize={8}
            formatter={(v) => <span className="text-[12px] text-ink-2">{v}</span>} />
          <Bar name="Income" dataKey="i" fill="var(--chart-1)" radius={[5, 5, 0, 0]} maxBarSize={22} animationDuration={500} />
          <Bar name="Expenses" dataKey="e" fill="var(--chart-4)" radius={[5, 5, 0, 0]} maxBarSize={22} animationDuration={500} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function StackedCategoryBars({ months, keys, currency }: {
  months: { month: string; categories: Record<string, MoneyStr> }[]; keys: { slug: string; name: string; color: string }[]; currency: string;
}) {
  const hidden = useUi((s) => s.privacy);
  const tick = useCompactTick(currency);
  const data = months.map((m) => ({ month: m.month, ...Object.fromEntries(keys.map((k) => [k.slug, toNum(m.categories[k.slug])])) }));
  return (
    <div className="h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis dataKey="month" tickFormatter={(v) => formatDate(`${v}-01`, "MMM")} tick={axisTick} axisLine={false} tickLine={false} dy={6} />
          <YAxis tickFormatter={tick} tick={axisTick} axisLine={false} tickLine={false} width={60} />
          <Tooltip cursor={{ fill: "var(--bg-subtle)" }}
            content={({ active, payload }) => active && payload?.length ? (
              <TooltipCard>
                <p className="mb-1 text-muted">{formatDate(`${payload[0].payload.month}-01`, "MMMM yyyy")}</p>
                {[...payload].reverse().map((p) => (
                  <p key={String(p.dataKey)} className="flex items-center justify-between gap-6 tabular">
                    <span className="flex items-center gap-1.5 text-ink-2"><span className="size-2 rounded-full" style={{ background: p.color }} />{p.name}</span>
                    <span className="font-medium text-ink">{formatMoney(String(p.value), currency, { hidden })}</span>
                  </p>
                ))}
              </TooltipCard>
            ) : null} />
          {keys.map((k, i) => <Bar key={k.slug} name={k.name} dataKey={k.slug} stackId="a" fill={k.color} maxBarSize={30}
            radius={i === keys.length - 1 ? [5, 5, 0, 0] : undefined} animationDuration={500} />)}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MiniLine({ points, color = "var(--chart-1)", height = 140, currency }: { points: { date: string; v: MoneyStr }[]; color?: string; height?: number; currency: string }) {
  const hidden = useUi((s) => s.privacy);
  const data = points.map((p) => ({ date: p.date, v: toNum(p.v), raw: p.v }));
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <YAxis hide domain={["auto", "auto"]} />
          <XAxis dataKey="date" hide />
          <Tooltip content={({ active, payload }) => active && payload?.[0] ? (
            <TooltipCard><p className="text-muted">{formatDate(payload[0].payload.date)}</p><p className="font-semibold tabular">{formatMoney(payload[0].payload.raw, currency, { hidden })}</p></TooltipCard>) : null} />
          <Area type="monotone" dataKey="v" stroke={color} fill={color} fillOpacity={0.08} strokeWidth={1.75} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
