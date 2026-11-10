"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, UserRound, X } from "lucide-react";
import { Dialog } from "radix-ui";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { getIdentity, getServerIdentity, signInPersonal, signOut, subscribeIdentity } from "@/lib/guest";

export function useIdentity() {
  return React.useSyncExternalStore(subscribeIdentity, getIdentity, getServerIdentity);
}

/** Sidebar footer line: "Add email or username" → small dialog; signed in → handle + sign out. */
export function IdentityControl({ onDone }: { onDone?: () => void }) {
  const identity = useIdentity();
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [handle, setHandle] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.identify(handle);
      signInPersonal({ attendeeId: r.attendee_id, kind: r.kind, display: r.display });
      await qc.resetQueries(); // reload profile, agenda and recommendations for this person
      setOpen(false);
      setHandle("");
      onDone?.(); // e.g. close the mobile menu
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const line = "flex h-8 w-full items-center gap-2 rounded-lg px-2 text-[12.5px] text-ink-3 hover:bg-surface-2 hover:text-ink";

  if (identity.status === "personal") {
    return (
      <div className="flex items-center gap-1">
        <span className="flex h-8 min-w-0 flex-1 items-center gap-2 px-2 text-[12.5px] text-ink-2" title="Your profile and agenda follow this handle on any device">
          <UserRound className="size-4 shrink-0 text-needle" />
          <span className="truncate">{identity.display}</span>
        </span>
        <button
          onClick={async () => {
            signOut();
            await qc.resetQueries();
            onDone?.();
          }}
          className="rounded-md p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink"
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className={line}>
        <UserRound className="size-4" />
        Add email or username
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 animate-fade bg-black/25 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-32px)] max-w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-lg)] outline-none">
          <div className="flex items-start justify-between gap-4">
            <Dialog.Title className="text-[15px] font-semibold text-ink">Your personalized experience</Dialog.Title>
            <Dialog.Close className="rounded-md p-1 text-ink-3 hover:bg-surface-2 hover:text-ink" aria-label="Close">
              <X className="size-4" />
            </Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-[13px] text-ink-3">
            Add your email or a username to keep your interests and agenda, and get them back on any device.
            Prefer not to share your email? A username works just as well.
          </Dialog.Description>
          <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
            <label className="flex flex-col gap-1.5 text-[12.5px] font-medium text-ink-2">
              Email or username
              <input
                autoFocus
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                placeholder="you@example.com or kube_fan"
                autoComplete="username"
                maxLength={254}
                className="h-10 rounded-[10px] border border-line bg-bg px-3 text-[14px] font-normal text-ink outline-none focus-visible:border-needle focus-visible:ring-2 focus-visible:ring-needle/20"
              />
            </label>
            {error && (
              <p role="alert" className="text-[12.5px] text-danger">
                {error}
              </p>
            )}
            <Button type="submit" variant="accent" disabled={busy || handle.trim().length === 0}>
              {busy ? "Saving…" : "Continue"}
            </Button>
            <p className="text-[11.5px] leading-relaxed text-ink-4">
              No password: anyone who enters the same handle sees the same agenda. Your email is never stored;
              only a one-way code derived from it.
            </p>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
