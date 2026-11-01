"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Info } from "lucide-react";
import { CashflowBars, Donut, StackedCategoryBars } from "@/components/charts/charts";
import { CategoryIcon } from "@/components/category-icon";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardHeader, ErrorState, Segmented, Skeleton, Stat } from "@/components/ui/primitives";
import { api, qs, type SpendingCat } from "@/lib/api";
import { formatDate, formatPct, type MoneyStr } from "@/lib/format";
import { useCurrency } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Cashflow {
  currency: string;
  months: { month: string; income: MoneyStr; expenses: MoneyStr; net: MoneyStr; savings_rate: MoneyStr; transfers_out: MoneyStr; partial: boolean; categories: Record<string, MoneyStr> }[];
  totals: { income: MoneyStr; expenses: MoneyStr; savings: MoneyStr; savings_rate: MoneyStr; full_months: number };
  definitions: Record<string, string>;
}

export default function AnalyticsPage() {
  const currency = useCurrency();
  const [months, setMonths] = React.useState("12");
  const [catPeriod, setCatPeriod] = React.useState<"last_month" | "3m" | "ytd">("last_month");
  const [nwPeriod, setNwPeriod] = React.useState<"monthly" | "quarterly" | "annual">("monthly");
  const cf = useQuery({ queryKey: ["cashflow", currency, months], queryFn: () => api<Cashflow>(`/analytics/cashflow${qs({ months, currency })}`) });
  const range = React.useMemo(() => {
    const t = new Date(); const fmt = (d: Date) => format(d, "yyyy-MM-dd");
    if (catPeriod === "last_month") { const a = new Date(t.getFullYear(), t.getMonth() - 1, 1); const b = new Date(t.getFullYear(), t.getMonth(), 0); return [fmt(a), fmt(b)]; }
    if (catPeriod === "3m") return [fmt(new Date(t.getFullYear(), t.getMonth() - 3, 1)), fmt(new Date(t.getFullYear(), t.getMonth(), 0))];
    return [fmt(new Date(t.getFullYear(), 0, 1)), fmt(t)];
  }, [catPeriod]);
  const cats = useQuery({ queryKey: ["cat-analytics", currency, range], queryFn: () => api<{ total: MoneyStr; groups: SpendingCat[]; detail: { slug: string; name: string; parent: string; amount: MoneyStr }[] }>(`/analytics/categories${qs({ date_from: range[0], date_to: range[1], currency })}`) });
  const nw = useQuery({ queryKey: ["nw-compare", currency, nwPeriod], queryFn: () => api<{ points: { date: string; net_worth: MoneyStr; change: MoneyStr }[] }>(`/analytics/net-worth${qs({ period: nwPeriod, currency })}`) });
  const yr = useQuery({ queryKey: ["yearly", currency], queryFn: () => api<Record<string, MoneyStr>>(`/analytics/yearly${qs({ currency })}`) });
  const topKeys = (cats.data?.groups ?? []).slice(0, 6).map((g) => ({ slug: g.slug, name: g.name, color: g.color ?? "var(--chart-8)" }));

  return (
    <div className="space-y-5">
      <PageHeader title="Analytics" subtitle="Understand where your money comes from and where it goes." />

      <Card>
        <CardHeader title="Income vs expenses" description="Monthly cash flow · current month is month-to-date"
          action={<Segmented label="Months" value={months} onChange={setMonths} options={[{ value: "6", label: "6M" }, { value: "12", label: "12M" }, { value: "24", label: "24M" }]} />} />
        <CardBody>
          {cf.isLoading ? <Skeleton className="h-72" /> : cf.isError ? <ErrorState error={cf.error} retry={cf.refetch} /> : cf.data && (
            <>
              <div className="mb-5 grid grid-cols-2 gap-5 sm:grid-cols-4">
                <Stat label="Income" sub={`${cf.data.totals.full_months} full months`}><Money value={cf.data.totals.income} currency={currency} /></Stat>
                <Stat label="Expenses"><Money value={cf.data.totals.expenses} currency={currency} /></Stat>
                <Stat label="Net savings"><Money value={cf.data.totals.savings} currency={currency} signed /></Stat>
                <Stat label="Savings rate">{cf.data.totals.savings_rate != null ? formatPct(cf.data.totals.savings_rate, { decimals: 1 }) : "—"}</Stat>
              </div>
              <CashflowBars months={cf.data.months} currency={currency} />
              <details className="mt-4 rounded-xl bg-bg-subtle px-4 py-3 text-[13.5px] text-ink-2">
                <summary className="flex cursor-pointer items-center gap-2 font-medium"><Info className="size-3.5" />What&apos;s included in these numbers</summary>
                <dl className="mt-2 space-y-1">{Object.entries(cf.data.definitions).map(([k, v]) => <div key={k}><dt className="inline font-medium capitalize">{k.replace("_", " ")}: </dt><dd className="inline text-muted">{v}</dd></div>)}</dl>
              </details>
            </>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-5 [&>*]:min-w-0 lg:grid-cols-12">
        <Card className="lg:col-span-5">
          <CardHeader title="Spending by category" description={`${formatDate(range[0], "d MMM")} – ${formatDate(range[1], "d MMM yyyy")}`}
            action={<Segmented label="Category period" value={catPeriod} onChange={setCatPeriod} options={[{ value: "last_month", label: "Last month" }, { value: "3m", label: "3M" }, { value: "ytd", label: "YTD" }]} />} />
          <CardBody>
            {cats.isLoading ? <Skeleton className="h-64" /> : cats.data && (
              <>
                <Donut size={200} currency={currency} centerLabel="Total spent" centerValue={cats.data.total}
                  data={cats.data.groups.map((g) => ({ key: g.slug, label: g.name, value: g.amount, share: g.share, color: g.color ?? undefined }))} />
                <div className="mt-5 space-y-2.5">
                  {cats.data.groups.map((g) => (
                    <div key={g.slug} className="flex items-center gap-3">
                      <CategoryIcon icon={g.icon} color={g.color} size="sm" />
                      <div className="flex-1">
                        <div className="flex justify-between text-[14px]"><span className="font-medium text-ink">{g.name}</span><Money value={g.amount} currency={currency} className="font-medium" /></div>
                        <div className="mt-1 h-1.5 rounded-full bg-bg-subtle"><div className="h-full rounded-full" style={{ width: `${Math.max(1, Number(g.share))}%`, background: g.color ?? "var(--accent)" }} /></div>
                      </div>
                      <span className="w-10 text-right text-[13px] tabular text-muted">{formatPct(g.share, { decimals: 0 })}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardBody>
        </Card>
        <Card className="lg:col-span-7">
          <CardHeader title="Monthly expense trends" description="Top categories, stacked by month" />
          <CardBody>
            {cf.data && topKeys.length ? <StackedCategoryBars months={cf.data.months} keys={topKeys} currency={currency} /> : <Skeleton className="h-72" />}
            {cats.data && (
              <div className="mt-5 max-h-72 overflow-auto rounded-xl border border-line">
                <table className="w-full text-[14px]">
                  <thead className="sticky top-0 bg-bg-subtle text-left text-[13px] text-muted"><tr><th className="px-3 py-2 font-medium">Subcategory</th><th className="px-3 py-2 font-medium">Group</th><th className="px-3 py-2 text-right font-medium">Amount</th></tr></thead>
                  <tbody className="divide-y divide-line">{cats.data.detail.map((d) => <tr key={d.slug}><td className="px-3 py-2">{d.name}</td><td className="px-3 py-2 text-muted">{d.parent}</td><td className="px-3 py-2 text-right"><Money value={d.amount} currency={currency} /></td></tr>)}</tbody>
                </table>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-5 [&>*]:min-w-0 lg:grid-cols-12">
        <Card className="lg:col-span-7">
          <CardHeader title="Wealth growth" description="Net worth at each period end and the change from the previous one"
            action={<Segmented label="Comparison" value={nwPeriod} onChange={setNwPeriod} options={[{ value: "monthly", label: "Monthly" }, { value: "quarterly", label: "Quarterly" }, { value: "annual", label: "Annual" }]} />} />
          <CardBody>
            {nw.isLoading ? <Skeleton className="h-60" /> : nw.data && (
              <div className="overflow-x-auto"><table className="w-full text-[14px]">
                <thead className="text-left text-[13px] text-muted"><tr><th className="py-2 font-medium">Period end</th><th className="py-2 text-right font-medium">Net worth</th><th className="py-2 text-right font-medium">Change</th></tr></thead>
                <tbody className="divide-y divide-line">{[...nw.data.points].reverse().map((p) => (
                  <tr key={p.date}><td className="py-2.5 text-ink-2">{formatDate(p.date, nwPeriod === "annual" ? "d MMM yyyy" : "MMM yyyy")}</td>
                    <td className="py-2.5 text-right font-medium"><Money value={p.net_worth} currency={currency} /></td>
                    <td className={cn("py-2.5 text-right", p.change == null ? "text-faint" : Number(p.change) >= 0 ? "text-pos" : "text-neg")}>{p.change == null ? "—" : <Money value={p.change} currency={currency} signed />}</td></tr>
                ))}</tbody>
              </table></div>
            )}
          </CardBody>
        </Card>
        <Card className="lg:col-span-5">
          <CardHeader title={`${yr.data?.year ?? ""} at a glance`} description="Year to date" />
          <CardBody>
            {yr.isLoading ? <Skeleton className="h-60" /> : yr.data && (
              <div className="grid grid-cols-2 gap-5">
                <Stat label="Total income"><Money value={yr.data.income} currency={currency} /></Stat>
                <Stat label="Total expenses"><Money value={yr.data.expenses} currency={currency} /></Stat>
                <Stat label="Net savings"><Money value={yr.data.net_savings} currency={currency} signed /></Stat>
                <Stat label="Savings rate">{yr.data.savings_rate ? formatPct(yr.data.savings_rate, { decimals: 1 }) : "—"}</Stat>
                <Stat label="Investment income" sub="Dividends"><Money value={yr.data.investment_income} currency={currency} /></Stat>
                <Stat label="Net worth change"><Money value={yr.data.net_worth_change} currency={currency} signed /></Stat>
                <p className="col-span-2 text-[12.5px] text-faint">{yr.data.coverage_note as string}</p>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
