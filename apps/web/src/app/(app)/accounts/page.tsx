"use client";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { motion, AnimatePresence } from "motion/react";
import { Building2, CheckCircle2, FileUp, KeyRound, Landmark, MoreHorizontal, Pencil, Plus, RefreshCw, ShieldCheck, Unplug, Upload } from "lucide-react";
import { ACCOUNT_TYPE_LABEL, InstitutionAvatar } from "@/components/category-icon";
import { Money } from "@/components/money";
import { ConnectionStatus } from "@/components/status";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Field, Input, NativeSelect, Skeleton, Stat, Switch } from "@/components/ui/primitives";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger, Modal } from "@/components/ui/overlay";
import { api, type AccountItem, type Connector } from "@/lib/api";
import { CURRENCIES, formatDate, formatMoney } from "@/lib/format";
import { useAccounts, useConnectors, useCurrency, useInvalidateAll } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";

export default function AccountsPage() {
  const currency = useCurrency();
  const { data, isLoading, isError, error, refetch } = useAccounts();
  const params = useSearchParams();
  const router = useRouter();
  const [adding, setAdding] = React.useState(params.get("add") === "1");
  const [rename, setRename] = React.useState<AccountItem | null>(null);
  const [disconnect, setDisconnect] = React.useState<AccountItem | null>(null);
  const [importFor, setImportFor] = React.useState<AccountItem | null>(null);
  const invalidate = useInvalidateAll();
  const sync = useMutation({
    mutationFn: (connId: number) => api<{ status: string; error: string | null }>(`/connections/${connId}/sync`, { method: "POST" }),
    onSuccess: (r) => { r.status === "succeeded" ? toast.success("Account synchronized") : toast.error(r.error ?? "Sync failed"); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });

  const groups = React.useMemo(() => {
    const acc = data?.accounts ?? [];
    return [
      { title: "Banking", items: acc.filter((a) => ["checking", "savings", "cash"].includes(a.account_type)) },
      { title: "Investments", items: acc.filter((a) => ["brokerage", "investment", "fixed_deposit"].includes(a.account_type)) },
      { title: "Credit & loans", items: acc.filter((a) => ["credit_card", "loan"].includes(a.account_type)) },
      { title: "Other", items: acc.filter((a) => a.account_type === "other") },
    ].filter((g) => g.items.length);
  }, [data]);

  return (
    <div className="space-y-6">
      <PageHeader title="Accounts" subtitle="Every connected and manually tracked account in one place."
        action={<Button variant="primary" onClick={() => setAdding(true)}><Plus />Add account</Button>} />

      <Card>
        <div className="grid grid-cols-2 gap-5 p-5 sm:p-6 lg:grid-cols-4">
          {isLoading ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />) : data && (
            <>
              <Stat label="Bank balances"><Money value={data.summary.bank as string} currency={currency} /></Stat>
              <Stat label="Investments"><Money value={data.summary.investments as string} currency={currency} /></Stat>
              <Stat label="Outstanding debt" sub="Connected credit accounts"><Money value={data.summary.debt as string} currency={currency} /></Stat>
              <Stat label="Connected" sub="Active connections">{String(data.summary.connected)}</Stat>
            </>
          )}
        </div>
      </Card>

      {isError && <Card><ErrorState error={error} retry={refetch} /></Card>}
      {data && !data.accounts.length && (
        <Card><EmptyState icon={Building2} title="No accounts yet" description="Connect a brokerage, import a bank statement or add a manual account."
          action={<Button variant="primary" onClick={() => setAdding(true)}><Plus />Add your first account</Button>} /></Card>
      )}

      {groups.map((g) => (
        <section key={g.title} aria-labelledby={`g-${g.title}`}>
          <h2 id={`g-${g.title}`} className="mb-3 text-[15.5px] font-semibold uppercase tracking-[0.06em] text-muted">{g.title}</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {g.items.map((a, i) => (
              <motion.div key={a.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
                <Card className="group flex h-full flex-col p-5 transition-shadow hover:shadow-pop">
                  <div className="flex items-start gap-3">
                    <InstitutionAvatar slug={a.institution_slug} name={a.institution} type={a.account_type} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-ink">{a.name}</p>
                      <p className="truncate text-[15px] text-muted">{a.institution} · {ACCOUNT_TYPE_LABEL[a.account_type]}{a.masked_reference ? ` · ${a.masked_reference}` : ""}</p>
                    </div>
                    <Menu>
                      <MenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label={`Actions for ${a.name}`}><MoreHorizontal /></Button></MenuTrigger>
                      <MenuContent>
                        <MenuItem onSelect={() => router.push(`/transactions?account_id=${a.id}`)}><Landmark />View transactions</MenuItem>
                        {a.connection_id && a.connector !== "manual" && <MenuItem onSelect={() => sync.mutate(a.connection_id!)}><RefreshCw />Synchronize</MenuItem>}
                        <MenuItem onSelect={() => setRename(a)}><Pencil />Rename / edit</MenuItem>
                        {["checking", "savings", "credit_card", "cash"].includes(a.account_type) && <MenuItem onSelect={() => setImportFor(a)}><Upload />Import statement</MenuItem>}
                        <MenuSeparator />
                        {a.connection_id && <MenuItem onSelect={() => setDisconnect(a)} className="text-neg data-[highlighted]:text-neg"><Unplug />Disconnect</MenuItem>}
                      </MenuContent>
                    </Menu>
                  </div>
                  <div className="mt-5 flex items-end justify-between gap-3">
                    <div>
                      <p className="text-2xl font-semibold tracking-tight text-ink"><Money value={a.balance} currency={a.currency} /></p>
                      {a.currency !== currency && <p className="mt-0.5 text-[14.5px] text-muted">≈ <Money value={a.balance_base} currency={currency} /></p>}
                      {a.investments_value_local && <p className="mt-0.5 text-[14.5px] text-muted">Cash <Money value={a.cash_balance} currency={a.currency} /> · holdings included</p>}
                    </div>
                    <Badge tone="outline">{a.currency}</Badge>
                  </div>
                  <div className="mt-auto flex items-center justify-between gap-2 border-t border-line pt-3 mt-4">
                    <ConnectionStatus status={a.connection_status} lastSync={a.last_sync} stale={a.is_stale} />
                    <div className="flex gap-1">
                      {a.is_demo && <Badge tone="warn">Demo</Badge>}
                      {!a.counts_toward_net_worth && <Badge tone="outline">Excluded from net worth</Badge>}
                    </div>
                  </div>
                  {a.connection_status === "reauth_required" && (
                    <Button size="sm" variant="primary" className="mt-3" onClick={() => setAdding(true)}><KeyRound />Reconnect</Button>
                  )}
                </Card>
              </motion.div>
            ))}
          </div>
        </section>
      ))}

      <ManualAssets />

      <AddAccountWizard open={adding} onOpenChange={(o) => { setAdding(o); if (!o && params.get("add")) router.replace("/accounts"); }} />
      {rename && <RenameDialog account={rename} onClose={() => setRename(null)} />}
      {disconnect && <DisconnectDialog account={disconnect} onClose={() => setDisconnect(null)} />}
      {importFor && <ImportDialog account={importFor} onClose={() => setImportFor(null)} />}
    </div>
  );
}

function RenameDialog({ account, onClose }: { account: AccountItem; onClose: () => void }) {
  const [name, setName] = React.useState(account.nickname ?? "");
  const [counts, setCounts] = React.useState(account.counts_toward_net_worth);
  const invalidate = useInvalidateAll();
  const save = useMutation({
    mutationFn: () => api(`/accounts/${account.id}`, { method: "PATCH", json: { nickname: name, counts_toward_net_worth: counts } }),
    onSuccess: () => { toast.success("Account updated"); invalidate(); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Edit account" description={`${account.institution} · ${account.official_name}`}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Nickname" htmlFor="nick" hint="Leave empty to use the institution's name"><Input id="nick" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={account.official_name} /></Field>
        <label className="flex items-center justify-between gap-4 rounded-xl border border-line p-3">
          <span><span className="block text-sm font-medium text-ink">Include in net worth</span><span className="text-[14.5px] text-muted">Turn off if this balance is already represented elsewhere, to avoid double counting.</span></span>
          <Switch checked={counts} onCheckedChange={setCounts} label="Include in net worth" />
        </label>
        <div className="flex justify-end gap-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}

function DisconnectDialog({ account, onClose }: { account: AccountItem; onClose: () => void }) {
  const [deleteData, setDeleteData] = React.useState(false);
  const invalidate = useInvalidateAll();
  const go = useMutation({
    mutationFn: () => api(`/connections/${account.connection_id}/disconnect`, { method: "POST", json: { delete_data: deleteData } }),
    onSuccess: () => { toast.success(deleteData ? "Disconnected and data deleted" : "Disconnected — history retained"); invalidate(); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={`Disconnect ${account.institution}?`}
      description="Stored credentials are deleted immediately and syncing stops. This affects every account on this connection.">
      <label className="flex items-start gap-3 rounded-xl border border-line p-3">
        <input type="checkbox" className="mt-1 size-4 accent-[var(--neg)]" checked={deleteData} onChange={(e) => setDeleteData(e.target.checked)} />
        <span><span className="block text-sm font-medium text-ink">Also delete imported history</span>
          <span className="text-[14.5px] text-muted">Removes transactions, balances and holdings from this connection. This cannot be undone. By default your history is kept.</span></span>
      </label>
      <div className="mt-5 flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button variant="danger" loading={go.isPending} onClick={() => go.mutate()}>Disconnect</Button></div>
    </Modal>
  );
}

// ---------------------------------------------------------------- Add account wizard
type Method = "api" | "openbanking" | "import" | "manual";
const INSTITUTIONS = [
  { slug: "interactive-brokers", name: "Interactive Brokers", kind: "Brokerage", methods: ["api", "import", "manual"] as Method[] },
  { slug: "groww", name: "Groww", kind: "Brokerage · India", methods: ["api", "import", "manual"] as Method[] },
  { slug: "revolut", name: "Revolut", kind: "Bank", methods: ["openbanking", "import", "manual"] as Method[] },
  { slug: "manual", name: "Other institution", kind: "Any bank, card or asset", methods: ["import", "manual"] as Method[] },
];
const METHOD_INFO: Record<Method, { title: string; desc: string; icon: React.ElementType }> = {
  api: { title: "Official API", desc: "Read-only token from the provider. Syncs automatically.", icon: KeyRound },
  openbanking: { title: "Open Banking", desc: "Authorized connection via a licensed provider.", icon: ShieldCheck },
  import: { title: "Statement import", desc: "Upload a CSV export. Preview before anything is saved.", icon: FileUp },
  manual: { title: "Manual account", desc: "Track a balance you update yourself.", icon: Pencil },
};
const CRED_LABELS: Record<string, { label: string; hint: string; secret?: boolean; optional?: boolean }> = {
  flex_token: { label: "Flex Web Service token", hint: "Client Portal → Reporting → Flex Queries → Flex Web Service", secret: true },
  query_id: { label: "Activity Flex Query ID", hint: "The numeric ID of your Activity Flex Query (XML format)" },
  access_token: { label: "Access token", hint: "Groww → Trading APIs → Generate API keys. Expires daily at 06:00 IST.", secret: true, optional: true },
  api_key: { label: "API key (optional)", hint: "With a TOTP secret, 1Finance can renew the daily token automatically.", secret: true, optional: true },
  totp_secret: { label: "TOTP secret (optional)", hint: "Stored encrypted; used only to mint read-only access tokens.", secret: true, optional: true },
};

function AddAccountWizard({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [step, setStep] = React.useState(1);
  const [inst, setInst] = React.useState<(typeof INSTITUTIONS)[number] | null>(null);
  const [method, setMethod] = React.useState<Method | null>(null);
  const [result, setResult] = React.useState<{ title: string; lines: string[] } | null>(null);
  const { data: connectors = [] } = useConnectors();
  React.useEffect(() => { if (!open) { setStep(1); setInst(null); setMethod(null); setResult(null); } }, [open]);
  const steps = ["Institution", "Method", "Authorize", "Confirm"];
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Add an account" className="max-w-xl"
      description={<span className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-accent-fg" />Read-only access. 1Finance never stores bank passwords or moves money.</span>}>
      <ol className="mb-6 flex items-center gap-2" aria-label="Progress">
        {steps.map((s, i) => (
          <li key={s} className="flex flex-1 items-center gap-2">
            <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-[13.5px] font-semibold",
              step > i + 1 ? "bg-accent text-accent-ink" : step === i + 1 ? "bg-accent-soft text-accent-fg ring-1 ring-accent" : "bg-bg-subtle text-faint")}
              aria-current={step === i + 1 ? "step" : undefined}>{step > i + 1 ? "✓" : i + 1}</span>
            <span className={cn("hidden text-[14.5px] sm:inline", step === i + 1 ? "font-medium text-ink" : "text-muted")}>{s}</span>
            {i < steps.length - 1 && <span className="h-px flex-1 bg-line" />}
          </li>
        ))}
      </ol>
      <AnimatePresence mode="wait">
        <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.18 }}>
          {step === 1 && (
            <div className="grid gap-2.5">
              {INSTITUTIONS.map((x) => (
                <button key={x.slug} onClick={() => { setInst(x); setStep(2); }}
                  className="flex items-center gap-3 hl rounded-2xl border border-line p-3.5 text-left hover:bg-accent-soft/40">
                  <InstitutionAvatar slug={x.slug} name={x.name} />
                  <span className="flex-1"><span className="block font-medium text-ink">{x.name}</span><span className="text-[15px] text-muted">{x.kind}</span></span>
                </button>
              ))}
            </div>
          )}
          {step === 2 && inst && (
            <div className="grid gap-2.5">
              {inst.methods.map((m) => {
                const I = METHOD_INFO[m].icon;
                const unavailable = m === "openbanking";
                return (
                  <button key={m} disabled={unavailable} onClick={() => { setMethod(m); setStep(3); }}
                    className="flex items-start gap-3 hl rounded-2xl border border-line p-3.5 text-left enabled:hover:bg-accent-soft/40 disabled:opacity-60">
                    <span className="grid size-9 place-items-center rounded-xl bg-bg-subtle text-ink-2"><I className="size-4" /></span>
                    <span className="flex-1">
                      <span className="flex items-center gap-2 font-medium text-ink">{METHOD_INFO[m].title}{unavailable && <Badge tone="outline">Not configured</Badge>}</span>
                      <span className="text-[15px] text-muted">{unavailable ? "Revolut Open Banking requires a regulated AISP or licensed aggregator. Use statement import instead." : METHOD_INFO[m].desc}</span>
                    </span>
                  </button>
                );
              })}
              {inst.slug === "groww" && <p className="rounded-xl bg-info-soft px-3 py-2 text-[14.5px] text-ink-2">Groww&apos;s Trade API covers stocks &amp; ETFs only. Mutual funds and FDs: <b>manual import available</b>.</p>}
              <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => setStep(1)}>← Back</Button>
            </div>
          )}
          {step === 3 && inst && method && (
            <AuthorizeStep inst={inst} method={method} connectors={connectors} onBack={() => setStep(2)}
              onDone={(r) => { setResult(r); setStep(4); }} />
          )}
          {step === 4 && result && (
            <div className="text-center">
              <div className="mx-auto grid size-14 place-items-center rounded-full bg-pos-soft text-pos"><CheckCircle2 className="size-7" /></div>
              <p className="mt-4 text-lg font-semibold text-ink">{result.title}</p>
              <ul className="mt-2 space-y-1 text-[15.5px] text-muted">{result.lines.map((l) => <li key={l}>{l}</li>)}</ul>
              <Button variant="primary" className="mt-6" onClick={() => onOpenChange(false)}>Done</Button>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </Modal>
  );
}

function AuthorizeStep({ inst, method, connectors, onBack, onDone }: {
  inst: (typeof INSTITUTIONS)[number]; method: Method; connectors: Connector[]; onBack: () => void; onDone: (r: { title: string; lines: string[] }) => void;
}) {
  const invalidate = useInvalidateAll();
  const real = connectors.find((c) => c.institution === inst.slug && !c.is_mock && c.auth_method === "api_token");
  const mock = connectors.find((c) => c.institution === inst.slug && c.is_mock);
  const [creds, setCreds] = React.useState<Record<string, string>>({});
  const [manual, setManual] = React.useState({ name: inst.slug === "manual" ? "" : `${inst.name} account`, account_type: ["interactive-brokers", "groww"].includes(inst.slug) ? "brokerage" : "checking", currency: "EUR", balance: "" });
  const connect = useMutation({
    mutationFn: (key: string) => api<{ sync: { status: string; stats: Record<string, unknown>; error: string | null } }>("/connections", { method: "POST", json: { connector: key, credentials: creds } }),
    onSuccess: (r) => {
      invalidate();
      if (r.sync.status !== "succeeded") { toast.warning("Connected, but the first sync failed", { description: r.sync.error ?? undefined }); }
      const s = r.sync.stats ?? {};
      onDone({ title: `${inst.name} connected`, lines: Object.entries(s).map(([k, v]) => `${k.replace("_", " ")}: ${typeof v === "object" ? (v as { new?: number }).new ?? 0 : v}`) });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const createManual = useMutation({
    mutationFn: () => api<{ id: number }>("/accounts/manual", { method: "POST", json: { ...manual, balance: manual.balance || "0" } }),
    onSuccess: () => { invalidate(); onDone({ title: "Manual account added", lines: [`${manual.name} · ${formatMoney(manual.balance || "0", manual.currency)}`, "Update its balance any time from Accounts."] }); },
    onError: (e: Error) => toast.error(e.message),
  });

  if (method === "api" && real) {
    const required = real.credential_fields.filter((f) => !CRED_LABELS[f]?.optional);
    const ok = required.every((f) => creds[f]?.trim()) && (inst.slug !== "groww" || creds.access_token || (creds.api_key && creds.totp_secret));
    return (
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); connect.mutate(real.key); }}>
        <p className="text-[15.5px] text-muted">{real.notes}</p>
        {real.credential_fields.map((f) => (
          <Field key={f} label={CRED_LABELS[f]?.label ?? f} hint={CRED_LABELS[f]?.hint} htmlFor={f}>
            <Input id={f} type={CRED_LABELS[f]?.secret ? "password" : "text"} autoComplete="off" spellCheck={false}
              value={creds[f] ?? ""} onChange={(e) => setCreds((c) => ({ ...c, [f]: e.target.value }))} />
          </Field>
        ))}
        <p className="flex items-start gap-2 text-[14.5px] text-muted"><ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-accent-fg" />Credentials are validated with a live read-only request, then encrypted (AES-256-GCM). They are never shown again or sent to your browser.</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>← Back</Button>
          <div className="flex gap-2">
            {mock && <Button type="button" onClick={() => connect.mutate(mock.key)} loading={connect.isPending && connect.variables === mock.key}>Use demo data</Button>}
            <Button type="submit" variant="primary" disabled={!ok} loading={connect.isPending && connect.variables === real.key}>Verify &amp; connect</Button>
          </div>
        </div>
      </form>
    );
  }
  if (method === "import") {
    return (
      <div className="space-y-4">
        <EmptyState icon={FileUp} title="Create the account, then import" description="Statement imports attach to an account so balances and duplicates can be checked. Create a manual account below, then use “Import statement” from its menu." />
        <ManualForm manual={manual} setManual={setManual} />
        <div className="flex justify-between"><Button variant="ghost" size="sm" onClick={onBack}>← Back</Button>
          <Button variant="primary" disabled={!manual.name} loading={createManual.isPending} onClick={() => createManual.mutate()}>Create account</Button></div>
      </div>
    );
  }
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); createManual.mutate(); }}>
      <ManualForm manual={manual} setManual={setManual} />
      <div className="flex justify-between"><Button type="button" variant="ghost" size="sm" onClick={onBack}>← Back</Button>
        <Button type="submit" variant="primary" disabled={!manual.name} loading={createManual.isPending}>Add account</Button></div>
    </form>
  );
}

function ManualForm({ manual, setManual }: { manual: { name: string; account_type: string; currency: string; balance: string }; setManual: React.Dispatch<React.SetStateAction<{ name: string; account_type: string; currency: string; balance: string }>> }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2"><Field label="Account name" htmlFor="mname"><Input id="mname" value={manual.name} onChange={(e) => setManual((m) => ({ ...m, name: e.target.value }))} /></Field></div>
      <Field label="Type" htmlFor="mtype"><NativeSelect id="mtype" value={manual.account_type} onChange={(e) => setManual((m) => ({ ...m, account_type: e.target.value }))}>
        {Object.entries(ACCOUNT_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</NativeSelect></Field>
      <Field label="Currency" htmlFor="mcur"><NativeSelect id="mcur" value={manual.currency} onChange={(e) => setManual((m) => ({ ...m, currency: e.target.value }))}>
        {CURRENCIES.map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
      <div className="sm:col-span-2"><Field label="Current balance" htmlFor="mbal" hint="For credit cards and loans enter the amount owed as a negative number.">
        <Input id="mbal" inputMode="decimal" value={manual.balance} placeholder="0.00" onChange={(e) => setManual((m) => ({ ...m, balance: e.target.value.replace(/[^\d.-]/g, "") }))} /></Field></div>
    </div>
  );
}

// ---------------------------------------------------------------- Statement import
interface Preview {
  batch_id: number; format: string; rows: number; skipped: number; errors: { row: number; error: string }[];
  dedup: Record<string, number>; currency_mismatch: string[];
  sample: { date: string; description: string; amount: string; currency: string; type: string; status: string }[];
}
function ImportDialog({ account, onClose }: { account: AccountItem; onClose: () => void }) {
  const [preview, setPreview] = React.useState<Preview | null>(null);
  const [busy, setBusy] = React.useState(false);
  const invalidate = useInvalidateAll();
  const upload = async (file: File) => {
    setBusy(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("account_id", String(account.id));
    try { setPreview(await api<Preview>("/imports/preview", { method: "POST", body: fd })); }
    catch (e) { toast.error((e as Error).message); }
    finally { setBusy(false); }
  };
  const commit = useMutation({
    mutationFn: () => api<{ stats: Record<string, number> }>(`/imports/${preview!.batch_id}/commit`, { method: "POST" }),
    onSuccess: (r) => { toast.success(`Imported ${r.stats.new} transactions`, { description: `${r.stats.duplicate} duplicates skipped · ${r.stats.possible_duplicate} flagged for review` }); invalidate(); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title="Import statement" className="max-w-2xl"
      description={`Into ${account.name} (${account.currency}). Supported: Revolut CSV export, or CSV with date, description, amount, currency.`}>
      {!preview ? (
        <label className={cn("flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-line px-6 py-12 text-center transition-colors hover:border-accent", busy && "opacity-60")}>
          <Upload className="size-6 text-muted" />
          <span className="mt-3 text-sm font-medium text-ink">{busy ? "Validating…" : "Choose a CSV file"}</span>
          <span className="mt-1 text-[14.5px] text-muted">Max 5 MB. Nothing is saved until you confirm the preview.</span>
          <input type="file" accept=".csv,text/csv" className="sr-only" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </label>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Valid rows">{preview.rows}</Stat>
            <Stat label="New">{preview.dedup.new}</Stat>
            <Stat label="Duplicates">{preview.dedup.duplicate}</Stat>
            <Stat label="To review">{preview.dedup.possible_duplicate}</Stat>
          </div>
          {preview.errors.length > 0 && (
            <div className="rounded-xl bg-warn-soft p-3 text-[15px] text-ink-2">
              <p className="font-medium">{preview.errors.length} row(s) could not be read and will not be imported:</p>
              <ul className="mt-1 list-disc pl-5">{preview.errors.slice(0, 5).map((e) => <li key={e.row}>Row {e.row}: {e.error}</li>)}</ul>
            </div>
          )}
          {preview.skipped > 0 && <p className="text-[14.5px] text-muted">{preview.skipped} declined/failed rows skipped.</p>}
          {preview.currency_mismatch.length > 0 && <p className="text-[14.5px] text-warn">Contains {preview.currency_mismatch.join(", ")} rows — original currencies will be preserved.</p>}
          <div className="max-h-64 overflow-auto rounded-xl border border-line">
            <table className="w-full text-[15px]">
              <thead className="sticky top-0 bg-bg-subtle text-left text-muted"><tr><th className="px-3 py-2 font-medium">Date</th><th className="px-3 py-2 font-medium">Description</th><th className="px-3 py-2 font-medium">Type</th><th className="px-3 py-2 text-right font-medium">Amount</th></tr></thead>
              <tbody className="divide-y divide-line">
                {preview.sample.map((s, i) => (
                  <tr key={i}><td className="px-3 py-2 text-muted">{formatDate(s.date, "d MMM yy")}</td><td className="max-w-56 truncate px-3 py-2">{s.description}{s.status === "pending" && <Badge tone="warn" className="ml-1">Pending</Badge>}</td>
                    <td className="px-3 py-2 capitalize text-muted">{s.type}</td><td className="px-3 py-2 text-right tabular">{formatMoney(s.amount, s.currency)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setPreview(null)}>Choose another file</Button>
            <Button variant="primary" disabled={!preview.dedup.new && !preview.dedup.possible_duplicate} loading={commit.isPending} onClick={() => commit.mutate()}>
              Import {preview.dedup.new + preview.dedup.possible_duplicate} transactions
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------- Manual assets & liabilities
function ManualAssets() {
  const currency = useCurrency();
  const { data, isLoading } = useQuery({
    queryKey: ["assets-liabilities", currency],
    queryFn: () => api<{ assets: { id: number; name: string; type: string; currency: string; value: string; value_base: string; valuation_date: string; is_estimate: boolean; notes: string | null }[];
      liabilities: { id: number; name: string; type: string; currency: string; outstanding: string; outstanding_base: string; as_of: string; interest_rate: string | null; payment_amount: string | null; next_payment_date: string | null }[] }>(`/assets-liabilities?currency=${currency}`),
  });
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState<{ kind: "asset" | "liability"; id: number; name: string } | null>(null);
  const [adding, setAdding] = React.useState<"asset" | "liability" | null>(null);
  return (
    <section id="manual" className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader title="Other assets" description="Manually valued: property, deposits, vehicles" action={<Button size="sm" onClick={() => setAdding("asset")}><Plus />Add</Button>} />
        <CardBody>
          {isLoading ? <Skeleton className="h-20" /> : !data?.assets.length ? <EmptyState title="No manual assets" /> : (
            <ul className="divide-y divide-line">
              {data.assets.map((a) => (
                <li key={a.id} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{a.name}</p>
                    <p className="text-[14.5px] text-muted">{a.type.replace("_", " ")} · valued {formatDate(a.valuation_date)}{a.notes ? ` · ${a.notes}` : ""}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-ink"><Money value={a.value} currency={a.currency} /></p>
                    {a.is_estimate && <Badge tone="outline">Estimate</Badge>}
                  </div>
                  <Button variant="ghost" size="icon-sm" aria-label={`Update value of ${a.name}`} onClick={() => setEditing({ kind: "asset", id: a.id, name: a.name })}><Pencil /></Button>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Liabilities" description="Loans and debts tracked manually" action={<Button size="sm" onClick={() => setAdding("liability")}><Plus />Add</Button>} />
        <CardBody>
          {isLoading ? <Skeleton className="h-20" /> : !data?.liabilities.length ? <EmptyState title="No liabilities" /> : (
            <ul className="divide-y divide-line">
              {data.liabilities.map((l) => (
                <li key={l.id} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{l.name}</p>
                    <p className="text-[14.5px] text-muted">{l.interest_rate ? `${Number(l.interest_rate)}% APR · ` : ""}{l.payment_amount ? `${formatMoney(l.payment_amount, l.currency)} / month · ` : ""}as of {formatDate(l.as_of)}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-ink"><Money value={l.outstanding} currency={l.currency} /></p>
                    {l.currency !== currency && <p className="text-[14px] text-muted">≈ <Money value={l.outstanding_base} currency={currency} /></p>}
                  </div>
                  <Button variant="ghost" size="icon-sm" aria-label={`Update balance of ${l.name}`} onClick={() => setEditing({ kind: "liability", id: l.id, name: l.name })}><Pencil /></Button>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
      {editing && <ValueDialog {...editing} onClose={() => { setEditing(null); qc.invalidateQueries(); }} />}
      {adding && <AddManualDialog kind={adding} onClose={() => { setAdding(null); qc.invalidateQueries(); }} />}
    </section>
  );
}

function ValueDialog({ kind, id, name, onClose }: { kind: "asset" | "liability"; id: number; name: string; onClose: () => void }) {
  const [v, setV] = React.useState("");
  const save = useMutation({
    mutationFn: () => api(kind === "asset" ? `/assets/${id}/valuations` : `/liabilities/${id}/balance`, { method: "POST", json: { value: v } }),
    onSuccess: () => { toast.success("Updated — previous values kept in history"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={`Update ${name}`} description="Records a new dated valuation; history is preserved.">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <Field label={kind === "asset" ? "Estimated value" : "Outstanding amount"} htmlFor="val"><Input id="val" inputMode="decimal" value={v} onChange={(e) => setV(e.target.value.replace(/[^\d.]/g, ""))} /></Field>
        <div className="flex justify-end gap-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!v} loading={save.isPending}>Save</Button></div>
      </form>
    </Modal>
  );
}

function AddManualDialog({ kind, onClose }: { kind: "asset" | "liability"; onClose: () => void }) {
  const [f, setF] = React.useState({ name: "", type: kind === "asset" ? "property" : "personal_loan", currency: "EUR", value: "", rate: "" });
  const save = useMutation({
    mutationFn: () => kind === "asset"
      ? api("/assets", { method: "POST", json: { name: f.name, asset_type: f.type, currency: f.currency, value: f.value || "0" } })
      : api("/liabilities", { method: "POST", json: { name: f.name, liability_type: f.type, currency: f.currency, outstanding: f.value || "0", interest_rate: f.rate || null } }),
    onSuccess: () => { toast.success("Added"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const types = kind === "asset" ? ["property", "fixed_deposit", "cash", "vehicle", "other"] : ["personal_loan", "education_loan", "home_loan", "credit_card", "other"];
  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={kind === "asset" ? "Add asset" : "Add liability"}>
      <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="sm:col-span-2"><Field label="Name" htmlFor="n"><Input id="n" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
        <Field label="Type" htmlFor="t"><NativeSelect id="t" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{types.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</NativeSelect></Field>
        <Field label="Currency" htmlFor="c"><NativeSelect id="c" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</NativeSelect></Field>
        <Field label={kind === "asset" ? "Estimated value" : "Outstanding principal"} htmlFor="v"><Input id="v" inputMode="decimal" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value.replace(/[^\d.]/g, "") })} /></Field>
        {kind === "liability" && <Field label="Interest rate (% APR)" htmlFor="r"><Input id="r" inputMode="decimal" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value.replace(/[^\d.]/g, "") })} /></Field>}
        <div className="flex justify-end gap-2 sm:col-span-2"><Button type="button" onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" disabled={!f.name} loading={save.isPending}>Add</Button></div>
      </form>
    </Modal>
  );
}
