"use client";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { Download, KeyRound, LogOut, Monitor, Moon, Plus, ShieldCheck, Smartphone, Sun, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ConnectionStatus } from "@/components/status";
import { Badge, Button, Card, CardBody, CardHeader, Field, Input, NativeSelect, Switch } from "@/components/ui/primitives";
import { Modal } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { CURRENCIES, ago, formatDate } from "@/lib/format";
import { useAccounts, useCategories, useInvalidateAll, useMe } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { cn, downloadBlob } from "@/lib/utils";

const SECTIONS = ["Profile", "Appearance", "Currency", "Connected accounts", "Categories", "Security", "Data", "Privacy"];

export default function SettingsPage() {
  const [active, setActive] = React.useState("Profile");
  React.useEffect(() => { if (window.location.hash === "#security") setActive("Security"); }, []);
  return (
    <div className="space-y-5">
      <PageHeader title="Settings" />
      <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
        <nav aria-label="Settings sections" className="flex gap-1 overflow-x-auto lg:flex-col">
          {SECTIONS.map((s) => (
            <button key={s} onClick={() => setActive(s)} aria-current={active === s ? "page" : undefined}
              className={cn("whitespace-nowrap rounded-xl px-3 py-2 text-left text-[13.5px] font-medium transition-colors", active === s ? "bg-card text-ink shadow-card" : "text-muted hover:text-ink")}>{s}</button>
          ))}
        </nav>
        <div className="min-w-0 space-y-5">
          {active === "Profile" && <Profile />}
          {active === "Appearance" && <Appearance />}
          {active === "Currency" && <CurrencyPrefs />}
          {active === "Connected accounts" && <Connected />}
          {active === "Categories" && <Categories />}
          {active === "Security" && <Security />}
          {active === "Data" && <DataMgmt />}
          {active === "Privacy" && <Privacy />}
        </div>
      </div>
    </div>
  );
}

function usePrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api("/settings/preferences", { method: "PATCH", json: body }),
    onSuccess: () => { toast.success("Saved"); qc.invalidateQueries(); },
    onError: (e: Error) => toast.error(e.message),
  });
}

function Profile() {
  const { data: me } = useMe();
  const [name, setName] = React.useState(me?.display_name ?? "");
  const save = usePrefs();
  return (
    <Card><CardHeader title="Profile" /><CardBody className="space-y-4">
      <div className="flex items-center gap-4"><span className="grid size-14 place-items-center rounded-full bg-accent-soft text-lg font-semibold text-accent">{name.slice(0, 1).toUpperCase()}</span>
        <p className="text-[13px] text-muted">Avatar uses your initials — 1Finance doesn&apos;t upload photos.</p></div>
      <Field label="Display name" htmlFor="dn"><Input id="dn" value={name} onChange={(e) => setName(e.target.value)} className="max-w-sm" /></Field>
      <Field label="Email" htmlFor="em"><Input id="em" value={me?.email ?? ""} disabled className="max-w-sm" /></Field>
      <Button variant="primary" onClick={() => save.mutate({ display_name: name })} loading={save.isPending}>Save profile</Button>
    </CardBody></Card>
  );
}

function Appearance() {
  const { theme, setTheme } = useTheme();
  const save = usePrefs();
  return (
    <Card><CardHeader title="Appearance" description="Choose how 1Finance looks on this device" /><CardBody>
      <div className="grid gap-3 sm:grid-cols-3">
        {([["light", "Light", Sun], ["dark", "Dark", Moon], ["system", "System", Monitor]] as const).map(([v, l, I]) => (
          <button key={v} onClick={() => { setTheme(v); save.mutate({ theme: v }); }} aria-pressed={theme === v}
            className={cn("rounded-2xl border p-4 text-left transition-colors", theme === v ? "border-accent bg-accent-soft/50" : "border-line hover:bg-bg-subtle")}>
            <I className="size-5 text-ink-2" /><p className="mt-3 font-medium text-ink">{l}</p>
          </button>
        ))}
      </div>
    </CardBody></Card>
  );
}

