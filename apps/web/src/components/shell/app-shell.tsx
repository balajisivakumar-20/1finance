"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronsLeft, Eye, EyeOff, LogOut, Monitor, Moon, MoreHorizontal, RefreshCw, Search, Settings, ShieldCheck, Sun } from "lucide-react";
import { motion } from "motion/react";
import { Wordmark, LogoMark } from "@/components/brand";
import { Badge, Button } from "@/components/ui/primitives";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuRadioGroup, MenuRadioItem, MenuSeparator, MenuTrigger, Tip } from "@/components/ui/overlay";
import { CommandMenu } from "./command-menu";
import { NAV, isActive } from "./nav";
import { api } from "@/lib/api";
import { CURRENCIES, ago } from "@/lib/format";
import { useCurrency, useMe, useSummary, useSyncAll } from "@/lib/hooks";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading, isError } = useMe();
  const router = useRouter();
  const [cmdOpen, setCmdOpen] = React.useState(false);

  React.useEffect(() => {
    if (isError) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  }, [isError, router]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (isLoading || !me) {
    return (
      <div className="grid min-h-dvh place-items-center" aria-busy="true">
        <LogoMark className="size-10 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh">
      <Sidebar />
      <SidebarSpacer>
        <Header onSearch={() => setCmdOpen(true)} />
        {me.demo_mode && <DemoBanner />}
        <main id="main" className="mx-auto w-full max-w-[1400px] px-4 pb-28 pt-5 sm:px-6 lg:px-8 lg:pb-12">{children}</main>
      </SidebarSpacer>
      <BottomNav />
      <CommandMenu open={cmdOpen} onOpenChange={setCmdOpen} />
    </div>
  );
}

function SidebarSpacer({ children }: { children: React.ReactNode }) {
  const collapsed = useUi((s) => s.sidebarCollapsed);
  return <div className={cn("transition-[padding] duration-300", collapsed ? "lg:pl-[76px]" : "lg:pl-[248px]")}>{children}</div>;
}

function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed: collapsed, toggleSidebar } = useUi();
  return (
    <aside aria-label="Primary"
      className={cn("fixed inset-y-0 left-0 z-30 hidden flex-col border-r border-line bg-card/70 backdrop-blur-xl transition-[width] duration-300 lg:flex",
        collapsed ? "w-[76px]" : "w-[248px]")}>
      <div className={cn("flex h-16 items-center", collapsed ? "justify-center" : "px-5")}>
        <Link href="/" aria-label="1Finance home">{collapsed ? <LogoMark /> : <Wordmark />}</Link>
      </div>
      <nav className="flex-1 space-y-0.5 px-3 py-3">
        {NAV.map((item) => {
          const active = isActive(pathname, item.href);
          const link = (
            <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}
              className={cn("group relative flex h-10 items-center gap-3 rounded-xl text-[14px] font-medium transition-colors",
                collapsed ? "justify-center" : "px-3",
                active ? "text-ink" : "text-muted hover:bg-bg-subtle hover:text-ink")}>
              {active && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl bg-bg-subtle" transition={{ type: "spring", bounce: 0.15, duration: 0.4 }} />}
              <item.icon className={cn("relative size-[18px]", active && "text-accent")} aria-hidden />
              {!collapsed && <span className="relative">{item.label}</span>}
            </Link>
          );
          return collapsed ? <Tip key={item.href} content={item.label}>{link}</Tip> : link;
        })}
      </nav>
      <div className="space-y-2 p-3">
        {!collapsed && (
          <div className="flex items-start gap-2 rounded-2xl bg-bg-subtle px-3 py-3 text-[12px] text-muted">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
            <span>Read-only connections. 1Finance can never move money.</span>
          </div>
        )}
        <button onClick={toggleSidebar} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn("flex h-9 w-full items-center gap-2 rounded-xl text-[13px] text-muted hover:bg-bg-subtle hover:text-ink", collapsed ? "justify-center" : "px-3")}>
          <ChevronsLeft className={cn("size-4 transition-transform", collapsed && "rotate-180")} aria-hidden />
          {!collapsed && "Collapse"}
        </button>
      </div>
    </aside>
  );
}

