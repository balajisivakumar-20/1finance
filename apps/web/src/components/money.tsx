"use client";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { formatMoney, formatPct, sign, type MoneyStr } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

export function Money({ value, currency, className, signed, compact, decimals, colored }: {
  value: MoneyStr; currency: string; className?: string; signed?: boolean; compact?: boolean; decimals?: number; colored?: boolean;
}) {
  const hidden = useUi((s) => s.privacy);
  const s = sign(value);
  return (
    <span className={cn("tabular", colored && (s > 0 ? "text-pos" : s < 0 ? "text-ink" : ""), className)}>
      {formatMoney(value, currency, { signed, compact, decimals, hidden })}
    </span>
  );
}

/** Gain/loss indicator — never colour alone: icon + sign + text. `invert` for liabilities/expenses where down is good. */
export function Change({ pct, amount, currency, invert, className, label }: {
  pct?: MoneyStr; amount?: MoneyStr; currency?: string; invert?: boolean; className?: string; label?: string;
}) {
  const hidden = useUi((s) => s.privacy);
  const s = sign(pct ?? amount);
  const good = invert ? s < 0 : s > 0;
  const Icon = s > 0 ? ArrowUpRight : s < 0 ? ArrowDownRight : Minus;
  const tone = s === 0 ? "bg-bg-subtle text-muted" : good ? "bg-pos-soft text-pos" : "bg-neg-soft text-neg";
  const words = s === 0 ? "No change" : s > 0 ? "Up" : "Down";
  if (pct == null && amount == null) return null;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium tabular", tone, className)}
      aria-label={`${words}${pct != null ? ` ${formatPct(pct)}` : ""}${label ? ` ${label}` : ""}`}>
      <Icon className="size-3.5" aria-hidden />
      {amount != null && currency && !hidden && <span>{formatMoney(amount, currency, { signed: true })}</span>}
      {pct != null && <span className={cn(amount != null && currency && !hidden && "opacity-80")}>{amount != null && currency && !hidden ? `(${formatPct(pct, { signed: true })})` : formatPct(pct, { signed: true })}</span>}
    </span>
  );
}
