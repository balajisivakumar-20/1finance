import { ArrowLeftRight, BarChart3, FileText, Flag, LayoutGrid, LineChart, PiggyBank, Settings, Wallet } from "lucide-react";

export const NAV = [
  { href: "/", label: "Overview", icon: LayoutGrid, mobile: true, section: "Today", blurb: "Your complete financial picture" },
  { href: "/accounts", label: "Accounts", icon: Wallet, mobile: true, section: "Today", blurb: "Banks, cards, brokers and manual assets" },
  { href: "/transactions", label: "Transactions", icon: ArrowLeftRight, mobile: true, section: "Today", blurb: "Every movement, categorised" },
  { href: "/investments", label: "Investments", icon: LineChart, mobile: true, section: "Wealth", blurb: "Holdings, allocation and returns" },
  { href: "/analytics", label: "Analytics", icon: BarChart3, section: "Wealth", blurb: "Cash flow, categories and trends" },
  { href: "/budgets", label: "Budgets", icon: PiggyBank, section: "Plan", blurb: "Monthly spending limits" },
  { href: "/goals", label: "Goals", icon: Flag, section: "Plan", blurb: "Save with purpose" },
  { href: "/reports", label: "Reports", icon: FileText, section: "Plan", blurb: "Statements and exports" },
  { href: "/settings", label: "Settings", icon: Settings, section: "Account", blurb: "Preferences, security and data" },
] as const;

export type NavItem = (typeof NAV)[number];
export const SECTIONS = ["Today", "Wealth", "Plan"] as const;

export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function currentNav(pathname: string): NavItem | undefined {
  return NAV.find((n) => isActive(pathname, n.href));
}
