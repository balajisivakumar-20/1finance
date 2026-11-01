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
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
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
      {error && <p role="alert" className="rounded-xl bg-neg-soft px-3 py-2 text-[13px] text-neg">{error}</p>}
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

export default function LoginPage() {
  const [demo, setDemo] = React.useState(false);
  React.useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then((h) => setDemo(!!h.demo_mode)).catch(() => undefined);
  }, []);
  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden px-4">
      <div aria-hidden className="pointer-events-none absolute inset-0 [background:radial-gradient(60%_50%_at_50%_0%,var(--accent-soft),transparent_70%)]" />
      <main id="main" className="relative w-full max-w-[400px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <LogoMark className="size-12" />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink">Welcome to 1Finance</h1>
          <p className="mt-1.5 text-sm text-muted">One app. Every asset. Complete financial clarity.</p>
        </div>
        <div className="rounded-3xl border border-line bg-card p-6 shadow-pop sm:p-7">
          <React.Suspense><LoginForm /></React.Suspense>
        </div>
        <div className="mt-5 space-y-2 text-center text-[12px] text-muted">
          <p className="inline-flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-accent" />Read-only access · Encrypted credentials · No ads, ever</p>
          {demo && <p className="text-faint">Demo mode · demo@1finance.app / demo-1finance</p>}
        </div>
      </main>
    </div>
  );
}
