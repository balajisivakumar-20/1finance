"use client";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, addMonths, subMonths, parse } from "date-fns";
import { toast } from "sonner";
import { AlertTriangle, ChevronLeft, ChevronRight, PiggyBank, Plus, Trash2 } from "lucide-react";
import { CategoryIcon } from "@/components/category-icon";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, NativeSelect, Progress, Skeleton } from "@/components/ui/primitives";
import { Modal } from "@/components/ui/overlay";
import { api, qs, type Category } from "@/lib/api";
import { formatPct, type MoneyStr } from "@/lib/format";
import { useCategories, useCurrency } from "@/lib/hooks";

interface BudgetItem { id: number; category: Category; amount: MoneyStr; spent: MoneyStr; remaining: MoneyStr; percent: MoneyStr; status: "ok" | "warning" | "over" }

export default function BudgetsPage() {
  const currency = useCurrency();
  const [month, setMonth] = React.useState(format(new Date(), "yyyy-MM"));
  const [adding, setAdding] = React.useState(false);
  const [edit, setEdit] = React.useState<BudgetItem | null>(null);
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["budgets", currency, month],
    queryFn: () => api<{ month: string; month_elapsed_pct: MoneyStr; items: BudgetItem[]; totals: { budget: MoneyStr; spent: MoneyStr } }>(`/budgets${qs({ month, currency })}`),
  });
  const del = useMutation({ mutationFn: (id: number) => api(`/budgets/${id}`, { method: "DELETE" }), onSuccess: () => { toast.success("Budget removed"); qc.invalidateQueries({ queryKey: ["budgets"] }); } });
  const m = parse(month, "yyyy-MM", new Date());
  const isCurrent = month === format(new Date(), "yyyy-MM");

  return (
    <div className="space-y-5">
      <PageHeader title="Budgets" subtitle="Monthly spending limits by category. Budgets are shown in your reporting currency."
        action={<Button variant="primary" onClick={() => setAdding(true)}><Plus />New budget</Button>} />
      <Card className="flex flex-wrap items-center gap-4 p-4 sm:p-5">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" aria-label="Previous month" onClick={() => setMonth(format(subMonths(m, 1), "yyyy-MM"))}><ChevronLeft /></Button>
          <span className="min-w-32 text-center font-semibold text-ink">{format(m, "MMMM yyyy")}</span>
          <Button variant="ghost" size="icon-sm" aria-label="Next month" disabled={isCurrent} onClick={() => setMonth(format(addMonths(m, 1), "yyyy-MM"))}><ChevronRight /></Button>
        </div>
        {data && (
          <div className="flex flex-1 flex-wrap items-center justify-end gap-x-6 gap-y-1 text-[13px] text-muted">
            <span>Budgeted <b className="text-ink"><Money value={data.totals.budget} currency={currency} /></b></span>
            <span>Spent <b className="text-ink"><Money value={data.totals.spent} currency={currency} /></b></span>
            {isCurrent && <span>{formatPct(data.month_elapsed_pct, { decimals: 0 })} of month elapsed</span>}
          </div>
        )}
      </Card>
      {isError && <Card><ErrorState error={error} retry={refetch} /></Card>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {isLoading && [0, 1, 2, 3, 4, 5].map((i) => <Card key={i} className="p-5"><Skeleton className="h-24" /></Card>)}
        {data?.items.map((b) => {
          const pct = Number(b.percent ?? 0);
          return (
            <Card key={b.id} className="group p-5">
              <div className="flex items-center gap-3">
                <CategoryIcon icon={b.category.icon} color={b.category.color} />
                <div className="min-w-0 flex-1"><p className="font-semibold text-ink">{b.category.name}</p>
                  <p className="text-[12px] text-muted"><Money value={b.spent} currency={currency} /> of <Money value={b.amount} currency={currency} /></p></div>
                {b.status === "over" ? <Badge tone="neg"><AlertTriangle />Over budget</Badge> : b.status === "warning" ? <Badge tone="warn"><AlertTriangle />Nearly there</Badge> : <Badge tone="pos">On track</Badge>}
              </div>
              <Progress className="mt-4" value={pct} tone={b.status === "over" ? "neg" : b.status === "warning" ? "warn" : "accent"} label={`${b.category.name} budget used`} />
              <div className="mt-2 flex items-center justify-between text-[12.5px]">
                <span className="text-muted">{formatPct(b.percent, { decimals: 0 })} used</span>
                <span className={Number(b.remaining) < 0 ? "font-medium text-neg" : "text-ink-2"}>{Number(b.remaining) < 0 ? "Over by " : ""}<Money value={Number(b.remaining) < 0 ? String(b.remaining).slice(1) : b.remaining} currency={currency} />{Number(b.remaining) >= 0 ? " left" : ""}</span>
              </div>
              <div className="mt-3 flex justify-end gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                <Button size="sm" variant="ghost" onClick={() => setEdit(b)}>Edit</Button>
                <Button size="sm" variant="ghost" aria-label={`Delete ${b.category.name} budget`} onClick={() => del.mutate(b.id)}><Trash2 /></Button>
              </div>
            </Card>
          );
        })}
      </div>
      {data && !data.items.length && <Card><EmptyState icon={PiggyBank} title="No budgets yet" description="Set a monthly limit for categories like groceries or restaurants." action={<Button variant="primary" onClick={() => setAdding(true)}><Plus />Create a budget</Button>} /></Card>}
      <p className="text-[12px] text-faint">Budget rollover is planned as an optional future feature.</p>
      {(adding || edit) && <BudgetDialog edit={edit} onClose={() => { setAdding(false); setEdit(null); qc.invalidateQueries({ queryKey: ["budgets"] }); }} currency={currency} />}
    </div>
  );
}

function BudgetDialog({ edit, onClose, currency }: { edit: BudgetItem | null; onClose: () => void; currency: string }) {
  const { data: cats = [] } = useCategories();
  const [cat, setCat] = React.useState("");
  const [amount, setAmount] = React.useState(edit ? String(edit.amount) : "");
  const save = useMutation({
    mutationFn: () => edit ? api(`/budgets/${edit.id}`, { method: "PATCH", json: { amount } }) : api("/budgets", { method: "POST", json: { category_id: Number(cat), amount, currency } }),
    onSuccess: () => { toast.success("Budget saved"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={edit ? `Edit ${edit.category.name} budget` : "New monthly budget"}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {!edit && <Field label="Category" htmlFor="bc" hint="A parent category covers all its subcategories"><NativeSelect id="bc" value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">Choose…</option>
          {cats.filter((c) => c.type === "expense").map((c) => <optgroup key={c.id} label={c.name}><option value={c.id}>All {c.name}</option>{c.children.map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}</optgroup>)}
        </NativeSelect></Field>}
        <Field label={`Monthly amount (${currency})`} htmlFor="ba"><Input id="ba" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!amount || (!edit && !cat)} loading={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}
