"use client";
import { toast } from "sonner";

/** Registers the shell-only service worker and surfaces an "update available" prompt. */
export function registerServiceWorker() {
  if (typeof window === "undefined" || !("serviceWorker" in navigator) || process.env.NODE_ENV !== "production") return;
  navigator.serviceWorker.register("/sw.js").then((reg) => {
    reg.addEventListener("updatefound", () => {
      const sw = reg.installing;
      sw?.addEventListener("statechange", () => {
        if (sw.state === "installed" && navigator.serviceWorker.controller) {
          toast("A new version of 1Finance is available", {
            action: { label: "Update", onClick: () => { sw.postMessage("SKIP_WAITING"); window.location.reload(); } },
            duration: Infinity,
          });
        }
      });
    });
  }).catch(() => undefined);
}
