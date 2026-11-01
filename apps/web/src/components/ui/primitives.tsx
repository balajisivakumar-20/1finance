"use client";
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Inbox, Loader2, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------- Button ----------------
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-[background,color,box-shadow,transform,border-color] duration-200 ease-out active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-ink hover:bg-accent-hover shadow-[0_6px_16px_-8px_rgba(200,140,0,0.7)] hover:shadow-[0_10px_22px_-10px_rgba(200,140,0,0.8)]",
        secondary: "bg-card text-ink border border-line hover:bg-bg-subtle shadow-card",
        ghost: "text-ink-2 hover:bg-bg-subtle hover:text-ink",
        subtle: "bg-bg-subtle text-ink hover:bg-line",
        danger: "bg-neg text-white hover:opacity-90",
        link: "text-accent-fg underline-offset-4 hover:underline px-0 h-auto",
      },
      size: { sm: "h-8 px-3.5 text-[13px]", md: "h-10 px-5", lg: "h-12 px-6 text-[15px]", icon: "size-10", "icon-sm": "size-8" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} {...props}>
        {asChild ? children : <>{loading && <Loader2 className="animate-spin" aria-hidden />}{children}</>}
      </Comp>
    );
  },
);
Button.displayName = "Button";

// ---------------- Card ----------------
export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("hl rounded-[var(--radius-card)] border border-line/70 bg-card shadow-card", className)} {...p} />;
}
export function CardHeader({ title, description, action, className }: { title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 px-5 pt-5 sm:px-6", className)}>
      <div className="min-w-0">
        <h2 className="text-[17px] font-semibold tracking-tight text-ink">{title}</h2>
        {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}
export function CardBody({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 pb-5 pt-4 sm:px-6", className)} {...p} />;
}

// ---------------- Badge ----------------
const badgeVariants = cva("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium leading-4 [&_svg]:size-3", {
  variants: {
    tone: {
      neutral: "bg-bg-subtle text-ink-2",
      accent: "bg-accent-soft text-accent-fg",
      pos: "bg-pos-soft text-pos",
      neg: "bg-neg-soft text-neg",
      warn: "bg-warn-soft text-warn",
      info: "bg-info-soft text-info",
      outline: "border border-line text-muted",
    },
  },
  defaultVariants: { tone: "neutral" },
});
export function Badge({ className, tone, ...p }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...p} />;
}

// ---------------- Skeleton / states ----------------
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} aria-hidden />;
}

export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: {
  icon?: React.ElementType; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <div className="mb-3 grid size-11 place-items-center rounded-2xl bg-bg-subtle text-muted"><Icon className="size-5" aria-hidden /></div>
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-[13px] text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry, className }: { error: unknown; retry?: () => void; className?: string }) {
  const msg = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div role="alert" className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <div className="mb-3 grid size-11 place-items-center rounded-2xl bg-neg-soft text-neg"><AlertTriangle className="size-5" aria-hidden /></div>
      <p className="text-sm font-medium text-ink">Couldn&apos;t load this section</p>
      <p className="mt-1 max-w-sm text-[13px] text-muted">{msg}</p>
      {retry && <Button size="sm" className="mt-4" onClick={retry}><RotateCw />Try again</Button>}
    </div>
  );
}

// ---------------- Progress ----------------
export function Progress({ value, tone = "accent", className, label }: { value: number; tone?: "accent" | "warn" | "neg"; className?: string; label?: string }) {
  const v = Math.max(0, Math.min(100, value));
  const color = tone === "neg" ? "bg-neg" : tone === "warn" ? "bg-warn" : "bg-accent";
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v)} aria-label={label}
      className={cn("h-2.5 w-full overflow-hidden rounded-full bg-bg-subtle", className)}>
      <div className={cn("h-full rounded-full transition-[width] duration-1000 ease-[cubic-bezier(0.22,1,0.36,1)]", color)} style={{ width: `${v}%` }} />
    </div>
  );
}

// ---------------- Segmented control ----------------
export function Segmented<T extends string>({ value, onChange, options, className, size = "sm", label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode }[]; className?: string; size?: "sm" | "md"; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-full bg-bg-subtle p-1", className)}>
      {options.map((o) => (
        <button key={o.value} role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cn("rounded-full font-medium text-muted transition-all duration-200 hover:text-ink",
            size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
            value === o.value && "bg-card text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06),0_4px_10px_-4px_rgba(40,30,10,0.18)]")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------------- Form controls ----------------
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("h-11 w-full rounded-2xl border border-line bg-card px-4 text-sm text-ink placeholder:text-faint transition-shadow focus:border-accent focus:outline-none focus:ring-4 focus:ring-[var(--ring)] disabled:opacity-60", className)} {...p} />
));
Input.displayName = "Input";

export const NativeSelect = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, ...p }, ref) => (
  <select ref={ref} className={cn("h-11 w-full appearance-none rounded-2xl border border-line bg-card bg-[length:16px] bg-[right_14px_center] bg-no-repeat px-4 pr-9 text-sm text-ink focus:border-accent focus:outline-none focus:ring-4 focus:ring-[var(--ring)]", className)}
    style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }} {...p} />
));
NativeSelect.displayName = "NativeSelect";

export function Label({ className, ...p }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-[13px] font-medium text-ink-2", className)} {...p} />;
}

export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: string; error?: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error ? <p className="mt-1 text-xs text-neg" role="alert">{error}</p> : hint ? <p className="mt-1 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export function Switch({ checked, onCheckedChange, label, id }: { checked: boolean; onCheckedChange: (v: boolean) => void; label: string; id?: string }) {
  return (
    <SwitchPrimitive.Root id={id} aria-label={label} checked={checked} onCheckedChange={onCheckedChange}
      className="relative h-6 w-10 shrink-0 rounded-full bg-line-strong transition-colors data-[state=checked]:bg-accent">
      <SwitchPrimitive.Thumb className="block size-5 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
    </SwitchPrimitive.Root>
  );
}

export function Stat({ label, children, sub, className }: { label: string; children: React.ReactNode; sub?: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <p className="text-[12px] font-medium uppercase tracking-[0.06em] text-muted">{label}</p>
      <div className="mt-1.5 text-xl font-semibold tracking-tight text-ink tabular">{children}</div>
      {sub && <div className="mt-1 text-[12px] text-muted">{sub}</div>}
    </div>
  );
}
