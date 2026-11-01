"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  currency: string | null; // null → user's saved base currency
  sidebarCollapsed: boolean;
  privacy: boolean; // hide balances on screen
  setCurrency: (c: string | null) => void;
  toggleSidebar: () => void;
  togglePrivacy: () => void;
}

/** Only non-sensitive UI preferences are persisted locally. Never financial data or tokens. */
export const useUi = create<UiState>()(
  persist(
    (set) => ({
      currency: null,
      sidebarCollapsed: false,
      privacy: false,
      setCurrency: (currency) => set({ currency }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      togglePrivacy: () => set((s) => ({ privacy: !s.privacy })),
    }),
    { name: "1f-ui", partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, privacy: s.privacy, currency: s.currency }) },
  ),
);
