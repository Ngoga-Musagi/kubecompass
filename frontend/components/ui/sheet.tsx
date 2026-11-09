"use client";

import { X } from "lucide-react";
import { Dialog } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

/** Side sheet (desktop) / bottom sheet (mobile) built on Radix Dialog. */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  width = 480,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: number;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 animate-fade bg-black/25 backdrop-blur-[2px]" />
        <Dialog.Content
          style={{ "--sheet-w": `${width}px` } as React.CSSProperties}
          className={cn(
            "fixed z-50 flex flex-col bg-surface shadow-[var(--shadow-lg)] outline-none animate-rise",
            "inset-x-0 bottom-0 max-h-[88dvh] rounded-t-2xl border-t border-line",
            "sm:inset-y-2 sm:right-2 sm:left-auto sm:max-h-none sm:w-[var(--sheet-w)] sm:rounded-2xl sm:border",
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="text-[15px] font-semibold text-ink">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-0.5 text-[13px] text-ink-3">{description}</Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{String(title)}</Dialog.Description>
              )}
            </div>
            <Dialog.Close className="rounded-md p-1 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="border-t border-line px-5 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
