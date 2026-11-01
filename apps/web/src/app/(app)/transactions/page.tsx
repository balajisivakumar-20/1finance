"use client";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type SortingState } from "@tanstack/react-table";
import { endOfWeek, format, startOfMonth, startOfWeek, startOfYear, subMonths, endOfMonth } from "date-fns";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Filter, Search, SearchX, Sparkles, X } from "lucide-react";
import { CategoryIcon } from "@/components/category-icon";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { Sheet } from "@/components/ui/overlay";
import { api, type Txn } from "@/lib/api";
import { CURRENCIES, formatDate, formatMoney, relativeDay } from "@/lib/format";
import { useAccounts, useCategories, useCurrency, useInvalidateAll, useTransaction, useTransactions } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

const TYPES = ["income", "expense", "refund", "transfer", "investment_buy", "investment_sell", "dividend", "interest", "fee", "deposit", "withdrawal"];
const PRESETS: { key: string; label: string; range: () => [Date, Date] }[] = [
  { key: "today", label: "Today", range: () => [new Date(), new Date()] },
  { key: "week", label: "This week", range: () => [startOfWeek(new Date(), { weekStartsOn: 1 }), endOfWeek(new Date(), { weekStartsOn: 1 })] },
  { key: "month", label: "This month", range: () => [startOfMonth(new Date()), new Date()] },
  { key: "last_month", label: "Last month", range: () => [startOfMonth(subMonths(new Date(), 1)), endOfMonth(subMonths(new Date(), 1))] },
  { key: "3m", label: "Last 3 months", range: () => [subMonths(new Date(), 3), new Date()] },
  { key: "year", label: "This year", range: () => [startOfYear(new Date()), new Date()] },
];
const label = (t: string) => t.replace("_", " ").replace(/^\w/, (c) => c.toUpperCase());

