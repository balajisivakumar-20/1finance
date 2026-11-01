import * as React from "react";

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-[29px] font-semibold leading-tight tracking-tight text-ink sm:text-[37px]">{title}</h1>
        {subtitle && <p className="mt-1.5 text-[16px] text-muted">{subtitle}</p>}
      </div>
      {action && <div className="flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}

