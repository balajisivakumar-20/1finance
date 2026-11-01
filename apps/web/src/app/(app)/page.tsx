"use client";
import * as React from "react";
import Link from "next/link";
import { format } from "date-fns";
import { motion } from "motion/react";
import { ArrowRight, ArrowDownLeft, ArrowUpRight, Info, Landmark, Lightbulb, PiggyBank, Sparkles, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import { Donut, NetWorthArea, WealthLines, PALETTE } from "@/components/charts/charts";
import { CategoryIcon, InstitutionAvatar, ACCOUNT_TYPE_LABEL } from "@/components/category-icon";
import { Change, Money } from "@/components/money";
import { ConnectionStatus } from "@/components/status";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Segmented, Skeleton } from "@/components/ui/primitives";
import { Tip } from "@/components/ui/overlay";
import { ago, formatDate, formatMoney, formatPct, greeting, relativeDay } from "@/lib/format";
import { useCurrency, useHistory, useInsights, useMe, useSpending, useSummary, useTransactions } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

const RANGES = [{ value: "1M", label: "1M" }, { value: "3M", label: "3M" }, { value: "6M", label: "6M" }, { value: "1Y", label: "1Y" }, { value: "ALL", label: "All" }] as const;
type Range = (typeof RANGES)[number]["value"];

const fade = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.3, ease: "easeOut" as const } };

export default function OverviewPage() {
  const { data: me } = useMe();
  const summary = useSummary();
  const [now, setNow] = React.useState<Date | null>(null);
  React.useEffect(() => setNow(new Date()), []);
  return (
    <div className="space-y-5 lg:space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[13px] text-muted">{now ? format(now, "EEEE, d MMMM yyyy") : " "}</p>
          <h1 className="mt-1 text-[30px] font-semibold leading-tight tracking-tight text-ink sm:text-[42px]">
            {now ? greeting(now) : "Hello"}{me?.display_name ? `, ${me.display_name.split(" ")[0]}` : ""}
          </h1>
          <p className="mt-0.5 text-[15px] text-muted">Here&apos;s your financial overview.</p>
        </div>
        {summary.data && (
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
            {summary.data.data_quality.includes_estimates && <Tip content="Includes manually estimated asset values"><Badge tone="outline">Includes estimates</Badge></Tip>}
            {summary.data.data_quality.price_types.includes("delayed") && <Tip content="Security prices may be delayed by 15+ minutes"><Badge tone="outline">Delayed prices</Badge></Tip>}
            {summary.data.fx && <Tip content={`Converted with ${summary.data.fx.provider.toUpperCase()} rates as of ${formatDate(summary.data.fx.as_of)}`}><Badge tone="outline">FX: {summary.data.fx.provider.toUpperCase()}</Badge></Tip>}
            <span>Last synced {ago(summary.data.last_sync)}</span>
          </div>
        )}
      </div>

      <NetWorthHero />
      <SummaryCards />

      <div className="grid gap-5 [&>*]:min-w-0 lg:grid-cols-12 lg:gap-6">
        <WealthOverTime className="lg:col-span-8" />
        <Allocation className="lg:col-span-4" />
      </div>
      <div className="grid gap-5 [&>*]:min-w-0 lg:grid-cols-12 lg:gap-6">
        <AccountsCard className="lg:col-span-5" />
        <SpendingCard className="lg:col-span-7" />
      </div>
      <div className="grid gap-5 [&>*]:min-w-0 lg:grid-cols-12 lg:gap-6">
        <RecentTransactions className="lg:col-span-7 xl:col-span-8" />
        <Insights className="lg:col-span-5 xl:col-span-4" />
      </div>
    </div>
  );
}