function CurrencyPrefs() {
  const { data: me } = useMe();
  const p = me?.preferences;
  const setOverride = useUi((s) => s.setCurrency);
  const save = usePrefs();
  const [f, setF] = React.useState({ base_currency: p?.base_currency ?? "EUR", number_format: p?.number_format ?? "en-IE", date_format: p?.date_format ?? "d MMM yyyy", timezone: p?.timezone ?? "Europe/Dublin" });
  return (
    <Card><CardHeader title="Currency & formatting" description="Original currencies are always preserved; this sets how totals are reported." /><CardBody className="grid gap-4 sm:grid-cols-2">
      <Field label="Base reporting currency" htmlFor="bc"><NativeSelect id="bc" value={f.base_currency} onChange={(e) => setF({ ...f, base_currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
      <Field label="Number format" htmlFor="nf"><NativeSelect id="nf" value={f.number_format} onChange={(e) => setF({ ...f, number_format: e.target.value })}><option value="en-IE">1,234.56</option><option value="de-DE">1.234,56</option><option value="en-IN">1,23,456.78</option></NativeSelect></Field>
      <Field label="Date format" htmlFor="df"><NativeSelect id="df" value={f.date_format} onChange={(e) => setF({ ...f, date_format: e.target.value })}><option>d MMM yyyy</option><option>dd/MM/yyyy</option><option>yyyy-MM-dd</option></NativeSelect></Field>
      <Field label="Time zone" htmlFor="tz"><NativeSelect id="tz" value={f.timezone} onChange={(e) => setF({ ...f, timezone: e.target.value })}>{["Europe/Dublin", "Europe/London", "Asia/Kolkata", "America/New_York", "UTC"].map((t) => <option key={t}>{t}</option>)}</NativeSelect></Field>
      <div className="sm:col-span-2"><Button variant="primary" loading={save.isPending} onClick={() => { setOverride(null); save.mutate(f); }}>Save preferences</Button></div>
    </CardBody></Card>
  );
}

function Connected() {
  const { data } = useAccounts();
  const invalidate = useInvalidateAll();
  const sync = useMutation({ mutationFn: (id: number) => api<{ status: string; error: string | null }>(`/connections/${id}/sync`, { method: "POST" }),
    onSuccess: (r) => { r.status === "succeeded" ? toast.success("Synchronized") : toast.error(r.error ?? "Sync failed"); invalidate(); } });
  return (
    <Card><CardHeader title="Connected accounts" description="All integrations are read-only." /><CardBody>
      <ul className="divide-y divide-line">
        {data?.connections.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-0 flex-1"><p className="font-medium text-ink">{c.institution} {c.is_demo && <Badge tone="warn">Demo</Badge>}</p>
              <p className="text-[12px] text-muted">{c.connector} · last success {ago(c.last_successful_sync)}{c.last_error ? ` · ${c.last_error}` : ""}</p></div>
            <ConnectionStatus status={c.status} lastSync={c.last_successful_sync} />
            {c.connector !== "manual" && <Button size="sm" loading={sync.isPending && sync.variables === c.id} onClick={() => sync.mutate(c.id)}>Sync now</Button>}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[12px] text-muted">Disconnect or rename individual accounts from the Accounts page.</p>
    </CardBody></Card>
  );
}

function Categories() {
  const { data: cats = [] } = useCategories();
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => api<{ id: number; pattern: string; field: string; kind: string; priority: number; category: { id: number; name: string } }[]>("/categorization-rules") });
  const [newCat, setNewCat] = React.useState({ name: "", parent_id: "" });
  const [newRule, setNewRule] = React.useState({ pattern: "", category_id: "" });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["categories"] }); qc.invalidateQueries({ queryKey: ["rules"] }); };
  const addCat = useMutation({ mutationFn: () => api("/categories", { method: "POST", json: { name: newCat.name, parent_id: newCat.parent_id ? Number(newCat.parent_id) : null } }), onSuccess: () => { toast.success("Category added"); setNewCat({ name: "", parent_id: "" }); refresh(); }, onError: (e: Error) => toast.error(e.message) });
  const delCat = useMutation({ mutationFn: (id: number) => api(`/categories/${id}`, { method: "DELETE" }), onSuccess: refresh, onError: (e: Error) => toast.error(e.message) });
  const addRule = useMutation({ mutationFn: () => api("/categorization-rules", { method: "POST", json: { pattern: newRule.pattern, category_id: Number(newRule.category_id) } }), onSuccess: () => { toast.success("Rule added — applies to new transactions"); setNewRule({ pattern: "", category_id: "" }); refresh(); }, onError: (e: Error) => toast.error(e.message) });
  const delRule = useMutation({ mutationFn: (id: number) => api(`/categorization-rules/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return (
    <>
      <Card><CardHeader title="Categories" description="System categories plus your own. Deleting a custom category keeps its transactions." /><CardBody>
        <form className="mb-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); addCat.mutate(); }}>
          <Input aria-label="New category name" placeholder="New category" value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })} className="w-48" />
          <NativeSelect aria-label="Parent category" value={newCat.parent_id} onChange={(e) => setNewCat({ ...newCat, parent_id: e.target.value })} className="w-48"><option value="">Top level</option>{cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</NativeSelect>
          <Button type="submit" disabled={!newCat.name} loading={addCat.isPending}><Plus />Add</Button>
        </form>
        <div className="grid gap-3 sm:grid-cols-2">
          {cats.map((c) => (
            <div key={c.id} className="rounded-2xl border border-line p-3">
              <p className="flex items-center gap-2 font-medium text-ink"><span className="size-2.5 rounded-full" style={{ background: c.color ?? "var(--muted)" }} />{c.name}{c.custom && <Badge tone="accent">Custom</Badge>}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">{c.children.map((k) => (
                <span key={k.id} className="inline-flex items-center gap-1 rounded-full bg-bg-subtle px-2 py-0.5 text-[12px] text-ink-2">{k.name}
                  {k.custom && <button aria-label={`Delete ${k.name}`} onClick={() => delCat.mutate(k.id)} className="text-faint hover:text-neg">×</button>}</span>))}</div>
            </div>
          ))}
        </div>
      </CardBody></Card>
      <Card><CardHeader title="Categorization rules" description="Applied first, before merchant matching. “Learned” rules come from your corrections." /><CardBody>
        <form className="mb-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); addRule.mutate(); }}>
          <Input aria-label="Description contains" placeholder="Description contains… (or /regex/)" value={newRule.pattern} onChange={(e) => setNewRule({ ...newRule, pattern: e.target.value })} className="w-64" />
          <NativeSelect aria-label="Category" value={newRule.category_id} onChange={(e) => setNewRule({ ...newRule, category_id: e.target.value })} className="w-52"><option value="">Category…</option>
            {cats.map((c) => <optgroup key={c.id} label={c.name}>{(c.children.length ? c.children : [c]).map((k) => <option key={k.id} value={k.id}>{k.name}</option>)}</optgroup>)}</NativeSelect>
          <Button type="submit" disabled={newRule.pattern.length < 2 || !newRule.category_id}><Plus />Add rule</Button>
        </form>
        {!rules.data?.length ? <p className="text-[13px] text-muted">No rules yet. Correct a transaction&apos;s category and choose “apply to future” to teach 1Finance.</p> : (
          <ul className="divide-y divide-line">{rules.data.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-2.5 text-[13px]">
              <Badge tone={r.kind === "learned" ? "info" : "neutral"}>{r.kind}</Badge>
              <code className="flex-1 truncate font-mono text-[12px] text-ink">{r.pattern}</code>
              <span className="text-muted">→ {r.category.name}</span>
              <Button variant="ghost" size="icon-sm" aria-label="Delete rule" onClick={() => delRule.mutate(r.id)}><Trash2 /></Button>
            </li>))}</ul>
        )}
      </CardBody></Card>
    </>
  );
}

function Security() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: () => api<{ id: number; user_agent: string; ip: string; last_seen_at: string; created_at: string; current: boolean }[]>("/auth/sessions") });
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => api<{ id: number; action: string; timestamp: string; ip: string | null }[]>("/settings/audit-log") });
  const revokeOthers = useMutation({ mutationFn: () => api<{ revoked: number }>("/auth/sessions/revoke-others", { method: "POST" }), onSuccess: (r) => { toast.success(`Signed out of ${r.revoked} other session(s)`); qc.invalidateQueries({ queryKey: ["sessions"] }); } });
  const revoke = useMutation({ mutationFn: (id: number) => api(`/auth/sessions/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }) });
  const [mfa, setMfa] = React.useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = React.useState("");
  const setup = useMutation({ mutationFn: () => api<{ secret: string; otpauth_uri: string }>("/auth/mfa/setup", { method: "POST" }), onSuccess: setMfa, onError: (e: Error) => toast.error(e.message) });
  const enable = useMutation({ mutationFn: () => api("/auth/mfa/enable", { method: "POST", json: { code } }), onSuccess: () => { toast.success("Two-factor authentication enabled"); setMfa(null); qc.invalidateQueries({ queryKey: ["me"] }); }, onError: (e: Error) => toast.error(e.message) });
  return (
    <>
      <Card><CardHeader title="Sign-in methods" /><CardBody className="space-y-3">
        <div className="flex items-center gap-3 rounded-2xl border border-line p-4">
          <ShieldCheck className="size-5 text-accent" /><div className="flex-1"><p className="font-medium text-ink">Authenticator app (TOTP)</p><p className="text-[12.5px] text-muted">Required for exports and data deletion once enabled.</p></div>
          {me?.mfa_enabled ? <Badge tone="pos">Enabled</Badge> : <Button size="sm" variant="primary" loading={setup.isPending} onClick={() => setup.mutate()}>Set up</Button>}
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-line p-4 opacity-80">
          <KeyRound className="size-5 text-ink-2" /><div className="flex-1"><p className="font-medium text-ink">Passkeys</p><p className="text-[12.5px] text-muted">Available once the server is configured with an HTTPS origin and relying-party ID.</p></div>
          <Badge tone="outline">Not configured</Badge>
        </div>
        <p className="text-[12.5px] text-muted">Sessions expire after 30 minutes of inactivity and 12 hours in total.</p>
      </CardBody></Card>
      <Card><CardHeader title="Active sessions" action={<Button size="sm" onClick={() => revokeOthers.mutate()}><LogOut />Sign out other devices</Button>} /><CardBody>
        <ul className="divide-y divide-line">{sessions.data?.map((s) => (
          <li key={s.id} className="flex items-center gap-3 py-3 text-[13px]"><Smartphone className="size-4 text-muted" />
            <div className="min-w-0 flex-1"><p className="truncate text-ink">{s.user_agent || "Unknown device"}</p><p className="text-[12px] text-muted">{s.ip} · active {ago(s.last_seen_at)}</p></div>
            {s.current ? <Badge tone="pos">This device</Badge> : <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>Revoke</Button>}</li>))}</ul>
      </CardBody></Card>
      <Card><CardHeader title="Security activity" /><CardBody>
        <ul className="divide-y divide-line text-[13px]">{audit.data?.slice(0, 15).map((a) => (
          <li key={a.id} className="flex justify-between gap-3 py-2"><span className="capitalize text-ink">{a.action.replaceAll("_", " ")}</span><span className="text-muted">{formatDate(a.timestamp, "d MMM yyyy HH:mm")}{a.ip ? ` · ${a.ip}` : ""}</span></li>))}</ul>
      </CardBody></Card>
      {mfa && (
        <Modal open onOpenChange={(o) => !o && setMfa(null)} title="Set up two-factor authentication" description="Add this key to your authenticator app, then enter the 6-digit code.">
          <div className="space-y-4">
            <div className="rounded-xl bg-bg-subtle p-3 text-center font-mono text-[13px] tracking-wider break-all">{mfa.secret}</div>
            <Field label="Verification code" htmlFor="mc"><Input id="mc" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
            <div className="flex justify-end"><Button variant="primary" disabled={code.length !== 6} loading={enable.isPending} onClick={() => enable.mutate()}>Enable</Button></div>
          </div>
        </Modal>
      )}
    </>
  );
}

