/**
 * Display-only formatting. Money arrives from the API as exact decimal strings computed server-side;
 * the client never sums or converts money. Number() is only used for chart geometry.
 */
import { format, formatDistanceToNowStrict, isToday, isYesterday, parseISO } from "date-fns";

export type MoneyStr = string | null | undefined;

const SYMBOL_LOCALE: Record<string, string> = { INR: "en-IN", EUR: "en-IE", USD: "en-US", GBP: "en-GB" };

function splitDecimal(v: string): { neg: boolean; int: string; frac: string } {
  const neg = v.startsWith("-");
  const [int, frac = ""] = (neg ? v.slice(1) : v).split(".");
  return { neg, int, frac };
}

/** Group digits without converting to float (keeps exactness for very large values). */
function groupInt(int: string, currency: string): string {
  if (currency === "INR") {
    // Indian grouping: 12,34,56,789
    const last3 = int.slice(-3);
    const rest = int.slice(0, -3);
    return rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + last3 : last3;
  }
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

const symbolCache: Record<string, string> = {};
export function currencySymbol(currency: string): string {
  if (!symbolCache[currency]) {
    try {
      const parts = new Intl.NumberFormat(SYMBOL_LOCALE[currency] ?? "en-IE", { style: "currency", currency }).formatToParts(0);
      symbolCache[currency] = parts.find((p) => p.type === "currency")?.value ?? currency;
    } catch {
      symbolCache[currency] = currency;
    }
  }
  return symbolCache[currency];
}

export function formatMoney(
  value: MoneyStr,
  currency: string,
  opts: { decimals?: number; signed?: boolean; compact?: boolean; hidden?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (opts.hidden) return `${currencySymbol(currency)}••••`;
  if (opts.compact) {
    const n = Number(value);
    const s = new Intl.NumberFormat(SYMBOL_LOCALE[currency] ?? "en-IE", {
      style: "currency", currency, notation: "compact", maximumFractionDigits: 1,
    }).format(Math.abs(n));
    return `${n < 0 ? "−" : opts.signed && n > 0 ? "+" : ""}${s}`;
  }
  const decimals = opts.decimals ?? 2;
  const { neg, int, frac } = splitDecimal(value);
  // value is already rounded server-side; pad/truncate for display only
  const f = decimals > 0 ? "." + (frac + "0".repeat(decimals)).slice(0, decimals) : "";
  const isZero = /^0*$/.test(int + frac);
  const sign = neg && !isZero ? "−" : opts.signed && !isZero ? "+" : "";
  return `${sign}${currencySymbol(currency)}${groupInt(int || "0", currency)}${f}`;
}

export function formatPct(value: MoneyStr, opts: { signed?: boolean; decimals?: number } = {}): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  const d = opts.decimals ?? (Math.abs(n) < 10 ? 2 : 1);
  const s = Math.abs(n).toFixed(d);
  return `${n < 0 ? "−" : opts.signed && n > 0 ? "+" : ""}${s}%`;
}

export function formatQty(value: MoneyStr): string {
  if (!value) return "—";
  const { int, frac } = splitDecimal(value);
  const f = frac.replace(/0+$/, "");
  return groupInt(int, "EUR") + (f ? "." + f : "");
}

export function toNum(v: MoneyStr): number {
  return v ? Number(v) : 0;
}

export function sign(v: MoneyStr): -1 | 0 | 1 {
  if (!v) return 0;
  const n = Number(v);
  return n > 0 ? 1 : n < 0 ? -1 : 0;
}

export function d(iso: string | Date): Date {
  return typeof iso === "string" ? parseISO(iso) : iso;
}

export function formatDate(iso: string | null | undefined, pattern = "d MMM yyyy"): string {
  if (!iso) return "—";
  return format(d(iso), pattern);
}

export function relativeDay(iso: string): string {
  const x = d(iso);
  if (isToday(x)) return "Today";
  if (isYesterday(x)) return "Yesterday";
  return format(x, "EEE, d MMM");
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = formatDistanceToNowStrict(d(iso), { addSuffix: true });
  return s === "0 seconds ago" ? "just now" : s;
}

export function greeting(now = new Date()): string {
  const h = now.getHours();
  if (h < 5) return "Good evening";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export const CURRENCIES = ["EUR", "INR", "USD", "GBP"] as const;
/** Currencies offered in the top-bar switcher for viewing every amount. */
export const DISPLAY_CURRENCIES = [
  { code: "EUR", name: "Euro" },
  { code: "USD", name: "US Dollar" },
  { code: "INR", name: "Indian Rupee" },
  { code: "GBP", name: "British Pound" },
] as const;