function NetWorthHero() {
  const currency = useCurrency();
  const [range, setRange] = React.useState<Range>("6M");
  const [hover, setHover] = React.useState<{ date: string; value: string | null | undefined } | null>(null);
  const summary = useSummary();
  const history = useHistory(range);
  const pts = history.data?.points ?? [];
  const last = summary.data?.net_worth.value;
  const changeAbs = history.data?.change ?? null; // computed server-side (Decimal)
  const changePct = history.data?.change_pct ?? null;
  const rangeLabel = { "1M": "past month", "3M": "past 3 months", "6M": "past 6 months", "1Y": "past year", ALL: "all time" }[range];

  return (
    <motion.div {...fade}>
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-4 px-5 pt-5 sm:flex-row sm:items-start sm:justify-between sm:px-7 sm:pt-6">
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted">Total net worth</p>
            {summary.isLoading ? <Skeleton className="mt-2 h-11 w-64" /> : summary.isError ? <p className="mt-2 text-sm text-neg">Unavailable</p> : (
              <>
                <p className="mt-1.5 text-[38px] font-semibold leading-none tracking-tight text-ink tabular sm:text-[44px]" aria-live="polite">
                  <Money value={hover?.value ?? last} currency={currency} />
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-muted">
                  {hover ? <span>{formatDate(hover.date, "EEE, d MMM yyyy")}</span> : (
                    <><Change pct={changePct} amount={changeAbs} currency={currency} label={rangeLabel} /><span>{rangeLabel}</span></>
                  )}
                </div>
              </>
            )}
          </div>
          <Segmented label="Net worth range" value={range} onChange={setRange} options={RANGES as unknown as { value: Range; label: string }[]} />
        </div>
        <div className="px-2 pb-3 pt-2 sm:px-4">
          {history.isLoading ? <Skeleton className="mx-3 h-[220px]" /> : history.isError ? <ErrorState error={history.error} retry={history.refetch} /> :
            pts.length < 2 ? <EmptyState title="Not enough history yet" description="Net worth history appears after your accounts have synced for at least two days." /> :
            <NetWorthArea points={pts} currency={currency} range={range} onHover={setHover} />}
        </div>
      </Card>
    </motion.div>
  );
}

