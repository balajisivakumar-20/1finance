import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Outfit } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit", display: "swap" });

export const metadata: Metadata = {
  title: { default: "1Finance", template: "%s · 1Finance" },
  description: "One App. Every Asset. Complete Financial Clarity.",
  applicationName: "1Finance",
  manifest: "/manifest.webmanifest",
  // Versioned URLs so browsers and the service worker fetch the yellow icons instead of cached green ones.
  icons: {
    icon: [{ url: "/favicon.ico?v=2", sizes: "32x32" }, { url: "/icons/icon.svg?v=2", type: "image/svg+xml" }],
    apple: "/icons/apple-touch-icon.png?v=2",
  },
  appleWebApp: { capable: true, title: "1Finance", statusBarStyle: "default" },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F6F4F0" },
    { media: "(prefers-color-scheme: dark)", color: "#0B0F14" },
  ],
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${outfit.variable} ${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-card focus:px-3 focus:py-2">Skip to content</a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
