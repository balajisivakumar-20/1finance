import type { Metadata } from "next";
import Link from "next/link";
import { LogoMark } from "@/components/brand";

export const metadata: Metadata = { title: "Privacy policy · 1Finance" };

const UPDATED = "2 November 2026";
const CONTACT = "privacy@1finance.win";

const SECTIONS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Who we are",
    body: <p>1Finance (1finance.win) is a personal finance app that brings your accounts, investments, budgets and goals into one place. This policy explains what we collect, why, and the choices you have.</p>,
  },
  {
    title: "What we collect",
    body: (
      <ul>
        <li><strong>Google account details.</strong> When you continue with Google we receive your name, email address and Google account ID. We never see your Google password.</li>
        <li><strong>Financial data you add.</strong> Accounts, balances, transactions, holdings, budgets, goals and anything you import or type in.</li>
        <li><strong>Connection credentials.</strong> If you link a broker (for example Groww or Interactive Brokers), we store the tokens needed for read-only access, encrypted.</li>
        <li><strong>Security records.</strong> Sign-in times, IP address and browser for your active sessions and audit log, plus your two-factor secret if you turn it on.</li>
      </ul>
    ),
  },
  {
    title: "How we use it",
    body: (
      <ul>
        <li>To sign you in and keep your account secure.</li>
        <li>To show you your own financial picture: totals, charts, reports and goal progress.</li>
        <li>To refresh data from the services you choose to connect.</li>
      </ul>
    ),
  },
  {
    title: "What we don't do",
    body: <p>We do not sell your data, show ads, or share your information with advertisers or data brokers. There are no third-party analytics or tracking scripts. Data from Google is used only to sign you in and is not used to train AI models.</p>,
  },
  {
    title: "Cookies",
    body: <p>We use only essential cookies: a session cookie that keeps you signed in, a security token that protects against cross-site requests, and a short-lived cookie during Google sign-in. No advertising or tracking cookies.</p>,
  },
  {
    title: "Where it is stored and who can see it",
    body: <p>Your data is stored in our own database on a server we operate, sent over HTTPS only, and visible only to your account. Connection credentials and two-factor secrets are encrypted at rest. We contact third parties only to sign you in (Google) and to fetch data from services you connect yourself.</p>,
  },
  {
    title: "Your choices",
    body: (
      <ul>
        <li><strong>Export:</strong> Settings → Export downloads all your data as JSON.</li>
        <li><strong>Delete:</strong> Settings lets you delete your financial data at any time. To close your account completely, email us and we will remove it within 30 days.</li>
        <li><strong>Disconnect:</strong> removing a connection deletes its stored credentials straight away. You can also revoke 1Finance&rsquo;s access from your Google account settings.</li>
      </ul>
    ),
  },
  {
    title: "Retention",
    body: <p>We keep your data while your account is open. When you delete data or close your account it is removed from the live database, and from backups within 30 days.</p>,
  },
  {
    title: "Children",
    body: <p>1Finance is not intended for anyone under 16.</p>,
  },
  {
    title: "Changes and contact",
    body: <p>If this policy changes we will update the date above. Questions or requests: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.</p>,
  },
];

export default function PrivacyPage() {
  return (
    <div className="min-h-viewport px-4 py-10 sm:py-16">
      <main id="main" className="mx-auto max-w-[720px]">
        <Link href="/" className="inline-flex items-center gap-2.5 text-ink">
          <LogoMark className="size-9" />
          <span className="text-lg font-semibold tracking-tight">1Finance</span>
        </Link>
        <h1 className="mt-8 text-3xl font-semibold tracking-tight text-ink">Privacy policy</h1>
        <p className="mt-2 text-sm text-muted">Last updated {UPDATED}</p>
        <div className="mt-8 space-y-4">
          {SECTIONS.map((s) => (
            <section key={s.title} className="rounded-[var(--radius-card)] border border-line/70 bg-card p-6 shadow-card">
              <h2 className="text-lg font-semibold text-ink">{s.title}</h2>
              <div className="mt-2 space-y-2 text-[16.5px] leading-relaxed text-muted [&_a]:text-accent-fg [&_a]:underline [&_li]:mt-1.5 [&_strong]:font-medium [&_strong]:text-ink [&_ul]:list-disc [&_ul]:pl-5">{s.body}</div>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
