import { AlertCircle, CheckCircle2, Clock, Loader2, PlugZap, Unplug } from "lucide-react";
import { Badge } from "@/components/ui/primitives";
import { ago } from "@/lib/format";

export function ConnectionStatus({ status, lastSync, stale }: { status: string; lastSync?: string | null; stale?: boolean }) {
  if (status === "reauth_required") return <Badge tone="warn"><PlugZap />Reconnection required</Badge>;
  if (status === "error") return <Badge tone="neg"><AlertCircle />Sync failed</Badge>;
  if (status === "syncing") return <Badge tone="info"><Loader2 className="animate-spin" />Syncing</Badge>;
  if (status === "disconnected") return <Badge tone="outline"><Unplug />Disconnected</Badge>;
  if (status === "manual") return <Badge tone="outline">Manual</Badge>;
  if (stale) return <Badge tone="warn"><Clock />Stale · {ago(lastSync)}</Badge>;
  return <Badge tone="pos"><CheckCircle2 />Updated {ago(lastSync)}</Badge>;
}

export function PriceTypeBadge({ type }: { type: string }) {
  const map: Record<string, [string, "pos" | "info" | "neutral" | "warn"]> = {
    live: ["Live", "pos"], delayed: ["Delayed", "info"], close: ["Last close", "neutral"], imported: ["Imported price", "warn"],
  };
  const [label, tone] = map[type] ?? [type, "neutral"];
  return <Badge tone={tone}>{label}</Badge>;
}
