import { cn } from "@/lib/utils";

/** 1Finance mark: a geometric "1" whose flag is a rising line ending in a data point — growth from a single source. */
export function LogoMark({ className, title = "1Finance" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={cn("size-8", className)} role="img" aria-label={title}>
      <rect width="40" height="40" rx="11" fill="var(--accent)" />
      <path d="M12.5 18.5 L21.5 11 V30" fill="none" stroke="var(--accent-ink)" strokeWidth="4.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 30 H27" stroke="var(--accent-ink)" strokeWidth="4.2" strokeLinecap="round" opacity="0.55" />
      <circle cx="28.5" cy="11.5" r="2.6" fill="var(--accent-ink)" opacity="0.9" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark className="size-8" />
      <span className="text-[17px] font-semibold tracking-tight text-ink">
        1<span className="text-ink-2">Finance</span>
      </span>
    </span>
  );
}
