"use client";
import * as React from "react";
import { toast } from "sonner";
import { BarChart3, FileSpreadsheet, FileText, LineChart, ListOrdered, PieChart, Receipt, ScrollText, Wallet } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button, Card, Field, Input } from "@/components/ui/primitives";
import { qs } from "@/lib/api";
import { useCurrency } from "@/lib/hooks";
import { downloadBlob } from "@/lib/utils";

const REPORTS = [
  { kind: "monthly", title: "Monthly financial summary", desc: "Last full month: income, expenses, savings, net worth and allocation.", icon: ScrollText },
  { kind: "annual", title: "Annual financial summary", desc: "Year to date with monthly cash flow and category breakdown.", icon: BarChart3 },
  { kind: "income-expense", title: "Income & expense report", desc: "Month-by-month income, expenses and net cash flow.", icon: Receipt },
  { kind: "categories", title: "Spending category report", desc: "Where your money went, grouped by category.", icon: PieChart },
  { kind: "holdings", title: "Investment holdings", desc: "All positions with quantities, prices and valuations.", icon: LineChart },
  { kind: "net-worth", title: "Net worth report", desc: "Assets, liabilities and weekly net worth history.", icon: Wallet },
  { kind: "allocation", title: "Asset allocation", desc: "Current distribution of your assets.", icon: PieChart },
  { kind: "transactions", title: "Transaction statement", desc: "Every transaction in the period with original and converted amounts.", icon: ListOrdered },
];

export default function ReportsPage() {
  const currency = useCurrency();
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const download = async (kind: string, format: "pdf" | "csv" | "xlsx") => {
    setBusy(`${kind}-${format}`);
    try {
      const res = await fetch(`/api/v1/reports/${kind}${qs({ format, currency, date_from: from && to ? from : undefined, date_to: from && to ? to : undefined })}`, { credentials: "same-origin" });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? "Export failed");
      const name = res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] ?? `1finance-${kind}.${format}`;
      downloadBlob(await res.blob(), name);
      toast.success("Report downloaded");
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(null); }
  };
  return (
    <div className="space-y-5">
      <PageHeader title="Reports" subtitle={`Export professional reports in ${currency}. Estimated, delayed or demo data is always labeled.`} />
      <Card className="flex flex-wrap items-end gap-4 p-5">
        <div className="w-44"><Field label="From (optional)" htmlFor="rf"><Input id="rf" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field></div>
        <div className="w-44"><Field label="To (optional)" htmlFor="rt"><Input id="rt" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field></div>
        <p className="pb-2 text-[12.5px] text-muted">Leave empty to use each report&apos;s default period.</p>
      </Card>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {REPORTS.map((r) => (
          <Card key={r.kind} className="flex flex-col p-5">
            <div className="flex items-start gap-3">
              <span className="grid size-10 place-items-center rounded-2xl bg-accent-soft text-accent"><r.icon className="size-5" /></span>
              <div><p className="font-semibold text-ink">{r.title}</p><p className="mt-0.5 text-[12.5px] text-muted">{r.desc}</p></div>
            </div>
            <div className="mt-5 flex gap-2 pt-1">
              <Button size="sm" variant="primary" loading={busy === `${r.kind}-pdf`} onClick={() => download(r.kind, "pdf")}><FileText />PDF</Button>
              <Button size="sm" loading={busy === `${r.kind}-xlsx`} onClick={() => download(r.kind, "xlsx")}><FileSpreadsheet />Excel</Button>
              <Button size="sm" loading={busy === `${r.kind}-csv`} onClick={() => download(r.kind, "csv")}>CSV</Button>
            </div>
          </Card>
        ))}
      </div>
      <p className="text-[12px] text-faint">Exports never include API tokens, credentials or full account numbers. Each export is recorded in your security activity.</p>
    </div>
  );
}