function SummaryCards() {
  const currency = useCurrency();
  const { data, isLoading } = useSummary();
  const cards = data ? [
    { title: "Total assets", icon: Wallet, value: data.assets.value, change: <Change pct={data.assets.change_pct} label="vs last month" />, note: "Balance now · vs 1 month ago", tone: "accent" },
    { title: "Total liabilities", icon: Landmark, value: data.liabilities.value, change: <Change pct={data.liabilities.change_pct} invert label="vs last month" />, note: "Outstanding now · vs 1 month ago", tone: "neutral" },
    { title: "Income this month", icon: ArrowDownLeft, value: data.income_month.value, change: data.income_month.change_pct != null ? <Change pct={data.income_month.change_pct} label="vs same days last month" /> : null,
      note: `Last month: ${formatMoney(data.income_month.last_month_total, currency, { hidden: useUi.getState().privacy })}`, tone: "pos" },
    { title: "Expenses this month", icon: ArrowUpRight, value: data.expenses_month.value, change: data.expenses_month.change_pct != null ? <Change pct={data.expenses_month.change_pct} invert label="vs same days last month" /> : null,
      note: `Last month: ${formatMoney(data.expenses_month.last_month_total, currency, { hidden: useUi.getState().privacy })}`, tone: "warn" },
  ] : [];
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      {isLoading && Array.from({ length: 4 }).map((_, i) => <Card key={i} className="p-5"><Skeleton className="h-4 w-24" /><Skeleton className="mt-3 h-7 w-32" /><Skeleton className="mt-3 h-4 w-20" /></Card>)}
      {cards.map((c, i) => (
        <motion.div key={c.title} {...fade} transition={{ ...fade.transition, delay: 0.04 * i }}>
          <Card className="group h-full p-4 transition-shadow hover:shadow-pop sm:p-5">
            <div className="flex items-center justify-between">
              <p className="text-[12.5px] font-medium text-muted">{c.title}</p>
              <span className={cn("grid size-8 place-items-center rounded-xl",
                c.tone === "accent" ? "bg-accent-soft text-accent-fg" : c.tone === "pos" ? "bg-pos-soft text-pos" : c.tone === "warn" ? "bg-warn-soft text-warn" : "bg-bg-subtle text-ink-2")}>
                <c.icon className="size-4" aria-hidden />
              </span>
            </div>
            <p className="mt-2.5 text-xl font-semibold tracking-tight text-ink tabular sm:text-2xl"><Money value={c.value} currency={currency} /></p>
            <div className="mt-2 flex min-h-5 flex-wrap items-center gap-1.5">{c.change}</div>
            <p className="mt-1.5 text-[11.5px] text-faint">{c.note}</p>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

function WealthOverTime({ className }: { className?: string }) {
  const currency = useCurrency();
  const [range, setRange] = React.useState<Range>("1Y");
  const history = useHistory(range);
  const [on, setOn] = React.useState({ net_worth: true, assets: true, liabilities: true });
  const series = [
    { key: "net_worth" as const, label: "Net worth", color: "var(--chart-1)", on: on.net_worth },
    { key: "assets" as const, label: "Assets", color: "var(--chart-3)", on: on.assets },
    { key: "liabilities" as const, label: "Liabilities", color: "var(--chart-4)", on: on.liabilities },
  ];
  return (
    <Card className={className}>
      <CardHeader title="Wealth over time" description="Net worth, assets and liabilities from daily snapshots"
        action={<Segmented label="Wealth range" value={range} onChange={setRange} options={RANGES.slice(1) as unknown as { value: Range; label: string }[]} />} />
      <CardBody>
        <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Series">
          {series.map((s) => (
            <button key={s.key} aria-pressed={s.on} onClick={() => setOn((o) => ({ ...o, [s.key]: !o[s.key] }))}
              className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[12px] font-medium transition-colors",
                s.on ? "border-line bg-card text-ink" : "border-dashed border-line text-faint")}>
              <span className="size-2 rounded-full" style={{ background: s.on ? s.color : "var(--line-strong)" }} />{s.label}
            </button>
          ))}
        </div>
        {history.isLoading ? <Skeleton className="h-[280px]" /> : history.isError ? <ErrorState error={history.error} retry={history.refetch} /> :
          <WealthLines points={history.data?.points ?? []} currency={currency} range={range} series={series} />}
      </CardBody>
    </Card>
  );
}

const ALLOC_LINK: Record<string, string> = { stocks: "/investments", etfs: "/investments", mutual_funds: "/investments", brokerage_cash: "/investments",
  bank: "/accounts", cash: "/accounts", fixed_deposits: "/accounts#manual", other_assets: "/accounts#manual", other_investments: "/investments" };

function Allocation({ className }: { className?: string }) {
  const currency = useCurrency();
  const { data, isLoading, isError, error, refetch } = useSummary();
  const [selected, setSelected] = React.useState<string | null>(null);
  const rows = (data?.allocation ?? []).map((a, i) => ({ ...a, color: PALETTE[i % PALETTE.length] }));
  return (
    <Card className={className}>
      <CardHeader title="Asset allocation" description="Where your assets are held" />
      <CardBody>
        {isLoading ? <Skeleton className="mx-auto size-[200px] rounded-full" /> : isError ? <ErrorState error={error} retry={refetch} /> : !rows.length ? (
          <EmptyState title="No assets yet" description="Connect an account to see your allocation." />
        ) : (
          <>
            <Donut data={rows} currency={currency} centerLabel="Total assets" centerValue={data!.assets.value} selected={selected} onSelect={setSelected} size={200} />
            <ul className="mt-4 space-y-0.5">
              {rows.map((r) => (
                <li key={r.key}>
                  <button onClick={() => setSelected(selected === r.key ? null : r.key)} aria-pressed={selected === r.key}
                    className={cn("flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left text-[13px] transition-colors hover:bg-bg-subtle", selected === r.key && "bg-bg-subtle")}>
                    <span className="size-2.5 shrink-0 rounded-full" style={{ background: r.color }} aria-hidden />
                    <span className="min-w-0 flex-1 truncate text-ink-2">{r.label}</span>
                    <span className="w-12 text-right text-muted tabular">{formatPct(r.share, { decimals: 1 })}</span>
                    <span className="w-24 text-right font-medium text-ink"><Money value={r.value} currency={currency} decimals={0} /></span>
                  </button>
                </li>
              ))}
            </ul>
            {selected && (
              <Link href={ALLOC_LINK[selected] ?? "/accounts"} className="mt-3 flex items-center justify-center gap-1 text-[13px] font-medium text-accent-fg hover:underline">
                View {rows.find((r) => r.key === selected)?.label.toLowerCase()} <ArrowRight className="size-3.5" />
              </Link>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function AccountsCard({ className }: { className?: string }) {
  const currency = useCurrency();
  const { data, isLoading } = useSummary();
  const accounts = data?.accounts ?? [];
  return (
    <Card className={className}>
      <CardHeader title="Your accounts" description={`${accounts.length} account${accounts.length === 1 ? "" : "s"}`}
        action={<Button asChild variant="ghost" size="sm"><Link href="/accounts">Manage<ArrowRight /></Link></Button>} />
      <CardBody className="px-3 sm:px-4">
        {isLoading && <div className="space-y-3 px-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>}
        {!isLoading && !accounts.length && <EmptyState title="No accounts connected" action={<Button asChild variant="primary" size="sm"><Link href="/accounts?add=1">Add account</Link></Button>} />}
        <ul className="divide-y divide-line">
          {accounts.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-2 py-3">
              <InstitutionAvatar slug={a.institution_slug} name={a.institution} type={a.account_type} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[14px] font-medium text-ink">{a.name}</p>
                <p className="truncate text-[12px] text-muted">{a.institution} · {ACCOUNT_TYPE_LABEL[a.account_type] ?? a.account_type}{a.masked_reference ? ` · ${a.masked_reference}` : ""}</p>
              </div>
              <div className="text-right">
                <p className="text-[14px] font-semibold text-ink"><Money value={a.balance} currency={a.currency} /></p>
                <div className="mt-0.5 flex justify-end">
                  {a.currency !== currency ? <span className="text-[11.5px] text-muted">≈ <Money value={a.balance_base} currency={currency} /></span>
                    : <ConnectionStatus status={a.connection_status} lastSync={a.last_sync} stale={a.is_stale} />}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

function SpendingCard({ className }: { className?: string }) {
  const currency = useCurrency();
  const [period, setPeriod] = React.useState<"this_month" | "last_month">("this_month");
  const { data, isLoading, isError, error, refetch } = useSpending(period);
  const cats = data?.categories ?? [];
  const top = cats.slice(0, 6);
  return (
    <Card className={className}>
      <CardHeader title="Monthly spending" description={data ? `${formatDate(data.period[0], "d MMM")} – ${formatDate(data.period[1], "d MMM yyyy")} · excludes transfers & investments` : " "}
        action={<Segmented label="Spending period" value={period} onChange={setPeriod} options={[{ value: "this_month", label: "This month" }, { value: "last_month", label: "Last month" }]} />} />
      <CardBody>
        {isLoading ? <Skeleton className="h-52" /> : isError ? <ErrorState error={error} retry={refetch} /> : !cats.length ? (
          <EmptyState icon={PiggyBank} title="No spending recorded yet" description={period === "this_month" ? "Nothing has been spent this month so far." : "No expenses last month."}
            action={period === "this_month" ? <Button size="sm" onClick={() => setPeriod("last_month")}>View last month</Button> : undefined} />
        ) : (
          <div className="grid items-center gap-6 sm:grid-cols-[180px_1fr]">
            <Donut data={cats.map((c) => ({ key: c.slug, label: c.name, value: c.amount, share: c.share, color: c.color ?? undefined }))}
              currency={currency} centerLabel="Spent" centerValue={data!.total} size={180} />
            <ul className="space-y-3">
              {top.map((c) => (
                <li key={c.slug} className="flex items-center gap-3">
                  <CategoryIcon icon={c.icon} color={c.color} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2 text-[13px]">
                      <span className="truncate font-medium text-ink">{c.name}</span>
                      <span className="font-medium text-ink"><Money value={c.amount} currency={currency} /></span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-bg-subtle">
                      <motion.div className="h-full rounded-full" style={{ background: c.color ?? "var(--accent)" }}
                        initial={{ width: 0 }} animate={{ width: `${Math.max(2, Number(c.share))}%` }} transition={{ duration: 0.6, ease: "easeOut" }} />
                    </div>
                  </div>
                  <span className="w-11 text-right text-[12px] text-muted tabular">{formatPct(c.share, { decimals: 0 })}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-5 flex justify-end">
          <Button asChild variant="ghost" size="sm"><Link href="/analytics">Detailed spending analytics<ArrowRight /></Link></Button>
        </div>
      </CardBody>
    </Card>
  );
}

function RecentTransactions({ className }: { className?: string }) {
  const currency = useCurrency();
  const { data, isLoading, isError, error, refetch } = useTransactions({ page_size: 8 });
  return (
    <Card className={className}>
      <CardHeader title="Recent transactions" description="Across all connected accounts"
        action={<Button asChild variant="ghost" size="sm"><Link href="/transactions">View all<ArrowRight /></Link></Button>} />
      <CardBody className="px-2 sm:px-3">
        {isLoading && <div className="space-y-2 px-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}</div>}
        {isError && <ErrorState error={error} retry={refetch} />}
        {data && !data.items.length && <EmptyState title="No transactions yet" description="Import a statement or connect a bank account." />}
        <ul>
          {data?.items.map((t) => {
            const inflow = Number(t.amount) > 0;
            return (
              <li key={t.id}>
                <Link href={`/transactions?id=${t.id}`} className="flex items-center gap-3 rounded-2xl px-3 py-2.5 transition-colors hover:bg-bg-subtle">
                  <CategoryIcon icon={t.category?.icon} color={t.category?.color} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-medium text-ink">{t.merchant ?? t.description}</p>
                    <p className="truncate text-[12px] text-muted">{t.category?.name ?? "Uncategorized"} · {t.account?.name} · {relativeDay(t.date)}</p>
                  </div>
                  <div className="text-right">
                    <p className={cn("text-[14px] font-semibold tabular", inflow ? "text-pos" : "text-ink")}>
                      <Money value={t.amount} currency={t.currency} signed={inflow} />
                    </p>
                    <div className="mt-0.5 flex justify-end gap-1">
                      {t.status === "pending" && <Badge tone="warn">Pending</Badge>}
                      {t.type === "transfer" && <Badge tone="outline">Transfer</Badge>}
                      {t.currency !== currency && t.amount_base && <span className="text-[11px] text-muted">≈ <Money value={t.amount_base} currency={currency} /></span>}
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}

function Insights({ className }: { className?: string }) {
  const currency = useCurrency();
  const { data, isLoading, isError, error, refetch } = useInsights();
  const iconFor = (k: string) => (k === "positive" ? TrendingUp : k === "attention" ? TrendingDown : Lightbulb);
  return (
    <Card className={className}>
      <CardHeader title={<span className="inline-flex items-center gap-2"><Sparkles className="size-4 text-accent-fg" />Financial insights</span>}
        description="Calculated from your recorded data" />
      <CardBody className="space-y-2.5">
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}
        {isError && <ErrorState error={error} retry={refetch} />}
        {data && !data.items.length && <EmptyState icon={Info} title="No insights yet" description="Insights appear once there's enough history to compare." />}
        {data?.items.map((it) => {
          const Icon = iconFor(it.kind);
          const v = it.values?.current;
          return (
            <div key={it.id} className="hl flex gap-3 rounded-2xl border border-line p-3.5">
              <span className={cn("grid size-8 shrink-0 place-items-center rounded-xl",
                it.kind === "positive" ? "bg-pos-soft text-pos" : it.kind === "attention" ? "bg-warn-soft text-warn" : "bg-info-soft text-info")}>
                <Icon className="size-4" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[13.5px] font-medium text-ink">{it.title}</p>
                  {v != null && it.unit !== "percent" && <span className="text-[13px] font-semibold text-ink"><Money value={v} currency={currency} /></span>}
                </div>
                <p className="mt-0.5 text-[12px] leading-relaxed text-muted">{it.body}</p>
              </div>
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}