function DataMgmt() {
  const qc = useQueryClient();
  const imports = useQuery({ queryKey: ["imports"], queryFn: () => api<{ id: number; file_name: string; source: string; status: string; imported_at: string; summary: { rows?: number } }[]>("/settings/imports") });
  const [confirm, setConfirm] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const exportAll = async () => {
    try { downloadBlob(await api<Blob>("/settings/export"), "1finance-export.json"); toast.success("Export downloaded"); } catch (e) { toast.error((e as Error).message); }
  };
  const revert = useMutation({ mutationFn: (id: number) => api<{ deleted_transactions: number }>(`/settings/imports/${id}`, { method: "DELETE" }), onSuccess: (r) => { toast.success(`Removed ${r.deleted_transactions} imported transactions`); qc.invalidateQueries(); }, onError: (e: Error) => toast.error(e.message) });
  const wipe = useMutation({ mutationFn: () => api("/settings/delete-data", { method: "POST", json: { confirm } }), onSuccess: () => { toast.success("All financial data deleted"); setOpen(false); qc.invalidateQueries(); }, onError: (e: Error) => toast.error(e.message) });
  return (
    <>
      <Card><CardHeader title="Export" description="Download everything as JSON, or use Reports for PDF/Excel." /><CardBody><Button onClick={exportAll}><Download />Export all data</Button></CardBody></Card>
      <Card><CardHeader title="Statement imports" description="Undo an import to remove exactly the transactions it added." /><CardBody>
        {!imports.data?.length ? <p className="text-[13px] text-muted">No imports yet. Import statements from an account&apos;s menu on the Accounts page.</p> : (
          <ul className="divide-y divide-line text-[13px]">{imports.data.map((i) => (
            <li key={i.id} className="flex items-center gap-3 py-2.5"><span className="flex-1 truncate text-ink">{i.file_name}</span><Badge tone="outline">{i.status}</Badge>
              <span className="text-muted">{formatDate(i.imported_at)}</span>
              {i.status === "committed" && <Button size="sm" variant="ghost" onClick={() => revert.mutate(i.id)}>Undo</Button>}</li>))}</ul>)}
      </CardBody></Card>
      <Card className="border-neg/30"><CardHeader title="Delete application data" description="Removes all accounts, connections, transactions, goals and budgets. Your login remains." /><CardBody>
        <Button variant="danger" onClick={() => setOpen(true)}><Trash2 />Delete all data</Button>
      </CardBody></Card>
      <Modal open={open} onOpenChange={setOpen} title="Delete all financial data?" description="This permanently removes everything. Type DELETE to confirm.">
        <Input aria-label="Type DELETE" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <div className="mt-4 flex justify-end gap-2"><Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="danger" disabled={confirm !== "DELETE"} loading={wipe.isPending} onClick={() => wipe.mutate()}>Delete permanently</Button></div>
      </Modal>
    </>
  );
}

