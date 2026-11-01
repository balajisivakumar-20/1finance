"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronsUpDown, Eye, EyeOff, LogOut, Monitor, Moon, MoreHorizontal, PanelLeft, RefreshCw, Search, Settings, ShieldCheck, Sun } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { LogoMark } from "@/components/brand";
import { Badge, Button } from "@/components/ui/primitives";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuRadioGroup, MenuRadioItem, MenuSeparator, MenuTrigger, Tip } from "@/components/ui/overlay";
import { CommandMenu } from "./command-menu";
import { NAV, SECTIONS, currentNav, isActive, type NavItem } from "./nav";
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
        <main id="main" className="mx-auto w-full max-w-[1400px] px-4 pb-32 pt-5 sm:px-6 lg:px-8 lg:pb-12">{children}</main>
      </SidebarSpacer>
      <BottomNav />
      <CommandMenu open={cmdOpen} onOpenChange={setCmdOpen} />
    </div>
  );
}

const SPRING = { type: "spring", bounce: 0.18, duration: 0.45 } as const;

function SidebarSpacer({ children }: { children: React.ReactNode }) {
  const collapsed = useUi((s) => s.sidebarCollapsed);
  return <div className={cn("transition-[padding] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]", collapsed ? "lg:pl-[108px]" : "lg:pl-[288px]")}>{children}</div>;
}

function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed: collapsed, toggleSidebar } = useUi();
  const settings = NAV.find((n) => n.href === "/settings")!;
  return (
    <aside aria-label="Primary"
      className={cn("sidebar-surface fixed bottom-3 left-3 top-3 z-30 hidden flex-col overflow-hidden rounded-[30px] lg:flex",
        "transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]", collapsed ? "w-[84px]" : "w-[264px]")}>
      <div className={cn("flex shrink-0 items-center gap-3 pt-5", collapsed ? "flex-col px-3" : "px-5")}>
        <Link href="/" aria-label="1Finance home" className="shrink-0 rounded-2xl bg-card/80 p-1 shadow-[0_2px_10px_-4px_rgba(31,22,0,0.25)] ring-1 ring-white/60 dark:ring-white/5">
          <LogoMark className="size-9" />
        </Link>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div key="brand" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -6 }} transition={{ duration: 0.2 }} className="min-w-0 flex-1">
              <p className="truncate text-[17.5px] font-semibold leading-tight tracking-tight text-ink">1Finance</p>
              <p className="truncate text-[11.5px] text-muted">Personal finance</p>
            </motion.div>
          )}
        </AnimatePresence>
        <Tip content={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <button onClick={toggleSidebar} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}
            className="grid size-9 shrink-0 place-items-center rounded-xl text-muted transition-colors hover:bg-card/70 hover:text-ink">
            <PanelLeft className="size-[18px]" aria-hidden />
          </button>
        </Tip>
      </div>
      {collapsed && <div className="mx-6 mt-3 h-px bg-ink/10" aria-hidden />}

      <nav className={cn("flex-1 overflow-y-auto overflow-x-hidden pb-3", collapsed ? "px-3 pt-3" : "px-4 pt-4")}>
        {SECTIONS.map((section) => (
          <div key={section} className={cn(collapsed ? "space-y-1.5 pb-3" : "pb-4")}>
            {!collapsed && <p className="px-3 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-faint">{section}</p>}
            <div className="space-y-1">
              {NAV.filter((n) => n.section === section).map((item) => <SideLink key={item.href} item={item} active={isActive(pathname, item.href)} collapsed={collapsed} />)}
            </div>
          </div>
        ))}
      </nav>

      <div className={cn("shrink-0 space-y-2 pb-4", collapsed ? "px-3" : "px-4")}>
        <SideLink item={settings} active={isActive(pathname, settings.href)} collapsed={collapsed} />
        <ProfileMenu variant={collapsed ? "avatar" : "card"} />
      </div>
    </aside>
  );
}