function Header({ onSearch }: { onSearch: () => void }) {
  const { data: summary } = useSummary();
  const sync = useSyncAll();
  const { privacy, togglePrivacy } = useUi();
  const [isMac, setIsMac] = React.useState(true);
  React.useEffect(() => setIsMac(/Mac|iPhone|iPad/.test(navigator.platform)), []);
  return (
    <header className="sticky top-0 z-20 border-b border-line/70 bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-2 px-4 sm:h-16 sm:px-6 lg:px-8">
        <Link href="/" className="lg:hidden" aria-label="1Finance home"><LogoMark className="size-7" /></Link>
        <button onClick={onSearch}
          aria-label="Search"
          className="ml-1 flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-xl border border-line bg-card text-[13px] text-faint transition-colors hover:border-line-strong sm:w-auto sm:min-w-0 sm:flex-1 sm:justify-start sm:px-3 sm:max-w-sm lg:ml-0">
          <Search className="size-4 shrink-0" aria-hidden />
          <span className="hidden truncate sm:inline">Search transactions, accounts…</span>
          <kbd className="ml-auto hidden rounded-md border border-line bg-bg-subtle px-1.5 py-0.5 font-sans text-[11px] text-muted sm:inline">{isMac ? "⌘" : "Ctrl"} K</kbd>
        </button>
        <div className="ml-auto flex min-w-0 items-center gap-0.5 sm:gap-1">
          <span className="mr-2 hidden text-[12px] text-muted xl:inline" title={summary?.last_sync ?? undefined}>
            {summary?.last_sync ? `Synced ${ago(summary.last_sync)}` : "Not synced yet"}
          </span>
          <Tip content="Refresh all accounts">
            <Button variant="ghost" size="icon" onClick={() => sync.mutate()} aria-label="Refresh all accounts" disabled={sync.isPending}>
              <RefreshCw className={cn(sync.isPending && "animate-spin")} />
            </Button>
          </Tip>
          <Tip content={privacy ? "Show balances" : "Hide balances"}>
            <Button variant="ghost" size="icon" onClick={togglePrivacy} aria-label={privacy ? "Show balances" : "Hide balances"} aria-pressed={privacy}>
              {privacy ? <EyeOff /> : <Eye />}
            </Button>
          </Tip>
          <CurrencyMenu />
          <span className="hidden sm:inline-flex"><ThemeMenu /></span>
          <Notifications />
          <ProfileMenu />
        </div>
      </div>
    </header>
  );
}

function CurrencyMenu() {
  const c = useCurrency();
  const setCurrency = useUi((s) => s.setCurrency);
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size="sm" className="h-9 px-2.5 font-semibold tabular" aria-label={`Reporting currency ${c}`}>{c}</Button>
      </MenuTrigger>
      <MenuContent>
        <MenuLabel>Reporting currency</MenuLabel>
        <MenuRadioGroup value={c} onValueChange={(v) => setCurrency(v)}>
          {CURRENCIES.map((x) => <MenuRadioItem key={x} value={x}>{x}</MenuRadioItem>)}
        </MenuRadioGroup>
        <MenuSeparator />
        <p className="px-2.5 pb-1.5 pt-1 text-[11px] leading-snug text-faint">Original currencies are always preserved; conversions use stored exchange rates.</p>
      </MenuContent>
    </Menu>
  );
}

export function ThemeMenu() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  const Icon = !mounted ? Monitor : theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <Menu>
      <MenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Theme"><Icon /></Button></MenuTrigger>
      <MenuContent>
        <MenuLabel>Appearance</MenuLabel>
        <MenuRadioGroup value={theme} onValueChange={setTheme}>
          <MenuRadioItem value="light"><span className="flex items-center gap-2"><Sun className="size-4" />Light</span></MenuRadioItem>
          <MenuRadioItem value="dark"><span className="flex items-center gap-2"><Moon className="size-4" />Dark</span></MenuRadioItem>
          <MenuRadioItem value="system"><span className="flex items-center gap-2"><Monitor className="size-4" />System</span></MenuRadioItem>
        </MenuRadioGroup>
      </MenuContent>
    </Menu>
  );
}

