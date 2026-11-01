"use client";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";
import { Fingerprint, Lock, ShieldCheck } from "lucide-react";
import { LogoMark } from "@/components/brand";
import { Button, Field, Input } from "@/components/ui/primitives";
import { Tip } from "@/components/ui/overlay";
import { api, ApiError } from "@/lib/api";

const GOOGLE_ERRORS: Record<string, string> = {
  google_cancelled: "Google sign-in was cancelled.",
  google_expired: "That sign-in link expired. Please try again.",
  google_unverified: "Your Google account's email address isn't verified.",
  google_failed: "We couldn't sign you in with Google. Please try again.",
};

function safeNext(n: string | null) {
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/";
}

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
  totp: z.string().regex(/^\d{6}$/, "Enter the 6-digit code").optional().or(z.literal("")),
});
type FormValues = z.infer<typeof schema>;

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [needsMfa, setNeedsMfa] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Never allow a native (pre-hydration) submit: it could place credentials in a URL.
  const [hydrated, setHydrated] = React.useState(false);
  React.useEffect(() => setHydrated(true), []);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", totp: "" },
  });

  const onSubmit = async (v: FormValues) => {
    setError(null);
    try {
      await api("/auth/login", { method: "POST", json: { email: v.email, password: v.password, totp: v.totp || undefined } });
      await qc.invalidateQueries();
      router.replace(safeNext(params.get("next")));
    } catch (e) {
      if (e instanceof ApiError) {
        const code = (e.body as { detail?: { code?: string } })?.detail?.code;
        if (code === "mfa_required") { setNeedsMfa(true); return; }
        setError(e.message);
      } else setError("Unable to reach 1Finance. Check your connection.");
    }
  };

  return (
    <form method="post" action="#" onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <Field label="Email" htmlFor="email" error={errors.email?.message}>
        <Input id="email" type="email" autoComplete="username webauthn" autoFocus {...register("email")} />
      </Field>
      <Field label="Password" htmlFor="password" error={errors.password?.message}>
        <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
      </Field>
      {needsMfa && (
        <Field label="Verification code" htmlFor="totp" error={errors.totp?.message} hint="From your authenticator app">
          <Input id="totp" inputMode="numeric" autoComplete="one-time-code" maxLength={6} {...register("totp")} />
        </Field>
      )}
      {error && <p role="alert" className="rounded-xl bg-neg-soft px-3 py-2 text-[15.5px] text-neg">{error}</p>}
      <Button type="submit" variant="primary" size="lg" className="w-full" loading={isSubmitting} disabled={!hydrated}>
        <Lock />Sign in
      </Button>
      <Tip content="Passkeys need HTTPS and a configured relying-party ID — see docs/SETUP.md.">
        <span className="block">
          <Button type="button" variant="secondary" size="lg" className="w-full" disabled><Fingerprint />Sign in with a passkey</Button>
        </span>
      </Tip>
    </form>
  );
}

function GoogleMfaForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/auth/google/mfa", { method: "POST", json: { totp: code } });
      await qc.invalidateQueries();
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach 1Finance. Check your connection.");
      setBusy(false);
    }
  };
  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <p className="text-[15.5px] text-ink-2">Signed in with Google. Enter the 6-digit code from your authenticator app to finish.</p>
      <Field label="Verification code" htmlFor="gtotp">
        <Input id="gtotp" inputMode="numeric" autoComplete="one-time-code" autoFocus maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
      </Field>
      {error && <p role="alert" className="rounded-xl bg-neg-soft px-3 py-2 text-[15.5px] text-neg">{error}</p>}
      <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy} disabled={code.length !== 6}><Lock />Verify</Button>
      <a href="/login" className="block text-center text-[15.5px] text-muted hover:text-ink">Start over</a>
    </form>
  );
}

function GoogleLogo() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden className="size-[18px]">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function SignIn({ health }: { health: { demo: boolean; google: boolean } | null }) {
  const params = useSearchParams();
  if (params.get("mfa") === "google") return <GoogleMfaForm />;
  const error = GOOGLE_ERRORS[params.get("error") ?? ""];
  const showPassword = !!health && (health.demo || !health.google);
  return (
    <div className="space-y-4">
      {error && <p role="alert" className="rounded-xl bg-neg-soft px-3 py-2 text-[15.5px] text-neg">{error}</p>}
      {health?.google && (
        <>
          <Button asChild variant="secondary" size="lg" className="w-full">
            <a href={`/api/v1/auth/google/start?next=${encodeURIComponent(safeNext(params.get("next")))}`}><GoogleLogo />Continue with Google</a>
          </Button>
          <p className="text-center text-[14.5px] text-muted">New to 1Finance? Continuing with Google creates your account.</p>
        </>
      )}
      {health?.google && showPassword && (
        <div className="flex items-center gap-3 text-[14.5px] text-faint"><span className="h-px flex-1 bg-line" />or sign in with email<span className="h-px flex-1 bg-line" /></div>
      )}
      {showPassword && <LoginForm />}
    </div>
  );
}

export default function LoginPage() {
  const [health, setHealth] = React.useState<{ demo: boolean; google: boolean } | null>(null);
  React.useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then((h) => setHealth({ demo: !!h.demo_mode, google: !!h.google_enabled })).catch(() => setHealth({ demo: false, google: false }));
  }, []);
  const demo = !!health?.demo;
  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden px-4">
      <div aria-hidden className="pointer-events-none absolute inset-0 [background:radial-gradient(60%_50%_at_50%_0%,var(--accent-soft),transparent_70%)]" />
      <main id="main" className="relative w-full max-w-[400px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <LogoMark className="size-12" />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink">Welcome to 1Finance</h1>
          <p className="mt-1.5 text-sm text-muted">One app. Every asset. Complete financial clarity.</p>
        </div>
        <div className="hl rounded-3xl border border-line bg-card p-6 shadow-pop sm:p-7">
          <React.Suspense><SignIn health={health} /></React.Suspense>
        </div>
        <div className="mt-5 space-y-2 text-center text-[14.5px] text-muted">
          <p className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-accent-fg" />Read-only access · Encrypted credentials · No ads, ever</p>
          {demo && <p className="text-faint">Demo mode · demo@1finance.app / demo-1finance</p>}
        </div>
      </main>
    </div>
  );
}