function SideLink({ item, active, collapsed }: { item: NavItem; active: boolean; collapsed: boolean }) {
  const link = (
    <Link href={item.href} aria-current={active ? "page" : undefined} aria-label={collapsed ? item.label : undefined}
      className={cn("group relative flex items-center gap-3 text-[13.5px] font-medium transition-colors duration-200",
        collapsed ? "mx-auto size-[52px] justify-center rounded-[18px]" : "h-12 rounded-full px-4",
        active ? "text-ink" : "text-ink-2/80 hover:text-ink")}>
      {active && <motion.span layoutId="nav-active" className="nav-pill absolute inset-0" style={{ borderRadius: collapsed ? 18 : 999 }} transition={SPRING} />}
      {!active && <span className={cn("absolute inset-0 bg-card/0 transition-colors duration-200 group-hover:bg-card/45", collapsed ? "rounded-[18px]" : "rounded-full")} aria-hidden />}
      <item.icon className={cn("relative size-[20px] shrink-0 transition-transform duration-200 group-hover:scale-105", active && "text-ink")} strokeWidth={1.75} aria-hidden />
      {!collapsed && <span className={cn("relative truncate", active && "font-semibold")}>{item.label}</span>}
    </Link>
  );
  return collapsed ? <Tip content={item.label}>{link}</Tip> : link;
}

function Header({ onSearch }: { onSearch: () => void }) {
  const { data: summary } = useSummary();
  const { data: me } = useMe();
  const sync = useSyncAll();
  const pathname = usePathname();
  const { privacy, togglePrivacy } = useUi();
  const [isMac, setIsMac] = React.useState(true);
  React.useEffect(() => setIsMac(/Mac|iPhone|iPad/.test(navigator.platform)), []);
  const nav = currentNav(pathname);
  const [scrolled, setScrolled] = React.useState(false);
  React.useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const first = me?.display_name?.split(" ")[0];
  const blurb = pathname === "/" && first ? `Welcome back, ${first} — here's where you stand` : nav?.blurb;
  return (
    <header className="sticky top-0 z-20">
      <div aria-hidden className={cn("header-glass pointer-events-none absolute inset-x-0 -bottom-8 top-0 transition-opacity duration-300", scrolled ? "opacity-100" : "opacity-0")} />
      <div className="relative mx-auto flex h-14 max-w-[1400px] items-center gap-2 px-4 sm:h-16 sm:px-6 lg:h-[76px] lg:px-8">
        <Link href="/" className="lg:hidden" aria-label="1Finance home"><LogoMark className="size-8" /></Link>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={nav?.href ?? pathname} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2 }}
            className="hidden min-w-0 lg:block">
            <p className="truncate text-[19.5px] font-semibold tracking-tight text-ink">{nav?.label ?? "1Finance"}</p>
            {blurb && <p className="truncate text-[15.5px] text-muted">{blurb}</p>}
          </motion.div>
        </AnimatePresence>
        <div className="ml-auto flex min-w-0 items-center gap-0.5 sm:gap-1">
          <button onClick={onSearch} aria-label="Search"
            className="mr-1 flex h-10 w-10 shrink-0 items-center justify-center gap-2 rounded-full border border-line/80 bg-card/80 text-[15.5px] text-faint shadow-card backdrop-blur transition-all duration-200 hover:border-line-strong hover:text-muted sm:w-64 sm:justify-start sm:px-4">
            <Search className="size-4 shrink-0" aria-hidden />
            <span className="hidden truncate sm:inline">Search…</span>
            <kbd className="ml-auto hidden rounded-full border border-line bg-bg-subtle px-2 py-0.5 font-sans text-[13.5px] text-muted sm:inline">{isMac ? "⌘" : "Ctrl"} K</kbd>
          </button>
          <span className="mr-1 hidden text-[14.5px] text-muted 2xl:inline" title={summary?.last_sync ?? undefined}>
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
          <span className="lg:hidden"><ProfileMenu variant="avatar" /></span>
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
        <p className="px-2.5 pb-1.5 pt-1 text-[13.5px] leading-snug text-faint">Original currencies are always preserved; conversions use stored exchange rates.</p>
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
          {data.length === 0 && <p className="px-3 py-6 text-center text-[15.5px] text-muted">You&apos;re all caught up.</p>}
          {data.map((n) => (
            <div key={n.id} className="rounded-xl px-3 py-2.5 hover:bg-bg-subtle">
              <div className="flex items-center gap-2">
                {!n.read && <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-label="Unread" />}
                <p className="text-[15.5px] font-medium text-ink">{n.title}</p>
              </div>
              {n.body && <p className="mt-0.5 text-[14.5px] text-muted">{n.body}</p>}
              <p className="mt-1 text-[13.5px] text-faint">{ago(n.created_at)}</p>
            </div>
          ))}
        </div>
      </MenuContent>
    </Menu>
  );
}

