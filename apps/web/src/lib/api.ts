/** Typed API client. Same-origin (proxied by Next) → session cookie is first-party & HttpOnly. */
import type { MoneyStr } from "./format";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

function csrf(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|; )(?:__Host-)?1f_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.json !== undefined) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrf());
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { /* ignore */ }
    const detail = (body as { detail?: unknown })?.detail;
    const msg = typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, msg, body);
  }
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("json") ? res.json() : res.blob()) as Promise<T>;
}

export function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---------------- types (mirror the FastAPI responses; see /api/openapi.json) ----------------
export interface Me {
  id: number; email: string; display_name: string; mfa_enabled: boolean; demo_mode: boolean;
  preferences: { base_currency: string; timezone: string; theme: string; number_format: string; date_format: string;
    ai_categorization_consent: boolean } | null;
}
export interface Change { value: MoneyStr; change?: MoneyStr; change_pct?: MoneyStr; previous?: MoneyStr }
export interface AccountItem {
  id: number; name: string; official_name: string; nickname: string | null; institution: string; institution_slug: string;
  connector: string; account_type: string; currency: string; masked_reference: string | null; balance: MoneyStr;
  cash_balance: MoneyStr; investments_value_local: MoneyStr; balance_base: MoneyStr; base_currency: string;
  valuation_timestamp: string | null; last_sync: string | null; connection_status: string; connection_id: number | null;
  is_stale: boolean; is_demo: boolean; status: string; counts_toward_net_worth: boolean;
}
export interface Summary {
  currency: string; as_of: string;
  net_worth: Change & { comparison: string };
  assets: Change; liabilities: Change;
  income_month: Change & { previous_same_period: MoneyStr; period: [string, string]; last_month_total: MoneyStr };
  expenses_month: Change & { previous_same_period: MoneyStr; period: [string, string]; pending_excluded: number; last_month_total: MoneyStr };
  allocation: { key: string; label: string; value: MoneyStr; share: MoneyStr }[];
  accounts: AccountItem[];
  last_sync: string | null;
  data_quality: { includes_demo: boolean; includes_estimates: boolean; missing_rates: string[]; stale_accounts: number[]; price_types: string[] };
  fx: { provider: string; as_of: string } | null;
}
export interface HistoryPoint { date: string; net_worth: MoneyStr; assets: MoneyStr; liabilities: MoneyStr }
export interface Category { id: number; slug: string; name: string; color: string | null; icon: string | null }
export interface CategoryTree extends Category { type: string; custom: boolean; children: (Category & { custom: boolean })[] }
export interface Txn {
  id: number; date: string; posting_date: string | null; description: string; merchant: string | null; amount: MoneyStr;
  currency: string; amount_base: MoneyStr; base_currency: string; type: string; system_type: string;
  category: Category | null; category_source: string | null; status: string;
  account: { id: number; name: string; institution: string } | null; notes: string | null; tags: string[]; source: string;
  external_reference: string | null; duplicate_status: string; transfer_group: string | null; is_demo: boolean;
  fx?: { rate: string; provider: string; effective_at: string | null; derived: boolean } | null;
}
export interface Paged<T> { total: number; page: number; page_size: number; currency: string; items: T[] }
export interface SpendingCat { slug: string; name: string; amount: MoneyStr; color: string | null; icon: string | null; share: MoneyStr }
export interface Insight {
  id: string; kind: "positive" | "attention" | "info"; title: string; body: string; unit?: "money" | "percent";
  values?: Record<string, MoneyStr>; period?: Record<string, [string, string]>;
}
export interface Holding {
  security_id: number; account_id: number; name: string; ticker: string; isin: string | null; asset_class: string;
  exchange: string | null; country: string | null; sector: string | null; brokerage: string; quantity: MoneyStr;
  average_price: MoneyStr; current_price: MoneyStr; market_value: MoneyStr; cost_basis: MoneyStr; unrealized: MoneyStr;
  unrealized_pct: MoneyStr; currency: string; market_value_base: MoneyStr; allocation_pct: MoneyStr; price_type: string;
  valuation_timestamp: string; is_stale: boolean; is_demo: boolean;
}
export interface Connector {
  key: string; institution: string; display_name: string; auth_method: string; capabilities: string[]; is_mock: boolean;
  credential_fields: string[]; notes: string;
}
