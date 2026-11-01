"use client";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarClock, Car, Flag, History, Home, PartyPopper, Pencil, Plane, Plus, ShieldCheck, ShoppingBag, Target, Trash2, TrendingUp, TriangleAlert } from "lucide-react";
import { MiniLine } from "@/components/charts/charts";
import { Money } from "@/components/money";
import { PageHeader } from "@/components/page-header";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, NativeSelect, Progress, Skeleton } from "@/components/ui/primitives";
import { Modal, Sheet } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { CURRENCIES, formatDate, formatPct, type MoneyStr } from "@/lib/format";
import { useAccounts } from "@/lib/hooks";

interface Entry { id: number; date: string; amount: MoneyStr; currency: string; note: string | null }
interface Goal {
  id: number; name: string; type: string; target: MoneyStr; currency: string; target_date: string | null; current: MoneyStr; remaining: MoneyStr;
  progress_pct: MoneyStr; monthly_plan: MoneyStr | null; estimated_completion: string | null; on_track: boolean | null; linked_account_id: number | null;
  history: { date: string; amount: MoneyStr }[]; contributions: Entry[];
}
const TYPES: { value: string; label: string; icon: React.ElementType }[] = [
  { value: "general", label: "General savings", icon: Target },
  { value: "car", label: "Car / vehicle", icon: Car },
  { value: "purchase", label: "Big purchase", icon: ShoppingBag },
  { value: "event", label: "Event", icon: PartyPopper },
  { value: "holiday", label: "Holiday", icon: Plane },
  { value: "home", label: "Home down payment", icon: Home },
  { value: "emergency", label: "Emergency fund", icon: ShieldCheck },
  { value: "investment", label: "Investment target", icon: TrendingUp },
];
const ICON: Record<string, React.ElementType> = Object.fromEntries(TYPES.map((t) => [t.value, t.icon]));
const today = () => new Date().toLocaleDateString("en-CA"); // local YYYY-MM-DD
const decimal = (v: string, signed = false) => v.replace(signed ? /[^\d.-]/g : /[^\d.]/g, "");