export default function TransactionsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const currency = useCurrency();
  const [q, setQ] = React.useState("");
  const [debQ, setDebQ] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [sorting, setSorting] = React.useState<SortingState>([{ id: "date", desc: true }]);
  const [showFilters, setShowFilters] = React.useState(false);
  const [f, setF] = React.useState({
    account_id: params.get("account_id") ?? "", category: params.get("category") ?? "", type: "", currency: "", status: "",
    date_from: "", date_to: "", min_amount: "", max_amount: "", preset: "", review: false,
  });
  const selected = params.get("id") ? Number(params.get("id")) : null;
  React.useEffect(() => { const t = setTimeout(() => { setDebQ(q); setPage(1); }, 250); return () => clearTimeout(t); }, [q]);

  const query = {
    page, page_size: 25, q: debQ || undefined, account_id: f.account_id || undefined, category: f.category || undefined,
    type: f.type || undefined, currency: f.currency || undefined, status: f.status || undefined, date_from: f.date_from || undefined,
    date_to: f.date_to || undefined, min_amount: f.min_amount || undefined, max_amount: f.max_amount || undefined,
    review: f.review || undefined, sort: sorting[0]?.id ?? "date", order: sorting[0]?.desc ? "desc" : "asc",
  };
  const { data, isLoading, isError, error, refetch, isFetching } = useTransactions(query);
  const { data: cats = [] } = useCategories();
  const { data: accts } = useAccounts();
  const activeCount = ["account_id", "category", "type", "currency", "status", "date_from", "min_amount", "max_amount"].filter((k) => f[k as keyof typeof f]).length + (f.review ? 1 : 0);
  const set = (patch: Partial<typeof f>) => { setF((x) => ({ ...x, ...patch })); setPage(1); };
  const open = (id: number | null) => router.replace(id ? `/transactions?id=${id}` : "/transactions", { scroll: false });

  const columns = React.useMemo<ColumnDef<Txn>[]>(() => [
    { id: "date", header: "Date", enableSorting: true, cell: ({ row }) => <span className="whitespace-nowrap text-muted">{formatDate(row.original.date, "d MMM yyyy")}</span> },
    { id: "description", header: "Description", enableSorting: true, cell: ({ row: { original: t } }) => (
      <div className="flex min-w-0 items-center gap-3">
        <CategoryIcon icon={t.category?.icon} color={t.category?.color} size="sm" />
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{t.merchant ?? t.description}</p>
          <p className="truncate text-[11.5px] text-faint">{t.description}</p>
        </div>
      </div>) },
    { id: "account", header: "Account", cell: ({ row: { original: t } }) => <span className="whitespace-nowrap text-ink-2">{t.account?.name}<span className="block text-[11.5px] text-faint">{t.account?.institution}</span></span> },
    { id: "category", header: "Category", cell: ({ row: { original: t } }) => <span className="whitespace-nowrap text-ink-2">{t.category?.name ?? "—"}{t.category_source === "user" && <span className="ml-1 text-[10px] text-accent-fg" title="Set by you">●</span>}</span> },
    { id: "type", header: "Type", cell: ({ row: { original: t } }) => <Badge tone={t.type === "transfer" ? "outline" : t.type.startsWith("investment") ? "info" : "neutral"}>{label(t.type)}</Badge> },
    { id: "amount", header: () => <span className="block text-right">Amount</span>, enableSorting: true, cell: ({ row: { original: t } }) => {
      const pos = Number(t.amount) > 0;
      return (
        <div className="text-right">
          <span className={cn("whitespace-nowrap font-semibold", pos ? "text-pos" : "text-ink")}><Money value={t.amount} currency={t.currency} signed={pos} /></span>
          {t.currency !== currency && t.amount_base && <span className="block text-[11.5px] text-muted">≈ <Money value={t.amount_base} currency={currency} /></span>}
        </div>);
    } },
    { id: "status", header: "Status", cell: ({ row: { original: t } }) => (
      <div className="flex flex-wrap gap-1">
        {t.status === "pending" ? <Badge tone="warn">Pending</Badge> : t.status === "reversed" ? <Badge tone="neg">Reversed</Badge> : <Badge tone="outline">Posted</Badge>}
        {t.duplicate_status === "possible_duplicate" && <Badge tone="warn">Possible duplicate</Badge>}
        {t.transfer_group?.startsWith("suggested") && <Badge tone="info">Transfer?</Badge>}
      </div>) },
  ], [currency]);

  const table = useReactTable({
    data: data?.items ?? [], columns, getCoreRowModel: getCoreRowModel(), manualSorting: true, manualPagination: true,
    state: { sorting }, onSortingChange: (u) => { setSorting(u); setPage(1); }, enableSortingRemoval: false,
  });
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const qc = useQueryClient();
  const detect = useMutation({
    mutationFn: () => api<{ suggested_pairs: number }>("/transactions/detect-transfers", { method: "POST" }),
    onSuccess: (r) => { toast.success(r.suggested_pairs ? `${r.suggested_pairs} possible transfer(s) found — review them` : "No new transfers detected"); if (r.suggested_pairs) set({ review: true }); qc.invalidateQueries({ queryKey: ["transactions"] }); },
  });

  return (
    <div className="space-y-5">
      <PageHeader title="Transactions" subtitle="Every transaction across your accounts, in its original currency."
        action={<Button onClick={() => detect.mutate()} loading={detect.isPending}><Sparkles />Detect transfers</Button>} />

      <Card className="p-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
            <Input aria-label="Search transactions" placeholder="Search merchant, description or notes" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Date presets">
            {PRESETS.map((p) => (
              <button key={p.key} aria-pressed={f.preset === p.key}
                onClick={() => { if (f.preset === p.key) return set({ preset: "", date_from: "", date_to: "" }); const [a, b] = p.range(); set({ preset: p.key, date_from: format(a, "yyyy-MM-dd"), date_to: format(b, "yyyy-MM-dd") }); }}
                className={cn("h-8 rounded-full border px-3 text-[12px] font-medium transition-colors", f.preset === p.key ? "border-accent bg-accent-soft text-accent-fg" : "border-line text-ink-2 hover:bg-bg-subtle")}>
                {p.label}
              </button>
            ))}
          </div>
          <Button size="sm" variant={showFilters ? "subtle" : "secondary"} onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}>
            <Filter />Filters{activeCount > 0 && <Badge tone="accent">{activeCount}</Badge>}
          </Button>
        </div>
        {showFilters && (
          <div className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Account" htmlFor="fa"><NativeSelect id="fa" value={f.account_id} onChange={(e) => set({ account_id: e.target.value })}>
              <option value="">All accounts</option>{accts?.accounts.map((a) => <option key={a.id} value={a.id}>{a.name} · {a.institution}</option>)}</NativeSelect></Field>
            <Field label="Category" htmlFor="fc"><NativeSelect id="fc" value={f.category} onChange={(e) => set({ category: e.target.value })}>
              <option value="">All categories</option>
              {cats.map((c) => <optgroup key={c.id} label={c.name}><option value={c.slug}>All {c.name}</option>{c.children.map((k) => <option key={k.id} value={k.slug}>{k.name}</option>)}</optgroup>)}</NativeSelect></Field>
            <Field label="Type" htmlFor="ft"><NativeSelect id="ft" value={f.type} onChange={(e) => set({ type: e.target.value })}><option value="">All types</option>{TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}</NativeSelect></Field>
            <Field label="Currency" htmlFor="fcur"><NativeSelect id="fcur" value={f.currency} onChange={(e) => set({ currency: e.target.value })}><option value="">Any</option>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
            <Field label="Status" htmlFor="fs"><NativeSelect id="fs" value={f.status} onChange={(e) => set({ status: e.target.value })}><option value="">Any</option><option value="posted">Posted</option><option value="pending">Pending</option><option value="reversed">Reversed</option></NativeSelect></Field>
            <Field label="From" htmlFor="fd1"><Input id="fd1" type="date" value={f.date_from} onChange={(e) => set({ date_from: e.target.value, preset: "" })} /></Field>
            <Field label="To" htmlFor="fd2"><Input id="fd2" type="date" value={f.date_to} onChange={(e) => set({ date_to: e.target.value, preset: "" })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Min amount" htmlFor="fmin"><Input id="fmin" inputMode="decimal" value={f.min_amount} onChange={(e) => set({ min_amount: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
              <Field label="Max amount" htmlFor="fmax"><Input id="fmax" inputMode="decimal" value={f.max_amount} onChange={(e) => set({ max_amount: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-[13px] text-ink-2"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={f.review} onChange={(e) => set({ review: e.target.checked })} />Needs review only</label>
            <div className="sm:col-span-2 lg:col-span-3 flex items-end justify-end">
              <Button variant="ghost" size="sm" onClick={() => { setF({ account_id: "", category: "", type: "", currency: "", status: "", date_from: "", date_to: "", min_amount: "", max_amount: "", preset: "", review: false }); setPage(1); }}><X />Clear all</Button>
            </div>
          </div>
        )}
      </Card>

      <Card className="overflow-hidden">
        {isError ? <ErrorState error={error} retry={refetch} /> : (
          <>
            {/* desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-[13px]">
                <thead className="border-b border-line bg-bg-subtle/60 text-left text-[12px] text-muted">
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id}>{hg.headers.map((h) => (
                      <th key={h.id} scope="col" className={cn("px-4 py-3 font-medium", h.column.id === "amount" && "text-right")}
                        aria-sort={h.column.getIsSorted() ? (h.column.getIsSorted() === "desc" ? "descending" : "ascending") : undefined}>
                        {h.column.getCanSort() ? (
                          <button className="inline-flex items-center gap-1 hover:text-ink" onClick={h.column.getToggleSortingHandler()}>
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            {h.column.getIsSorted() === "desc" ? <ArrowDown className="size-3" /> : h.column.getIsSorted() === "asc" ? <ArrowUp className="size-3" /> : null}
                          </button>
                        ) : flexRender(h.column.columnDef.header, h.getContext())}
                      </th>))}
                    </tr>
                  ))}
                </thead>
                <tbody className={cn("divide-y divide-line transition-opacity", isFetching && !isLoading && "opacity-60")}>
                  {isLoading && Array.from({ length: 10 }).map((_, i) => <tr key={i}><td colSpan={7} className="px-4 py-3"><Skeleton className="h-8" /></td></tr>)}
                  {table.getRowModel().rows.map((r) => (
                    <tr key={r.id} tabIndex={0} onClick={() => open(r.original.id)} onKeyDown={(e) => e.key === "Enter" && open(r.original.id)}
                      className="cursor-pointer transition-colors hover:bg-bg-subtle/70 focus-visible:bg-bg-subtle">
                      {r.getVisibleCells().map((c) => <td key={c.id} className={cn("px-4 py-2.5 align-middle", c.column.id === "description" && "max-w-[320px]")}>{flexRender(c.column.columnDef.cell, c.getContext())}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* mobile list */}
            <ul className="divide-y divide-line md:hidden">
              {isLoading && Array.from({ length: 8 }).map((_, i) => <li key={i} className="p-4"><Skeleton className="h-10" /></li>)}
              {data?.items.map((t) => {
                const pos = Number(t.amount) > 0;
                return (
                  <li key={t.id}>
                    <button onClick={() => open(t.id)} className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-bg-subtle">
                      <CategoryIcon icon={t.category?.icon} color={t.category?.color} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[14px] font-medium text-ink">{t.merchant ?? t.description}</p>
                        <p className="truncate text-[12px] text-muted">{relativeDay(t.date)} · {t.category?.name ?? "Uncategorized"}</p>
                      </div>
                      <div className="text-right">
                        <p className={cn("text-[14px] font-semibold", pos ? "text-pos" : "text-ink")}><Money value={t.amount} currency={t.currency} signed={pos} /></p>
                        {t.status === "pending" && <Badge tone="warn">Pending</Badge>}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
            {data && !data.items.length && <EmptyState icon={SearchX} title="No transactions match" description="Try a different search or clear some filters." />}
            {data && data.total > 0 && (
              <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-[12.5px] text-muted">
                <span>{(page - 1) * data.page_size + 1}–{Math.min(page * data.page_size, data.total)} of {data.total.toLocaleString()}</span>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}><ChevronLeft /></Button>
                  <span className="px-2">Page {page} of {pages}</span>
                  <Button variant="ghost" size="icon-sm" aria-label="Next page" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}><ChevronRight /></Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>
      <TransactionDrawer id={selected} onClose={() => open(null)} />
    </div>
  );
}

function TransactionDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const currency = useCurrency();
  const { data: t, isLoading } = useTransaction(id);
  const { data: cats = [] } = useCategories();
  const invalidate = useInvalidateAll();
  const hidden = useUi((s) => s.privacy);
  const [form, setForm] = React.useState({ category_id: "", type: "", notes: "", tags: "", apply_to_future: false, apply_to_existing: false });
  React.useEffect(() => {
    if (t) setForm({ category_id: String(t.category?.id ?? ""), type: t.type, notes: t.notes ?? "", tags: t.tags.join(", "), apply_to_future: false, apply_to_existing: false });
  }, [t]);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { notes: form.notes, tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean) };
      if (t && String(t.category?.id ?? "") !== form.category_id && form.category_id) Object.assign(body, { category_id: Number(form.category_id), apply_to_future: form.apply_to_future, apply_to_existing: form.apply_to_existing });
      if (t && form.type !== t.type) body.type = form.type;
      return api<{ also_updated: number }>(`/transactions/${id}`, { method: "PATCH", json: body });
    },
    onSuccess: (r) => { toast.success("Transaction updated", { description: r.also_updated ? `${r.also_updated} similar transactions also recategorized` : undefined }); invalidate(); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const review = useMutation({
    mutationFn: (decision: string) => api(`/transactions/${id}/review?decision=${decision}`, { method: "POST" }),
    onSuccess: () => { toast.success("Review saved"); invalidate(); },
  });
  const catChanged = t && form.category_id && String(t.category?.id ?? "") !== form.category_id;
  const row = (k: string, v: React.ReactNode) => (
    <div className="flex items-start justify-between gap-4 py-2.5 text-[13px]"><dt className="text-muted">{k}</dt><dd className="text-right text-ink">{v}</dd></div>
  );
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && onClose()} title={t ? (t.merchant ?? t.description) : "Transaction"} description={t ? formatDate(t.date, "EEEE, d MMMM yyyy · HH:mm") : undefined}
      footer={t && <div className="flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save changes</Button></div>}>
      {isLoading || !t ? <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-40" /></div> : (
        <div className="space-y-6">
          <div className="rounded-2xl bg-bg-subtle p-4 text-center">
            <p className={cn("text-3xl font-semibold tracking-tight", Number(t.amount) > 0 ? "text-pos" : "text-ink")}><Money value={t.amount} currency={t.currency} signed={Number(t.amount) > 0} /></p>
            {t.currency !== currency && t.amount_base && (
              <p className="mt-1 text-[12.5px] text-muted">≈ {formatMoney(t.amount_base, currency, { hidden })}{t.fx && <> · rate {Number(t.fx.rate).toPrecision(6)} ({t.fx.provider}{t.fx.derived ? ", derived" : ""}, {formatDate(t.fx.effective_at)})</>}</p>
            )}
            <div className="mt-2 flex justify-center gap-1.5">
              {t.status === "pending" ? <Badge tone="warn">Pending</Badge> : <Badge tone="pos">Posted</Badge>}
              {t.is_demo && <Badge tone="warn">Demo</Badge>}
            </div>
          </div>
          {(t.duplicate_status === "possible_duplicate" || t.transfer_group?.startsWith("suggested")) && (
            <div className="rounded-2xl border border-warn/40 bg-warn-soft p-3.5 text-[13px]">
              {t.duplicate_status === "possible_duplicate" ? (
                <><p className="font-medium text-ink">This may be a duplicate</p><p className="mt-0.5 text-muted">A similar transaction exists on the same account within 2 days. Nothing was deleted.</p>
                  <div className="mt-2 flex gap-2"><Button size="sm" onClick={() => review.mutate("not_duplicate")}>Keep both</Button><Button size="sm" variant="danger" onClick={() => review.mutate("duplicate")}>Mark as duplicate</Button></div></>
              ) : (
                <><p className="font-medium text-ink">Looks like a transfer between your accounts</p><p className="mt-0.5 text-muted">Transfers are excluded from income and expenses.</p>
                  <div className="mt-2 flex gap-2"><Button size="sm" variant="primary" onClick={() => review.mutate("confirm_transfer")}>Confirm transfer</Button><Button size="sm" onClick={() => review.mutate("reject_transfer")}>Not a transfer</Button></div></>
              )}
            </div>
          )}
          <dl className="divide-y divide-line">
            {row("Original description", <span className="font-mono text-[12px]">{t.description}</span>)}
            {row("Merchant", t.merchant ?? "—")}
            {row("Transaction date", formatDate(t.date, "d MMM yyyy HH:mm"))}
            {row("Posting date", t.posting_date ? formatDate(t.posting_date, "d MMM yyyy") : "—")}
            {row("Account", `${t.account?.name} · ${t.account?.institution}`)}
            {row("Original currency", t.currency)}
            {row("Import source", <Badge tone="outline">{t.source}</Badge>)}
            {row("Reference", <span className="font-mono text-[12px]">{t.external_reference ?? "—"}</span>)}
            {row("Categorized by", t.category_source === "user" ? "You" : t.category_source === "rule" ? "Your rule" : t.category_source === "learned" ? "Learned from your edits" : t.category_source === "dictionary" ? "Merchant match" : "System")}
          </dl>
          <div className="space-y-4">
            <p className="text-[12px] font-semibold uppercase tracking-wider text-muted">Your classification</p>
            <Field label="Category" htmlFor="tc"><NativeSelect id="tc" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
              {cats.map((c) => <optgroup key={c.id} label={c.name}>{c.children.length ? c.children.map((k) => <option key={k.id} value={k.id}>{k.name}</option>) : <option value={c.id}>{c.name}</option>}</optgroup>)}
            </NativeSelect></Field>
            {catChanged && (
              <div className="space-y-2 rounded-xl bg-accent-soft/60 p-3 text-[13px]">
                <label className="flex items-start gap-2"><input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={form.apply_to_future} onChange={(e) => setForm({ ...form, apply_to_future: e.target.checked })} />
                  <span>Apply this category to future transactions from this merchant</span></label>
                {form.apply_to_future && <label className="flex items-start gap-2 pl-6"><input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={form.apply_to_existing} onChange={(e) => setForm({ ...form, apply_to_existing: e.target.checked })} />
                  <span>Also update past uncategorized-by-you transactions</span></label>}
              </div>
            )}
            <Field label="Type" htmlFor="tt" hint="Transfers and investment purchases are excluded from spending."><NativeSelect id="tt" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>{TYPES.map((x) => <option key={x} value={x}>{label(x)}</option>)}</NativeSelect></Field>
            <Field label="Tags" htmlFor="ttags" hint="Comma separated"><Input id="ttags" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="e.g. work, reimbursable" /></Field>
            <Field label="Notes" htmlFor="tn"><textarea id="tn" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="w-full rounded-xl border border-line bg-card px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-4 focus:ring-[var(--ring)]" /></Field>
            <p className="text-[11.5px] text-faint">Edits are stored separately — the original data received from your institution is never modified.</p>
          </div>
        </div>
      )}
    </Sheet>
  );
}
