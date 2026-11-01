"use client";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, qs, type AccountItem, type CategoryTree, type Connector, type HistoryPoint, type Holding, type Insight,
  type Me, type Paged, type SpendingCat, type Summary, type Txn } from "./api";
import type { MoneyStr } from "./format";
import { useUi } from "./store";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/auth/me"), staleTime: 5 * 60_000, retry: false });
}

/** Effective reporting currency: header override → saved preference → EUR. */
export function useCurrency(): string {
  const override = useUi((s) => s.currency);
  const { data } = useMe();
  return override ?? data?.preferences?.base_currency ?? "EUR";
}

export function useSummary() {
  const c = useCurrency();
  return useQuery({ queryKey: ["summary", c], queryFn: () => api<Summary>(`/dashboard/summary${qs({ currency: c })}`), placeholderData: keepPreviousData });
}
export function useHistory(range: string) {
  const c = useCurrency();
  return useQuery({
    queryKey: ["history", c, range],
    queryFn: () => api<{ currency: string; points: HistoryPoint[]; step_days: number; change: MoneyStr; change_pct: MoneyStr }>(`/dashboard/history${qs({ range, currency: c })}`),
    placeholderData: keepPreviousData,
  });
}
export function useSpending(period: "this_month" | "last_month" = "this_month") {
  const c = useCurrency();
  return useQuery({
    queryKey: ["spending", c, period],
    queryFn: () => api<{ currency: string; total: MoneyStr; period: [string, string]; categories: SpendingCat[] }>(`/dashboard/spending${qs({ currency: c, period })}`),
    placeholderData: keepPreviousData,
  });
}
export function useInsights() {
  const c = useCurrency();
  return useQuery({ queryKey: ["insights", c], queryFn: () => api<{ currency: string; items: Insight[] }>(`/insights${qs({ currency: c })}`) });
}
export function useTransactions(params: Record<string, unknown>) {
  const c = useCurrency();
  return useQuery({
    queryKey: ["transactions", c, params],
    queryFn: () => api<Paged<Txn>>(`/transactions${qs({ ...params, currency: c })}`),
    placeholderData: keepPreviousData,
  });
}
export function useTransaction(id: number | null) {
  const c = useCurrency();
  return useQuery({ queryKey: ["transaction", id, c], queryFn: () => api<Txn & { merchant_key: string }>(`/transactions/${id}${qs({ currency: c })}`), enabled: !!id });
}
export function useCategories() {
  return useQuery({ queryKey: ["categories"], queryFn: () => api<CategoryTree[]>("/categories"), staleTime: 10 * 60_000 });
}
export function useAccounts() {
  const c = useCurrency();
  return useQuery({
    queryKey: ["accounts", c],
    queryFn: () => api<{ currency: string; summary: Record<string, MoneyStr | number>; accounts: AccountItem[];
      connections: { id: number; institution: string; connector: string; status: string; last_successful_sync: string | null; last_error: string | null; is_demo: boolean }[] }>(`/accounts${qs({ currency: c })}`),
    placeholderData: keepPreviousData,
  });
}
export function useConnectors() {
  return useQuery({ queryKey: ["connectors"], queryFn: () => api<Connector[]>("/connectors"), staleTime: 60 * 60_000 });
}
export function useHoldings(scope: string) {
  const c = useCurrency();
  return useQuery({
    queryKey: ["holdings", c, scope],
    queryFn: () => api<{ currency: string; total: MoneyStr; items: Holding[]; allocation: Record<string, { label: string; value: MoneyStr; share: MoneyStr }[]> }>(`/investments/holdings${qs({ scope, currency: c })}`),
    placeholderData: keepPreviousData,
  });
}

export function useInvalidateAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" && q.queryKey[0] !== "connectors" });
}

export function useSyncAll() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: () => api<{ results: { connection_id: number; status: string }[] }>("/sync-all", { method: "POST" }),
    onSuccess: (r) => {
      const failed = r.results.filter((x) => x.status !== "succeeded").length;
      if (failed) toast.warning(`${failed} connection(s) could not be synchronized`, { description: "Open Accounts for details." });
      else toast.success("All accounts are up to date");
      invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