function ProfileMenu({ variant }: { variant: "avatar" | "card" }) {
  const { data: me } = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const initials = (me?.display_name ?? "?").split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();
  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.clear();
    router.replace("/login");
  };
  const avatar = <span className="grid size-11 shrink-0 place-items-center rounded-full bg-accent-soft text-[12.5px] font-semibold text-accent-fg ring-1 ring-accent/30">{initials}</span>;
  return (
    <Menu>
      <MenuTrigger asChild>
        {variant === "card" ? (
          <button className="flex w-full items-center gap-3 rounded-[22px] p-2 text-left transition-colors duration-200 hover:bg-card/55" aria-label="Profile menu">
            {avatar}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13.5px] font-semibold text-ink">{me?.display_name}</span>
              <span className="block truncate text-[11px] text-muted">{me?.email}</span>
            </span>
            <ChevronsUpDown className="size-4 shrink-0 text-muted" aria-hidden />
          </button>
        ) : (
          <button className="mx-auto grid place-items-center rounded-full transition-transform duration-200 hover:scale-105" aria-label="Profile menu">{avatar}</button>
        )}
      </MenuTrigger>
      <MenuContent className="w-60" side={variant === "card" ? "top" : "bottom"} align={variant === "card" ? "start" : "end"}>
        <div className="px-2.5 py-2">
          <p className="text-[15.5px] font-semibold text-ink">{me?.display_name}</p>
          <p className="truncate text-[14.5px] text-muted">{me?.email}</p>
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
      <div className="flex items-center gap-3 rounded-2xl border border-dashed border-warn/40 bg-warn-soft px-4 py-2.5 text-[15.5px] text-ink-2">
        <Badge tone="warn">Demo data</Badge>
        <span className="min-w-0 truncate">You&apos;re viewing generated demonstration data — nothing here is real financial information.</span>
        <Link href="/accounts?add=1" className="ml-auto hidden shrink-0 font-medium text-accent-fg hover:underline sm:inline">Connect a real account</Link>
      </div>
    </div>
  );
}

function BottomNav() {
  const pathname = usePathname();
  const router = useRouter();
  const more = NAV.filter((n) => !("mobile" in n && n.mobile));
  const moreActive = more.some((n) => isActive(pathname, n.href));
  const item = "relative flex flex-col items-center justify-center gap-0.5 text-[13px] font-medium transition-colors duration-200";
  return (
    <nav aria-label="Primary" className="fixed inset-x-3 bottom-3 z-30 lg:hidden" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div className="mx-auto grid h-[66px] max-w-lg grid-cols-5 gap-1 rounded-[26px] border border-white/60 bg-card/80 p-1.5 shadow-pop backdrop-blur-xl dark:border-white/5">
        {NAV.filter((n) => "mobile" in n && n.mobile).map((n) => {
          const active = isActive(pathname, n.href);
          return (
            <Link key={n.href} href={n.href} aria-label={n.label} aria-current={active ? "page" : undefined} className={cn(item, active ? "text-ink" : "text-muted")}>
              {active && <motion.span layoutId="bottom-active" className="absolute inset-0 rounded-[20px] bg-accent-soft" transition={SPRING} />}
              <n.icon className="relative size-5" strokeWidth={1.75} aria-hidden /><span className="relative">{"short" in n ? n.short : n.label}</span>
            </Link>
          );
        })}
        <Menu>
          <MenuTrigger className={cn(item, "rounded-[20px]", moreActive ? "bg-accent-soft text-ink" : "text-muted")} aria-label="More sections">
            <MoreHorizontal className="size-5" aria-hidden />More
          </MenuTrigger>
          <MenuContent side="top" className="mb-2 w-56">
            {more.map((n) => <MenuItem key={n.href} onSelect={() => router.push(n.href)}><n.icon />{n.label}</MenuItem>)}
            <MenuSeparator />
            <div className="flex items-center justify-between px-2.5 py-1 text-[15.5px] text-ink-2">Theme <ThemeMenu /></div>
          </MenuContent>
        </Menu>
      </div>
    </nav>
  );
}
