"use client";
import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as DM from "@radix-ui/react-dropdown-menu";
import * as TT from "@radix-ui/react-tooltip";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Right-side drawer on desktop, bottom sheet on mobile. */
export function Sheet({ open, onOpenChange, title, description, children, footer, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: React.ReactNode; description?: React.ReactNode;
  children: React.ReactNode; footer?: React.ReactNode; wide?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
        <Dialog.Content
          className={cn(
            "fixed z-50 flex flex-col bg-card shadow-pop outline-none",
            "inset-x-0 bottom-0 max-h-[92dvh] rounded-t-3xl border-t border-line data-[state=open]:animate-fade-in",
            "sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[440px] sm:rounded-none sm:rounded-l-3xl sm:border-l sm:border-t-0 sm:data-[state=open]:animate-slide-in",
            wide && "sm:w-[560px]",
          )}>
          <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line-strong sm:hidden" aria-hidden />
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <div className="min-w-0">
              <Dialog.Title className="truncate text-base font-semibold text-ink">{title}</Dialog.Title>
              {description ? <Dialog.Description className="mt-0.5 text-[13px] text-muted">{description}</Dialog.Description>
                : <Dialog.Description className="sr-only">Details</Dialog.Description>}
            </div>
            <Dialog.Close className="grid size-8 place-items-center rounded-lg text-muted hover:bg-bg-subtle hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer && <div className="border-t border-line px-6 py-4 pb-safe">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Modal({ open, onOpenChange, title, description, children, className }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: React.ReactNode; description?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/35 backdrop-blur-[2px] data-[state=open]:animate-fade-in" />
        <Dialog.Content className={cn("fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100vw-24px)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-3xl border border-line bg-card p-6 shadow-pop outline-none data-[state=open]:animate-fade-in", className)}>
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold tracking-tight text-ink">{title}</Dialog.Title>
              {description ? <Dialog.Description className="mt-1 text-[13px] text-muted">{description}</Dialog.Description>
                : <Dialog.Description className="sr-only">Dialog</Dialog.Description>}
            </div>
            <Dialog.Close className="grid size-8 place-items-center rounded-lg text-muted hover:bg-bg-subtle hover:text-ink" aria-label="Close"><X className="size-4" /></Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export const Menu = DM.Root;
export const MenuTrigger = DM.Trigger;
export function MenuContent({ className, align = "end", ...p }: DM.DropdownMenuContentProps) {
  return (
    <DM.Portal>
      <DM.Content align={align} sideOffset={6} className={cn("z-50 min-w-48 rounded-2xl border border-line bg-card p-1.5 shadow-pop data-[state=open]:animate-fade-in", className)} {...p} />
    </DM.Portal>
  );
}
export function MenuItem({ className, ...p }: DM.DropdownMenuItemProps) {
  return <DM.Item className={cn("flex cursor-default select-none items-center gap-2.5 rounded-xl px-2.5 py-2 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-bg-subtle data-[highlighted]:text-ink [&_svg]:size-4 [&_svg]:text-muted", className)} {...p} />;
}
export function MenuLabel({ className, ...p }: DM.DropdownMenuLabelProps) {
  return <DM.Label className={cn("px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-faint", className)} {...p} />;
}
export const MenuSeparator = () => <DM.Separator className="my-1 h-px bg-line" />;
export const MenuRadioGroup = DM.RadioGroup;
export function MenuRadioItem({ className, children, ...p }: DM.DropdownMenuRadioItemProps) {
  return (
    <DM.RadioItem className={cn("flex cursor-default select-none items-center justify-between gap-2.5 rounded-xl px-2.5 py-2 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-bg-subtle data-[state=checked]:font-medium data-[state=checked]:text-ink", className)} {...p}>
      {children}
      <DM.ItemIndicator><span className="size-1.5 rounded-full bg-accent block" /></DM.ItemIndicator>
    </DM.RadioItem>
  );
}

export function Tip({ content, children }: { content: React.ReactNode; children: React.ReactNode }) {
  return (
    <TT.Root delayDuration={250}>
      <TT.Trigger asChild>{children}</TT.Trigger>
      <TT.Portal>
        <TT.Content sideOffset={6} className="z-50 max-w-64 rounded-lg bg-ink px-2.5 py-1.5 text-xs text-bg shadow-pop data-[state=delayed-open]:animate-fade-in">{content}</TT.Content>
      </TT.Portal>
    </TT.Root>
  );
}
