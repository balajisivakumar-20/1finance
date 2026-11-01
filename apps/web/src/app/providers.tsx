"use client";
import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as Tooltip from "@radix-ui/react-tooltip";
import { MotionConfig } from "motion/react";
import { Toaster } from "sonner";
import { ApiError } from "@/lib/api";
import { registerServiceWorker } from "@/lib/pwa";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(() => new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2,
      },
    },
  }));
  React.useEffect(() => { registerServiceWorker(); }, []);
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <MotionConfig reducedMotion="user">
          <Tooltip.Provider>{children}</Tooltip.Provider>
        </MotionConfig>
        <Toaster position="bottom-right" toastOptions={{ className: "!rounded-2xl !border-line !bg-card !text-ink" }} />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