function Notifications() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ id: number; kind: string; title: string; body: string | null; read: boolean; created_at: string }[]>("/notifications"),
    refetchInterval: 120_000,
  });
  const unread = data.filter((n) => !n.read).length;
  return (
    <Menu onOpenChange={(o) => { if (!o && unread) api("/notifications/read-all", { method: "POST" }).then(() => qc.invalidateQueries({ queryKey: ["notifications"] })); }}>
      <MenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} className="relative">
          <Bell />
          {unread > 0 && <span className="absolute right-2 top-2 size-2 rounded-full bg-accent ring-2 ring-bg" aria-hidden />}
        </Button>
      </MenuTrigger>
      <MenuContent className="w-80 p-0">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold">Notifications</div>
        <div className="max-h-96 overflow-y-auto p-1.5">
          {data.length === 0 && <p className="px-3 py-6 text-center text-[13px] text-muted">You&apos;re all caught up.</p>}
          {data.map((n) => (
            <div key={n.id} className="rounded-xl px-3 py-2.5 hover:bg-bg-subtle">
              <div className="flex items-center gap-2">
                {!n.read && <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-label="Unread" />}
                <p className="text-[13px] font-medium text-ink">{n.title}</p>
              </div>
              {n.body && <p className="mt-0.5 text-[12px] text-muted">{n.body}</p>}
              <p className="mt-1 text-[11px] text-faint">{ago(n.created_at)}</p>
            </div>
          ))}
        </div>
      </MenuContent>
    </Menu>
  );
}

function ProfileMenu() {
  const { data: me } = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const initials = (me?.display_name ?? "?").split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.clear();
    router.replace("/login");
  };
  return (
    <Menu>
      <MenuTrigger asChild>
        <button className="ml-1 grid size-9 place-items-center rounded-full bg-accent-soft text-[13px] font-semibold text-accent ring-offset-2 ring-offset-bg hover:ring-2 hover:ring-line" aria-label="Profile menu">
          {initials}
        </button>
      </MenuTrigger>
      <MenuContent className="w-60">
        <div className="px-2.5 py-2">
          <p className="text-[13px] font-semibold text-ink">{me?.display_name}</p>
          <p className="truncate text-[12px] text-muted">{me?.email}</p>
        </div>
        <MenuSeparator />
        <MenuItem onSelect={() => router.push("/settings")}><Settings />Settings</MenuItem>
        <MenuItem onSelect={() => router.push("/settings#security")}><ShieldCheck />Security</MenuItem>
        <MenuSeparator />
        <MenuItem onSelect={logout}><LogOut />Sign out</MenuItem>
      </MenuContent>
    </Menu>
  );
}

function DemoBanner() {
  return (
    <div className="mx-auto max-w-[1400px] px-4 pt-4 sm:px-6 lg:px-8">
      <div className="flex items-center gap-3 rounded-2xl border border-dashed border-warn/40 bg-warn-soft px-4 py-2.5 text-[13px] text-ink-2">
        <Badge tone="warn">Demo data</Badge>
        <span className="min-w-0 truncate">You&apos;re viewing generated demonstration data — nothing here is real financial information.</span>
        <Link href="/accounts?add=1" className="ml-auto hidden shrink-0 font-medium text-accent hover:underline sm:inline">Connect a real account</Link>
      </div>
    </div>
  );
}

function BottomNav() {
  const pathname = usePathname();
  const router = useRouter();
  const more = NAV.filter((n) => !("mobile" in n && n.mobile));
  const moreActive = more.some((n) => isActive(pathname, n.href));
  return (
    <nav aria-label="Primary" className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-card/90 backdrop-blur-xl pb-safe lg:hidden">
      <div className="mx-auto grid h-16 max-w-lg grid-cols-5">
        {NAV.filter((n) => "mobile" in n && n.mobile).map((n) => {
          const active = isActive(pathname, n.href);
          return (
            <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
              className={cn("flex flex-col items-center justify-center gap-1 text-[10.5px] font-medium", active ? "text-accent" : "text-muted")}>
              <n.icon className="size-5" aria-hidden />{n.label}
            </Link>
          );
        })}
        <Menu>
          <MenuTrigger className={cn("flex flex-col items-center justify-center gap-1 text-[10.5px] font-medium", moreActive ? "text-accent" : "text-muted")} aria-label="More sections">
            <MoreHorizontal className="size-5" aria-hidden />More
          </MenuTrigger>
          <MenuContent side="top" className="mb-2 w-56">
            {more.map((n) => <MenuItem key={n.href} onSelect={() => router.push(n.href)}><n.icon />{n.label}</MenuItem>)}
            <MenuSeparator />
            <div className="flex items-center justify-between px-2.5 py-1 text-[13px] text-ink-2">Theme <ThemeMenu /></div>
          </MenuContent>
        </Menu>
      </div>
    </nav>
  );
}