function Privacy() {
  const { data: me } = useMe();
  const save = usePrefs();
  const { privacy, togglePrivacy } = useUi();
  const row = (title: string, desc: string, control: React.ReactNode) => (
    <div className="flex items-center justify-between gap-4 py-4"><div><p className="font-medium text-ink">{title}</p><p className="text-[12.5px] text-muted">{desc}</p></div>{control}</div>
  );
  return (
    <Card><CardHeader title="Privacy" description="1Finance has no ads, sells no data and uses no third-party analytics." /><CardBody className="divide-y divide-line">
      {row("AI-assisted categorization", "Allow sending uncertain transaction descriptions to an AI service. Off by default; basic categorization never needs it.",
        <Switch label="AI-assisted categorization" checked={!!me?.preferences?.ai_categorization_consent} onCheckedChange={(v) => save.mutate({ ai_categorization_consent: v })} />)}
      {row("Hide balances on screen", "Masks amounts everywhere until you toggle it off (also in the header).", <Switch label="Hide balances" checked={privacy} onCheckedChange={togglePrivacy} />)}
      {row("Notification content", "System notifications never include balances or transaction details.", <Badge tone="pos">Always on</Badge>)}
      {row("Data retention", "Disconnected accounts keep their history until you delete it.", <Badge tone="outline">Keep until deleted</Badge>)}
    </CardBody></Card>
  );
}

