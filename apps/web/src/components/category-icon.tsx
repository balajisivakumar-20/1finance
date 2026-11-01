import { ArrowLeftRight, CircleDashed, HeartPulse, Home, Landmark, Plane, Plug, Repeat, ShoppingBag, Tag, Ticket, TrainFront, Utensils, Wallet,
  Building2, LineChart, PiggyBank, CreditCard, Banknote } from "lucide-react";
import { cn } from "@/lib/utils";

const ICONS: Record<string, React.ElementType> = {
  home: Home, utensils: Utensils, "train-front": TrainFront, "shopping-bag": ShoppingBag, plug: Plug, repeat: Repeat,
  "heart-pulse": HeartPulse, ticket: Ticket, plane: Plane, landmark: Landmark, "circle-dashed": CircleDashed, wallet: Wallet,
  "arrow-left-right": ArrowLeftRight, tag: Tag,
};

export function CategoryIcon({ icon, color, className, size = "md" }: { icon?: string | null; color?: string | null; className?: string; size?: "sm" | "md" }) {
  const Icon = (icon && ICONS[icon]) || Tag;
  return (
    <span className={cn("grid shrink-0 place-items-center rounded-xl", size === "sm" ? "size-8" : "size-9", className)}
      style={{ background: `color-mix(in srgb, ${color ?? "var(--muted)"} 13%, transparent)`, color: color ?? "var(--muted)" }} aria-hidden>
      <Icon className="size-4" />
    </span>
  );
}

const ACCOUNT_ICONS: Record<string, React.ElementType> = {
  checking: Wallet, savings: PiggyBank, brokerage: LineChart, investment: LineChart, cash: Banknote, credit_card: CreditCard,
  loan: Landmark, fixed_deposit: Building2, other: Wallet,
};
const INST_COLORS: Record<string, string> = { revolut: "#2563EB", "interactive-brokers": "#B91C1C", groww: "#0D9488", manual: "#64748B" };

export function InstitutionAvatar({ slug, name, type, className }: { slug: string; name: string; type?: string; className?: string }) {
  const color = INST_COLORS[slug] ?? "#475569";
  const Icon = type ? ACCOUNT_ICONS[type] : null;
  return (
    <span className={cn("relative grid size-10 shrink-0 place-items-center rounded-2xl text-[13px] font-semibold", className)}
      style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color }} aria-hidden>
      {name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
      {Icon && <span className="absolute -bottom-1 -right-1 grid size-5 place-items-center rounded-full border-2 border-card bg-card text-muted"><Icon className="size-3" /></span>}
    </span>
  );
}

export const ACCOUNT_TYPE_LABEL: Record<string, string> = {
  checking: "Current account", savings: "Savings", brokerage: "Brokerage", investment: "Investment", cash: "Cash",
  credit_card: "Credit card", loan: "Loan", fixed_deposit: "Fixed deposit", other: "Other",
};
