"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, FileText, LineChart, Search, Tag, Wallet } from "lucide-react";
import { api, qs, type Txn } from "@/lib/api";
import { formatMoney, relativeDay } from "@/lib/format";
import { useUi } from "@/lib/store";
import { NAV } from "./nav";

interface SearchResult {
  accounts: { id: number; label: string; type: string }[];
  transactions: Txn[];
  categories: { id: number; label: string; slug: string }[];
  investments: { id: number; label: string; ticker: string }[];
  reports: { label: string }[];
}

export function CommandMenu({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const [q, setQ] = React.useState("");
  const [debounced, setDebounced] = React.useState("");
  const hidden = useUi((s) => s.privacy);
  React.useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 180); return () => clearTimeout(t); }, [q]);
  React.useEffect(() => { if (!open) setQ(""); }, [open]);
  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api<SearchResult>(`/search${qs({ q: debounced })}`),
    enabled: open && debounced.length >= 2,
  });
  const go = (href: string) => { onOpenChange(false); router.push(href); };
  const item = "flex cursor-default items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] text-ink-2 aria-selected:bg-bg-subtle aria-selected:text-ink [&_svg]:size-4 [&_svg]:text-muted";
  const group = "px-1.5 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-faint";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
        <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[calc(100vw-24px)] max-w-xl -translate-x-1/2 overflow-hidden rounded-3xl border border-line bg-card shadow-pop data-[state=open]:animate-fade-in">
          <Dialog.Title className="sr-only">Search</Dialog.Title>
          <Dialog.Description className="sr-only">Search transactions, merchants, accounts, investments, categories and reports</Dialog.Description>
          <Command shouldFilter={false} label="Global search">
            <div className="flex items-center gap-3 border-b border-line px-4">
              <Search className="size-4 text-muted" aria-hidden />
              <Command.Input value={q} onValueChange={setQ} autoFocus placeholder="Search transactions, merchants, accounts…"
                className="h-14 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-faint" />
              {isFetching && <span className="text-[11px] text-faint">Searching…</span>}
            </div>
            <Command.List className="max-h-[60vh] overflow-y-auto pb-2">
              {debounced.length < 2 && (
                <Command.Group heading="Go to" className={group}>
                  {NAV.map((n) => (
                    <Command.Item key={n.href} value={n.label} onSelect={() => go(n.href)} className={item}><n.icon />{n.label}</Command.Item>
                  ))}
                </Command.Group>
              )}
              {debounced.length >= 2 && data && (
                <>
                  {!data.accounts.length && !data.transactions.length && !data.categories.length && !data.investments.length && !data.reports.length && (
                    <p className="px-4 py-10 text-center text-[13px] text-muted">No results for “{debounced}”.</p>
                  )}
                  {data.accounts.length > 0 && (
                    <Command.Group heading="Accounts" className={group}>
                      {data.accounts.map((a) => <Command.Item key={a.id} value={`a${a.id}`} onSelect={() => go(`/accounts`)} className={item}><Wallet />{a.label}<span className="ml-auto text-[11px] capitalize text-faint">{a.type.replace("_", " ")}</span></Command.Item>)}
                    </Command.Group>
                  )}
                  {data.transactions.length > 0 && (
                    <Command.Group heading="Transactions" className={group}>
                      {data.transactions.map((t) => (
                        <Command.Item key={t.id} value={`t${t.id}`} onSelect={() => go(`/transactions?id=${t.id}`)} className={item}>
                          <ArrowLeftRight /><span className="min-w-0 flex-1 truncate">{t.merchant ?? t.description}</span>
                          <span className="text-[11px] text-faint">{relativeDay(t.date)}</span>
                          <span className="tabular w-24 text-right text-ink">{formatMoney(t.amount, t.currency, { hidden })}</span>
                        </Command.Item>
                      ))}
                    </Command.Group>
                  )}
                  {data.investments.length > 0 && (
                    <Command.Group heading="Investments" className={group}>
                      {data.investments.map((s) => <Command.Item key={s.id} value={`s${s.id}`} onSelect={() => go(`/investments`)} className={item}><LineChart />{s.label}<span className="ml-auto text-[11px] text-faint">{s.ticker}</span></Command.Item>)}
                    </Command.Group>
                  )}
                  {data.categories.length > 0 && (
                    <Command.Group heading="Categories" className={group}>
                      {data.categories.map((c) => <Command.Item key={c.id} value={`c${c.id}`} onSelect={() => go(`/transactions?category=${c.slug}`)} className={item}><Tag />{c.label}</Command.Item>)}
                    </Command.Group>
                  )}
                  {data.reports.length > 0 && (
                    <Command.Group heading="Reports" className={group}>
                      {data.reports.map((r) => <Command.Item key={r.label} value={r.label} onSelect={() => go(`/reports`)} className={item}><FileText />{r.label}</Command.Item>)}
                    </Command.Group>
                  )}
                </>
              )}
            </Command.List>
            <div className="flex items-center gap-4 border-t border-line px-4 py-2 text-[11px] text-faint">
              <span><kbd className="font-sans">↑↓</kbd> navigate</span><span><kbd className="font-sans">↵</kbd> open</span><span><kbd className="font-sans">esc</kbd> close</span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
