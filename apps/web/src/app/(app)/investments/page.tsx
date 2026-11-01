"use client";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Info, LineChart as LineIcon } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Donut, PALETTE } from "@/components/charts/charts";
import { Change, Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { PriceTypeBadge } from "@/components/status";
import { Badge, Card, CardBody, CardHeader, EmptyState, ErrorState, NativeSelect, Segmented, Skeleton, Stat } from "@/components/ui/primitives";
import { Sheet, Tip } from "@/components/ui/overlay";
import { api, qs, type Holding } from "@/lib/api";
import { formatDate, formatMoney, formatPct, formatQty, type MoneyStr } from "@/lib/format";
import { useCurrency, useHoldings } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

type Range = "1M" | "3M" | "6M" | "1Y" | "ALL";
interface InvSummary {
  currency: string; total_value: MoneyStr; holdings_value: MoneyStr; cash: MoneyStr; invested_capital: MoneyStr; unrealized: MoneyStr;
  unrealized_pct: MoneyStr; realized: MoneyStr; dividends: MoneyStr; cost_basis_note: string; price_types: string[]; stale: boolean;
  scopes: { value: string; label: string }[];
}
interface InvHistory {
  currency: string; points: { date: string; value: MoneyStr; holdings: MoneyStr; cash: MoneyStr; net_flow: MoneyStr }[];
  twr: MoneyStr; mwr: MoneyStr; methods?: Record<string, string>; decomposition: Record<string, MoneyStr> | null; decomposition_note?: string;
}

export default function InvestmentsPage() {
  const currency = useCurrency();
  const [scope, setScope] = React.useState("all");
  const [range, setRange] = React.useState<Range>("1Y");
  const [group, setGroup] = React.useState("asset_class");
  const [sort, setSort] = React.useState<{ key: keyof Holding; desc: boolean }>({ key: "market_value_base", desc: true });
  const [detail, setDetail] = React.useState<Holding | null>(null);
  const hidden = useUi((s) => s.privacy);

  const summary = useQuery({ queryKey: ["inv-summary", currency, scope], queryFn: () => api<InvSummary>(`/investments/summary${qs({ scope, currency })}`) });
  const history = useQuery({ queryKey: ["inv-history", currency, scope, range], queryFn: () => api<InvHistory>(`/investments/history${qs({ scope, range, currency })}`) });
  const holdings = useHoldings(scope);
  const s = summary.data;

  const rows = React.useMemo(() => {
    const items = [...(holdings.data?.items ?? [])];
    items.sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      const cmp = typeof av === "string" && !isNaN(Number(av)) ? Number(av) - Number(bv) : String(av ?? "").localeCompare(String(bv ?? ""));
      return sort.desc ? -cmp : cmp;
    });
    return items;
  }, [holdings.data, sort]);

  const th = (key: keyof Holding, label: string, right = true) => (
    <th scope="col" className={cn("px-4 py-3 font-medium", right && "text-right")} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : undefined}>
      <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort((x) => ({ key, desc: x.key === key ? !x.desc : true }))}>
        {label}{sort.key === key && (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />)}
      </button>
    </th>
  );

  return (
    <div className="space-y-5">
      <PageHeader title="Investments" subtitle="Interactive Brokers and Groww, consolidated into one portfolio."
        action={<NativeSelect aria-label="Portfolio scope" className="w-56" value={scope} onChange={(e) => setScope(e.target.value)}>
          {(s?.scopes ?? [{ value: "all", label: "All investments" }]).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </NativeSelect>} />

      <Card>
        <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[1.2fr_2fr]">
          <div>
            <p className="text-[14.5px] font-semibold uppercase tracking-[0.08em] text-muted">Total investment value</p>
            {summary.isLoading ? <Skeleton className="mt-2 h-10 w-52" /> : summary.isError ? <ErrorState error={summary.error} /> : s && (
              <>
                <p className="mt-1.5 text-4xl font-semibold tracking-tight text-ink"><Money value={s.total_value} currency={currency} /></p>
                <div className="mt-2 flex flex-wrap items-center gap-2"><Change amount={s.unrealized} pct={s.unrealized_pct} currency={currency} label="unrealized" /><span className="text-[15.5px] text-muted">unrealized</span></div>
                <div className="mt-3 flex flex-wrap gap-1.5">{s.price_types.map((p) => <PriceTypeBadge key={p} type={p} />)}{s.stale && <Badge tone="warn">Stale prices</Badge>}</div>
              </>
            )}
          </div>
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-3">
            {s && <>
              <Stat label="Invested capital" sub="Cost basis"><Money value={s.invested_capital} currency={currency} /></Stat>
              <Stat label="Unrealized P/L"><span className={Number(s.unrealized) >= 0 ? "text-pos" : "text-neg"}><Money value={s.unrealized} currency={currency} signed /></span></Stat>
              <Stat label="Realized P/L" sub="From recorded sales"><Money value={s.realized} currency={currency} signed /></Stat>
              <Stat label="Dividends received"><Money value={s.dividends} currency={currency} /></Stat>
              <Stat label="Cash at brokers"><Money value={s.cash} currency={currency} /></Stat>
              <Stat label="Return (TWR)" sub={<Tip content={history.data?.methods?.twr ?? ""}><span className="inline-flex items-center gap-1 underline decoration-dotted">Time-weighted, {range}<Info className="size-3" /></span></Tip>}>
                {history.data?.twr != null ? <span className={Number(history.data.twr) >= 0 ? "text-pos" : "text-neg"}>{formatPct(history.data.twr, { signed: true })}</span> : "—"}
              </Stat>
            </>}
          </div>
        </div>
        {s && <p className="border-t border-line px-6 py-2.5 text-[14px] text-faint">{s.cost_basis_note}</p>}
      </Card>

      <div className="grid gap-5 [&>*]:min-w-0 lg:grid-cols-12">
        <Card className="lg:col-span-8">
          <CardHeader title="Portfolio performance" description="Holdings + broker cash, in reporting currency"
            action={<Segmented label="Performance range" value={range} onChange={setRange} options={(["1M", "3M", "6M", "1Y", "ALL"] as Range[]).map((v) => ({ value: v, label: v === "ALL" ? "All" : v }))} />} />
          <CardBody>
            {history.isLoading ? <Skeleton className="h-64" /> : history.isError ? <ErrorState error={history.error} retry={history.refetch} /> : !history.data?.points.length ? <EmptyState icon={LineIcon} title="No portfolio history yet" /> : (
              <>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={history.data.points.map((p) => ({ ...p, v: Number(p.value), h: Number(p.holdings) }))} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
                      <defs><linearGradient id="invg" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="var(--chart-2)" stopOpacity={0.2} /><stop offset="100%" stopColor="var(--chart-2)" stopOpacity={0} /></linearGradient></defs>
                      <XAxis dataKey="date" tickFormatter={(v) => formatDate(v, range === "1M" ? "d MMM" : "MMM yy")} tick={{ fill: "var(--faint)", fontSize: 13.5 }} axisLine={false} tickLine={false} minTickGap={48} />
                      <YAxis hide domain={["auto", "auto"]} />
                      <Tooltip content={({ active, payload }) => active && payload?.[0] ? (
                        <div className="rounded-xl border border-line bg-card px-3 py-2 text-[14.5px] shadow-pop">
                          <p className="text-muted">{formatDate(payload[0].payload.date)}</p>
                          <p className="font-semibold tabular">{formatMoney(payload[0].payload.value, currency, { hidden })}</p>
                          {Number(payload[0].payload.net_flow) !== 0 && <p className="text-info">Contribution {formatMoney(payload[0].payload.net_flow, currency, { signed: true, hidden })}</p>}
                        </div>) : null} />
                      <Area type="monotone" dataKey="v" stroke="var(--chart-2)" strokeWidth={2} fill="url(#invg)" animationDuration={500} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                {history.data.decomposition && (
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {([["Total change", "total_change"], ["Your contributions", "contributions"], ["Market performance", "market"], ["Currency effect", "fx_effect"]] as const).map(([l, k]) => (
                      <div key={k} className="rounded-2xl bg-bg-subtle p-3">
                        <p className="text-[14px] text-muted">{l}</p>
                        <p className="mt-0.5 font-semibold text-ink"><Money value={history.data!.decomposition![k]} currency={currency} signed /></p>
                      </div>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-[14px] text-faint">TWR {formatPct(history.data.twr, { signed: true })} · MWR {formatPct(history.data.mwr, { signed: true })} (annualized). {history.data.decomposition_note}</p>
              </>
            )}
          </CardBody>
        </Card>
        <Card className="lg:col-span-4">
          <CardHeader title="Allocation" action={<NativeSelect aria-label="Group allocation by" className="h-8 w-36 text-[14.5px]" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="asset_class">Asset class</option><option value="brokerage">Brokerage</option><option value="country">Country</option><option value="currency">Currency</option><option value="sector">Sector</option></NativeSelect>} />
          <CardBody>
            {holdings.isLoading ? <Skeleton className="mx-auto size-48 rounded-full" /> : holdings.data && (
              <>
                <Donut size={190} currency={currency} centerLabel="Holdings" centerValue={holdings.data.total}
                  data={(holdings.data.allocation[group] ?? []).map((a, i) => ({ key: a.label, label: labelize(a.label), value: a.value, share: a.share, color: PALETTE[i % PALETTE.length] }))} />
                <ul className="mt-4 space-y-1.5">
                  {(holdings.data.allocation[group] ?? []).map((a, i) => (
                    <li key={a.label} className="flex items-center gap-2.5 text-[15.5px]">
                      <span className="size-2.5 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                      <span className="flex-1 truncate text-ink-2">{labelize(a.label)}</span>
                      <span className="tabular text-muted">{formatPct(a.share, { decimals: 1 })}</span>
                    </li>
                  ))}
                </ul>
                {group === "sector" && <p className="mt-3 text-[14px] text-faint">Sector shown only where the provider supplies it; unknown values are not guessed.</p>}
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader title="Holdings" description={`${rows.length} positions · values in trading currency unless noted`} />
        <div className="mt-4 overflow-x-auto">
          {holdings.isError ? <ErrorState error={holdings.error} retry={holdings.refetch} /> : (
            <table className="w-full min-w-[960px] text-[15.5px]">
              <thead className="border-y border-line bg-bg-subtle/60 text-left text-[14.5px] text-muted">
                <tr>{th("name", "Asset", false)}{th("brokerage", "Broker", false)}{th("quantity", "Qty")}{th("average_price", "Avg price")}{th("current_price", "Price")}
                  {th("market_value", "Value")}{th("unrealized", "Unrealized P/L")}{th("allocation_pct", "Alloc.")}{th("market_value_base", `Value (${currency})`)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {holdings.isLoading && Array.from({ length: 6 }).map((_, i) => <tr key={i}><td colSpan={9} className="px-4 py-3"><Skeleton className="h-8" /></td></tr>)}
                {rows.map((h) => {
                  const up = Number(h.unrealized) >= 0;
                  return (
                    <tr key={`${h.account_id}-${h.security_id}`} tabIndex={0} onClick={() => setDetail(h)} onKeyDown={(e) => e.key === "Enter" && setDetail(h)} className="cursor-pointer hover:bg-bg-subtle/70">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className="grid size-9 place-items-center rounded-xl bg-bg-subtle text-[13px] font-bold text-ink-2">{h.ticker.slice(0, 4)}</span>
                          <div className="min-w-0"><p className="max-w-56 truncate font-medium text-ink">{h.name}</p>
                            <p className="text-[14px] text-faint">{h.ticker}{h.isin ? ` · ${h.isin}` : ""} · {labelize(h.asset_class)}</p></div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-ink-2">{h.brokerage}</td>
                      <td className="px-4 py-3 text-right tabular">{formatQty(h.quantity)}</td>
                      <td className="px-4 py-3 text-right"><Money value={h.average_price} currency={h.currency} /></td>
                      <td className="px-4 py-3 text-right"><Money value={h.current_price} currency={h.currency} />{h.is_stale && <Badge tone="warn" className="ml-1">Stale</Badge>}</td>
                      <td className="px-4 py-3 text-right font-medium"><Money value={h.market_value} currency={h.currency} /></td>
                      <td className={cn("px-4 py-3 text-right", up ? "text-pos" : "text-neg")}>
                        <span className="inline-flex items-center gap-0.5 whitespace-nowrap">{up ? <ArrowUp className="size-3" aria-label="gain" /> : <ArrowDown className="size-3" aria-label="loss" />}<Money value={h.unrealized} currency={h.currency} signed /></span>
                        <span className="block text-[14px]">{formatPct(h.unrealized_pct, { signed: true })}</span>
                      </td>
                      <td className="px-4 py-3 text-right tabular text-muted">{formatPct(h.allocation_pct, { decimals: 1 })}</td>
                      <td className="px-4 py-3 text-right font-medium"><Money value={h.market_value_base} currency={currency} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Card>
      <HoldingDetail holding={detail} onClose={() => setDetail(null)} />
    </div>
  );
}

function labelize(s: string) {
  const m: Record<string, string> = { etf: "ETFs", stock: "Stocks", mutual_fund: "Mutual funds", bond: "Bonds", other: "Other", IE: "Ireland", US: "United States", IN: "India", NL: "Netherlands" };
  return m[s] ?? s;
}

function HoldingDetail({ holding, onClose }: { holding: Holding | null; onClose: () => void }) {
  const currency = useCurrency();
  const hidden = useUi((s) => s.privacy);
  const { data, isLoading } = useQuery({
    queryKey: ["holding", holding?.security_id, holding?.account_id, currency],
    queryFn: () => api<{ security: { name: string; ticker: string; isin: string | null; asset_class: string; exchange: string | null; sector: string | null };
      quantity: string; average_price: string; current_price: string; price_type: string; valuation_timestamp: string; market_value: string; total_invested: string;
      unrealized: string; unrealized_pct: string; currency: string; dividends_total: string; price_history: { date: string; price: string }[];
      activity: { date: string; type: string; quantity: string | null; price: string | null; amount: string; currency: string }[] }>(`/investments/holdings/${holding!.security_id}${qs({ account_id: holding!.account_id, currency })}`),
    enabled: !!holding,
  });
  return (
    <Sheet open={!!holding} onOpenChange={(o) => !o && onClose()} wide title={holding?.name ?? ""} description={holding ? `${holding.ticker} · ${holding.brokerage}` : undefined}>
      {isLoading || !data ? <Skeleton className="h-64" /> : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Stat label="Market value"><Money value={data.market_value} currency={data.currency} /></Stat>
            <Stat label="Total invested"><Money value={data.total_invested} currency={data.currency} /></Stat>
            <Stat label="Unrealized"><span className={Number(data.unrealized) >= 0 ? "text-pos" : "text-neg"}><Money value={data.unrealized} currency={data.currency} signed /></span></Stat>
            <Stat label="Quantity">{formatQty(data.quantity)}</Stat>
            <Stat label="Average price"><Money value={data.average_price} currency={data.currency} /></Stat>
            <Stat label="Current price" sub={<span className="inline-flex items-center gap-1"><PriceTypeBadge type={data.price_type} />{formatDate(data.valuation_timestamp, "d MMM HH:mm")}</span>}><Money value={data.current_price} currency={data.currency} /></Stat>
          </div>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.price_history.map((p) => ({ ...p, v: Number(p.price) }))}>
                <YAxis hide domain={["auto", "auto"]} /><XAxis dataKey="date" hide />
                <Tooltip content={({ active, payload }) => active && payload?.[0] ? <div className="rounded-lg border border-line bg-card px-2 py-1 text-[14.5px]">{formatDate(payload[0].payload.date)} · {formatMoney(payload[0].payload.price, data.currency, { hidden })}</div> : null} />
                <Area dataKey="v" stroke="var(--chart-3)" fill="var(--chart-3)" fillOpacity={0.08} strokeWidth={1.75} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[15.5px]">
            <dt className="text-muted">ISIN</dt><dd className="text-right font-mono text-[14.5px]">{data.security.isin ?? "—"}</dd>
            <dt className="text-muted">Exchange</dt><dd className="text-right">{data.security.exchange ?? "—"}</dd>
            <dt className="text-muted">Asset class</dt><dd className="text-right">{labelize(data.security.asset_class)}</dd>
            <dt className="text-muted">Dividends (recorded)</dt><dd className="text-right"><Money value={data.dividends_total} currency={data.currency} /></dd>
          </dl>
          <div>
            <p className="mb-2 text-[14.5px] font-semibold uppercase tracking-wider text-muted">Activity</p>
            {!data.activity.length ? <p className="text-[15.5px] text-muted">No recorded activity from this provider.</p> : (
              <ul className="divide-y divide-line text-[15.5px]">
                {data.activity.map((a, i) => (
                  <li key={i} className="flex items-center justify-between py-2">
                    <span><Badge tone={a.type === "buy" ? "info" : a.type === "dividend" ? "pos" : "neutral"}>{a.type}</Badge> <span className="ml-2 text-muted">{formatDate(a.date)}</span></span>
                    <span className="tabular">{a.quantity ? `${formatQty(a.quantity)} @ ${formatMoney(a.price, a.currency, { hidden })} · ` : ""}<Money value={a.amount} currency={a.currency} signed /></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Sheet>
  );
}