export default function GoalsPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState<Goal | "new" | null>(null);
  const [logFor, setLogFor] = React.useState<{ goal: Goal; entry?: Entry } | null>(null);
  const [openId, setOpenId] = React.useState<number | null>(null);
  const { data, isLoading, isError, error, refetch } = useQuery({ queryKey: ["goals"], queryFn: () => api<{ items: Goal[]; overlaps: { account_id: number; goals: string[] }[] }>("/goals") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["goals"] });
  const del = useMutation({ mutationFn: (id: number) => api(`/goals/${id}`, { method: "DELETE" }), onSuccess: () => { toast.success("Goal deleted"); setOpenId(null); refresh(); } });
  const open = data?.items.find((g) => g.id === openId) ?? null;
  return (
    <div className="space-y-5">
      <PageHeader title="Goals" subtitle="Save with purpose. Progress counts only the amounts you log here — statements and balances never change it."
        action={<Button variant="primary" onClick={() => setEditing("new")}><Plus />New goal</Button>} />
      {data?.overlaps.map((o) => (
        <div key={o.account_id} className="flex items-start gap-2 rounded-2xl bg-warn-soft px-4 py-3 text-[15.5px] text-ink-2">
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
                <span className="grid size-10 place-items-center rounded-2xl bg-accent-soft text-accent-fg"><Icon className="size-5" /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-ink">{g.name}</p>
                  <p className="text-[14.5px] text-muted">{g.target_date ? `Target ${formatDate(g.target_date, "d MMM yyyy")}` : "No target date"}</p>
                </div>
                {pct >= 100 ? <Badge tone="pos">Achieved</Badge> : g.on_track === true ? <Badge tone="pos">On track</Badge> : g.on_track === false ? <Badge tone="warn">Behind</Badge> : null}
              </div>
              <div className="mt-5 flex items-end justify-between">
                <div>
                  <p className="text-[14.5px] text-muted">Saved so far</p>
                  <p className="text-2xl font-semibold tracking-tight text-ink"><Money value={g.current} currency={g.currency} decimals={0} /></p>
                </div>
                <p className="text-[15.5px] text-muted">of <Money value={g.target} currency={g.currency} decimals={0} /></p>
              </div>
              <Progress className="mt-3" value={pct} label={`${g.name} progress`} />
              <div className="mt-2 flex justify-between text-[14.5px] text-muted"><span>{formatPct(g.progress_pct, { decimals: 0 })} complete</span><span><Money value={g.remaining} currency={g.currency} decimals={0} /> to go</span></div>
              {g.history.length > 1 && <div className="mt-3"><MiniLine points={g.history.map((h) => ({ date: h.date, v: h.amount }))} currency={g.currency} height={70} /></div>}
              <div className="mt-auto pt-4">
                <p className="flex items-center gap-1.5 text-[14.5px] text-ink-2"><CalendarClock className="size-3.5 text-muted" />
                  {g.estimated_completion ? <>Est. completion {formatDate(g.estimated_completion, "MMM yyyy")} at <Money value={g.monthly_plan} currency={g.currency} decimals={0} />/month</> : "Set a monthly plan to estimate completion"}</p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" className="flex-1" onClick={() => setLogFor({ goal: g })}><Plus />Log savings</Button>
                  <Button size="sm" variant="ghost" aria-label={`${g.name} savings log`} onClick={() => setOpenId(g.id)}><History />{g.contributions.length}</Button>
                  <Button size="sm" variant="ghost" aria-label={`Edit ${g.name}`} onClick={() => setEditing(g)}><Pencil /></Button>
                  <Button size="sm" variant="ghost" aria-label={`Delete ${g.name}`} onClick={() => confirm(`Delete goal “${g.name}” and all its logged savings?`) && del.mutate(g.id)}><Trash2 /></Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
      {data && !data.items.length && <Card><EmptyState icon={Target} title="No goals yet" description="Saving for a car, an event, a holiday or an emergency fund? Create a goal and log what you put aside." action={<Button variant="primary" onClick={() => setEditing("new")}><Plus />Create a goal</Button>} /></Card>}
      {open && <GoalLogSheet goal={open} onClose={() => setOpenId(null)} onLog={(entry) => setLogFor({ goal: open, entry })} onEdit={() => setEditing(open)} onChanged={refresh} />}
      {editing && <GoalDialog goal={editing === "new" ? undefined : editing} onClose={() => { setEditing(null); refresh(); }} />}
      {logFor && <EntryDialog goal={logFor.goal} entry={logFor.entry} onClose={() => { setLogFor(null); refresh(); }} />}
    </div>
  );
}

function GoalLogSheet({ goal, onClose, onLog, onEdit, onChanged }: { goal: Goal; onClose: () => void; onLog: (e?: Entry) => void; onEdit: () => void; onChanged: () => void }) {
  const del = useMutation({
    mutationFn: (id: number) => api(`/goals/${goal.id}/contributions/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Entry deleted"); onChanged(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={goal.name}
      description={<>Saved <Money value={goal.current} currency={goal.currency} decimals={0} /> of <Money value={goal.target} currency={goal.currency} decimals={0} />{goal.target_date && <> · by {formatDate(goal.target_date)}</>}</>}
      footer={<div className="flex gap-2"><Button className="flex-1" variant="primary" onClick={() => onLog()}><Plus />Log savings</Button><Button onClick={onEdit}><Pencil />Edit goal</Button></div>}>
      {goal.contributions.length ? (
        <ul className="divide-y divide-line">
          {goal.contributions.map((c) => (
            <li key={c.id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-[15.5px] font-medium text-ink">{formatDate(c.date)}</p>
                {c.note && <p className="truncate text-[14.5px] text-muted">{c.note}</p>}
              </div>
              <p className={Number(c.amount) < 0 ? "text-[15.5px] font-medium text-neg" : "text-[15.5px] font-medium text-ink"}><Money value={c.amount} currency={c.currency} /></p>
              <Button size="icon-sm" variant="ghost" aria-label="Edit entry" onClick={() => onLog(c)}><Pencil /></Button>
              <Button size="icon-sm" variant="ghost" aria-label="Delete entry" onClick={() => confirm("Delete this entry?") && del.mutate(c.id)}><Trash2 /></Button>
            </li>
          ))}
        </ul>
      ) : <EmptyState icon={History} title="Nothing logged yet" description="Each time you put money aside for this goal, log it here." />}
    </Sheet>
  );
}

function GoalDialog({ goal, onClose }: { goal?: Goal; onClose: () => void }) {
  const { data: accts } = useAccounts();
  const [f, setF] = React.useState({
    name: goal?.name ?? "", goal_type: goal?.type ?? "general", target_amount: goal ? String(Number(goal.target)) : "", currency: goal?.currency ?? "EUR",
    target_date: goal?.target_date ?? "", monthly_plan: goal?.monthly_plan ? String(Number(goal.monthly_plan)) : "", linked_account_id: goal?.linked_account_id ? String(goal.linked_account_id) : "",
  });
  const save = useMutation({
    mutationFn: () => {
      const json = { ...f, target_date: f.target_date || null, monthly_plan: f.monthly_plan || null, linked_account_id: f.linked_account_id ? Number(f.linked_account_id) : null };
      return goal ? api(`/goals/${goal.id}`, { method: "PATCH", json }) : api("/goals", { method: "POST", json });
    },
    onSuccess: () => { toast.success(goal ? "Goal updated" : "Goal created"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={goal ? `Edit ${goal.name}` : "New savings goal"}>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="sm:col-span-2"><Field label="Goal name" htmlFor="gn"><Input id="gn" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Buy car" /></Field></div>
        <Field label="Type" htmlFor="gt"><NativeSelect id="gt" value={f.goal_type} onChange={(e) => setF({ ...f, goal_type: e.target.value })}>
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</NativeSelect></Field>
        <Field label="Currency" htmlFor="gc" hint={goal ? "Logged amounts keep their numbers" : undefined}><NativeSelect id="gc" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
        <Field label="Target amount" htmlFor="ga"><Input id="ga" inputMode="decimal" value={f.target_amount} onChange={(e) => setF({ ...f, target_amount: decimal(e.target.value) })} /></Field>
        <Field label="Target date" htmlFor="gd" hint="Optional"><Input id="gd" type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} /></Field>
        <Field label="Monthly saving plan" htmlFor="gm" hint="Optional — used to estimate completion"><Input id="gm" inputMode="decimal" value={f.monthly_plan} onChange={(e) => setF({ ...f, monthly_plan: decimal(e.target.value) })} /></Field>
        <Field label="Linked savings account" htmlFor="gl" hint="Reference only — doesn't change progress"><NativeSelect id="gl" value={f.linked_account_id} onChange={(e) => setF({ ...f, linked_account_id: e.target.value })}>
          <option value="">None</option>{accts?.accounts.filter((a) => ["savings", "checking", "brokerage"].includes(a.account_type)).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</NativeSelect></Field>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!f.name.trim() || !Number(f.target_amount)} loading={save.isPending}>{goal ? "Save changes" : "Create goal"}</Button></div>
      </form>
    </Modal>
  );
}

function EntryDialog({ goal, entry, onClose }: { goal: Goal; entry?: Entry; onClose: () => void }) {
  const [f, setF] = React.useState({ amount: entry ? String(Number(entry.amount)) : "", on: entry?.date ?? today(), note: entry?.note ?? "" });
  const save = useMutation({
    mutationFn: () => {
      const json = { amount: f.amount, on: f.on || today(), note: f.note.trim() || null };
      return entry ? api(`/goals/${goal.id}/contributions/${entry.id}`, { method: "PATCH", json }) : api(`/goals/${goal.id}/contributions`, { method: "POST", json });
    },
    onSuccess: () => { toast.success(entry ? "Entry updated" : "Savings logged"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={entry ? "Edit entry" : `Log savings for ${goal.name}`} description="Tracked manually — no money is moved.">
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label={`Amount (${goal.currency})`} htmlFor="ea" hint="Negative to record a withdrawal"><Input id="ea" inputMode="decimal" autoFocus value={f.amount} onChange={(e) => setF({ ...f, amount: decimal(e.target.value, true) })} /></Field>
        <Field label="Date" htmlFor="ed"><Input id="ed" type="date" value={f.on} onChange={(e) => setF({ ...f, on: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Field label="Note" htmlFor="en" hint="Optional"><Input id="en" maxLength={200} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="e.g. Bonus, sold old bike" /></Field></div>
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!Number(f.amount)} loading={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}
