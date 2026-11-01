import { ArrowLeftRight, BarChart3, FileText, Flag, LayoutGrid, LineChart, PiggyBank, Settings, Wallet } from "lucide-react";

export const NAV = [
  { href: "/", label: "Overview", icon: LayoutGrid, mobile: true },
  { href: "/accounts", label: "Accounts", icon: Wallet, mobile: true },
  { href: "/transactions", label: "Transactions", icon: ArrowLeftRight, mobile: true },
  { href: "/investments", label: "Investments", icon: LineChart, mobile: true },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/budgets", label: "Budgets", icon: PiggyBank },
  { href: "/goals", label: "Goals", icon: Flag },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
