"use client";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarClock, Flag, Home, Plane, Plus, ShieldCheck, Target, Trash2, TrendingUp, TriangleAlert } from "lucide-react";
import { MiniLine } from "@/components/charts/charts";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, NativeSelect, Progress, Skeleton } from "@/components/ui/primitives";
import { Modal } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { CURRENCIES, formatDate, formatPct, type MoneyStr } from "@/lib/format";
import { useAccounts } from "@/lib/hooks";

interface Goal {
  id: number; name: string; type: string; target: MoneyStr; currency: string; target_date: string | null; current: MoneyStr; remaining: MoneyStr;
  progress_pct: MoneyStr; monthly_plan: MoneyStr; estimated_completion: string | null; on_track: boolean | null; linked_account_id: number | null;
  history: { date: string; amount: MoneyStr }[];
}
const ICON: Record<string, React.ElementType> = { emergency: ShieldCheck, holiday: Plane, home: Home, investment: TrendingUp, general: Target };

export default function GoalsPage() {
  const qc = useQueryClient();
  const [adding, setAdding] = React.useState(false);
  const [contrib, setContrib] = React.useState<Goal | null>(null);
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["goals"], queryFn: () => api<{ items: Goal[]; overlaps: { account_id: number; goals: string[] }[] }>("/goals") });
  const del = useMutation({ mutationFn: (id: number) => api(`/goals/${id}`, { method: "DELETE" }), onSuccess: () => { toast.success("Goal deleted"); qc.invalidateQueries({ queryKey: ["goals"] }); } });
  return (
    <div className="space-y-5">
      <PageHeader title="Goals" subtitle="Save with purpose. Progress is based on the contributions you allocate."
        action={<Button variant="primary" onClick={() => setAdding(true)}><Plus />New goal</Button>} />
      {data?.overlaps.map((o) => (
        <div key={o.account_id} className="flex items-start gap-2 rounded-2xl bg-warn-soft px-4 py-3 text-[13px] text-ink-2">
          <TriangleAlert className="mt-0.5 size-4 text-warn" />The same account is linked to {o.goals.join(" and ")} — the same money may be counted twice.
        </div>
      ))}
      {isError && <Card><ErrorState error={error} retry={refetch} /></Card>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {isLoading && [0, 1, 2].map((i) => <Card key={i} className="p-5"><Skeleton className="h-48" /></Card>)}
        {data?.items.map((g) => {
          const Icon = ICON[g.type] ?? Flag;
          const pct = Number(g.progress_pct);
          return (
            <Card key={g.id} className="flex flex-col p-5">
              <div className="flex items-start gap-3">
                <span className="grid size-10 place-items-center rounded-2xl bg-accent-soft text-accent"><Icon className="size-5" /></span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-ink">{g.name}</p>
                  <p className="text-[12px] text-muted">{g.target_date ? `Target ${formatDate(g.target_date, "MMM yyyy")}` : "No target date"}</p>
                </div>
                {pct >= 100 ? <Badge tone="pos">Achieved</Badge> : g.on_track === true ? <Badge tone="pos">On track</Badge> : g.on_track === false ? <Badge tone="warn">Behind</Badge> : null}
              </div>
              <div className="mt-5 flex items-end justify-between">
                <p className="text-2xl font-semibold tracking-tight text-ink"><Money value={g.current} currency={g.currency} decimals={0} /></p>
                <p className="text-[13px] text-muted">of <Money value={g.target} currency={g.currency} decimals={0} /></p>
              </div>
              <Progress className="mt-3" value={pct} label={`${g.name} progress`} />
              <div className="mt-2 flex justify-between text-[12px] text-muted"><span>{formatPct(g.progress_pct, { decimals: 0 })} complete</span><span><Money value={g.remaining} currency={g.currency} decimals={0} /> to go</span></div>
              {g.history.length > 1 && <div className="mt-3"><MiniLine points={g.history.map((h) => ({ date: h.date, v: h.amount }))} currency={g.currency} height={70} /></div>}
              <div className="mt-auto pt-4">
                <p className="flex items-center gap-1.5 text-[12px] text-ink-2"><CalendarClock className="size-3.5 text-muted" />
                  {g.estimated_completion ? <>Est. completion {formatDate(g.estimated_completion, "MMM yyyy")} at <Money value={g.monthly_plan} currency={g.currency} decimals={0} />/month</> : "Set a monthly plan to estimate completion"}</p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" className="flex-1" onClick={() => setContrib(g)}><Plus />Add contribution</Button>
                  <Button size="sm" variant="ghost" aria-label={`Delete ${g.name}`} onClick={() => confirm(`Delete goal “${g.name}”?`) && del.mutate(g.id)}><Trash2 /></Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
      {data && !data.items.length && <Card><EmptyState icon={Target} title="No goals yet" description="Create an emergency fund, holiday fund or any savings target." action={<Button variant="primary" onClick={() => setAdding(true)}><Plus />Create a goal</Button>} /></Card>}
      {adding && <GoalDialog onClose={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["goals"] }); }} />}
      {contrib && <ContributionDialog goal={contrib} onClose={() => { setContrib(null); qc.invalidateQueries({ queryKey: ["goals"] }); }} />}
    </div>
  );
}

function GoalDialog({ onClose }: { onClose: () => void }) {
  const { data: accts } = useAccounts();
  const [f, setF] = React.useState({ name: "", goal_type: "general", target_amount: "", currency: "EUR", target_date: "", monthly_plan: "", linked_account_id: "" });
  const save = useMutation({
    mutationFn: () => api("/goals", { method: "POST", json: { ...f, target_date: f.target_date || null, monthly_plan: f.monthly_plan || null, linked_account_id: f.linked_account_id ? Number(f.linked_account_id) : null } }),
    onSuccess: () => { toast.success("Goal created"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="New savings goal">
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="sm:col-span-2"><Field label="Goal name" htmlFor="gn"><Input id="gn" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Emergency fund" /></Field></div>
        <Field label="Type" htmlFor="gt"><NativeSelect id="gt" value={f.goal_type} onChange={(e) => setF({ ...f, goal_type: e.target.value })}>
          <option value="emergency">Emergency fund</option><option value="holiday">Holiday</option><option value="home">Home down payment</option><option value="investment">Investment target</option><option value="general">General savings</option></NativeSelect></Field>
        <Field label="Currency" htmlFor="gc"><NativeSelect id="gc" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
        <Field label="Target amount" htmlFor="ga"><Input id="ga" inputMode="decimal" value={f.target_amount} onChange={(e) => setF({ ...f, target_amount: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
        <Field label="Target date" htmlFor="gd"><Input id="gd" type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} /></Field>
        <Field label="Monthly contribution plan" htmlFor="gm" hint="Used to estimate completion"><Input id="gm" inputMode="decimal" value={f.monthly_plan} onChange={(e) => setF({ ...f, monthly_plan: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
        <Field label="Linked savings account" htmlFor="gl" hint="Optional"><NativeSelect id="gl" value={f.linked_account_id} onChange={(e) => setF({ ...f, linked_account_id: e.target.value })}>
          <option value="">None — allocate manually</option>{accts?.accounts.filter((a) => ["savings", "checking", "brokerage"].includes(a.account_type)).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</NativeSelect></Field>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!f.name || !f.target_amount} loading={save.isPending}>Create goal</Button></div>
      </form>
    </Modal>
  );
}

function ContributionDialog({ goal, onClose }: { goal: Goal; onClose: () => void }) {
  const [amount, setAmount] = React.useState("");
  const save = useMutation({
    mutationFn: () => api(`/goals/${goal.id}/contributions`, { method: "POST", json: { amount } }),
    onSuccess: () => { toast.success("Contribution recorded"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={`Contribute to ${goal.name}`} description="Records an allocation; no money is moved.">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label={`Amount (${goal.currency})`} htmlFor="ca" hint="Use a negative number to record a withdrawal"><Input id="ca" inputMode="decimal" autoFocus value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.-]/g, ""))} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!amount} loading={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}
