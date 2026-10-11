"use client";

import { useActionState, useState, type ComponentType, type ReactNode } from "react";
import Link from "next/link";
import { m } from "framer-motion";
import {
  AlertCircle, ArrowRight, Eye, EyeOff, FileCheck2, Gauge, Loader2, Lock, Mail, PlayCircle, Sparkles, User,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { ease, fadeUp, stagger } from "@/lib/motion";
import { login, signup, type AuthFormState } from "@/app/actions/auth";

const FEATURES = [
  { icon: FileCheck2, title: "BRD traceability", body: "Every requirement mapped to the code and tests that prove it." },
  { icon: PlayCircle, title: "Runtime verified", body: "Generated tests run against the live app, not just read from the repo." },
  { icon: Gauge, title: "Scored on 8 dimensions", body: "Compliance, security, architecture, performance and production readiness." },
];

const PIPELINE = ["Fetch repo", "Analyze", "Trace BRD", "Generate tests", "Run live", "Score"];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-3">
      <div className="relative flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet text-white shadow-lg shadow-primary/30">
        <Sparkles className="size-5" />
        <span className="absolute inset-0 rounded-xl ring-1 ring-inset ring-white/20" />
      </div>
      <div className="flex flex-col leading-tight">
        <span className="text-base font-bold tracking-tight">MTA</span>
        <span className="text-xs font-medium text-muted-foreground">Master Testing Agent</span>
      </div>
    </Link>
  );
}

function Field({
  id, label, icon: Icon, error, children,
}: { id: string; label: string; icon: ComponentType<{ className?: string }>; error?: string[]; children: ReactNode }) {
  return (
    <m.div variants={fadeUp} className="space-y-2">
      <Label htmlFor={id} className="text-[13px]">{label}</Label>
      <div className="group relative">
        <Icon className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground transition-colors group-focus-within:text-primary" />
        {children}
      </div>
      {error?.length ? <p id={`${id}-error`} className="text-xs text-destructive">{error[0]}</p> : null}
    </m.div>
  );
}

const inputClass = "h-11 rounded-xl bg-background/60 pl-10 text-sm shadow-xs transition-shadow focus-visible:shadow-[0_0_0_4px_var(--glow)]";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const isSignup = mode === "signup";
  const [state, action, pending] = useActionState<AuthFormState, FormData>(isSignup ? signup : login, undefined);
  const [showPassword, setShowPassword] = useState(false);
  const errs = state?.fieldErrors;

  return (
    <main className="relative grid min-h-full flex-1 lg:grid-cols-[1.1fr_1fr]">
      <div className="app-backdrop" />

      {/* ── showcase panel (desktop) ─────────────────────────────────────── */}
      <section className="relative hidden overflow-hidden border-r border-border/60 lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.35] [background-image:linear-gradient(var(--border)_1px,transparent_1px),linear-gradient(90deg,var(--border)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_30%_40%,black,transparent_70%)]"
        />
        <div aria-hidden className="pointer-events-none absolute -top-32 -left-24 size-[28rem] rounded-full bg-primary/20 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-40 right-0 size-[26rem] rounded-full bg-violet/20 blur-3xl" />

        <m.div initial="hidden" animate="show" variants={stagger(0.08, 0.05)} className="relative">
          <m.div variants={fadeUp}><Brand /></m.div>
        </m.div>

        <m.div initial="hidden" animate="show" variants={stagger(0.08, 0.15)} className="relative max-w-lg">
          <m.span
            variants={fadeUp}
            className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary"
          >
            <Sparkles className="size-3.5" /> Autonomous agent QA
          </m.span>
          <m.h1 variants={fadeUp} className="mt-5 text-4xl leading-[1.1] font-bold tracking-tight text-balance xl:text-5xl">
            <span className="text-gradient">Know your agent is ready</span> before your users do.
          </m.h1>
          <m.p variants={fadeUp} className="mt-4 text-base text-pretty text-muted-foreground">
            Point MTA at a repo and its requirements. It traces every requirement, runs the app live and scores it,
            with no hand-written tests.
          </m.p>

          <ul className="mt-10 space-y-5">
            {FEATURES.map((f) => (
              <m.li key={f.title} variants={fadeUp} className="flex gap-4">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-border bg-card/70 text-primary shadow-sm backdrop-blur">
                  <f.icon className="size-[18px]" />
                </div>
                <div>
                  <p className="text-sm font-semibold">{f.title}</p>
                  <p className="text-sm text-muted-foreground">{f.body}</p>
                </div>
              </m.li>
            ))}
          </ul>
        </m.div>

        <m.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.6, ease: ease.out }}
          className="glass relative rounded-2xl p-5"
        >
          <p className="mb-3 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">How a run works</p>
          <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
            {PIPELINE.map((step, i) => (
              <m.li
                key={step}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.75 + i * 0.08, duration: 0.3, ease: ease.out }}
                className="flex items-center gap-1.5"
              >
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background/70 px-2.5 py-1 text-xs font-medium">
                  <span className="flex size-4 items-center justify-center rounded-full bg-gradient-to-br from-primary to-violet text-[9px] font-bold text-white tabular-nums">
                    {i + 1}
                  </span>
                  {step}
                </span>
                {i < PIPELINE.length - 1 && <ArrowRight className="size-3 text-muted-foreground/60" />}
              </m.li>
            ))}
          </ol>
        </m.div>
      </section>

      {/* ── form panel ───────────────────────────────────────────────────── */}
      <section className="relative flex items-center justify-center px-4 py-12 sm:px-8">
        <div aria-hidden className="pointer-events-none absolute top-1/4 left-1/2 size-80 -translate-x-1/2 rounded-full bg-primary/15 blur-3xl lg:hidden" />

        <m.div
          initial={{ opacity: 0, y: 16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: ease.emphasized }}
          className="relative w-full max-w-[420px]"
        >
          <div className="mb-8 flex justify-center lg:hidden"><Brand /></div>

          <div className="gradient-border rounded-2xl p-7 shadow-2xl shadow-primary/10 backdrop-blur-xl sm:p-9">
            <m.div initial="hidden" animate="show" variants={stagger(0.06, 0.2)}>
              <m.div variants={fadeUp} className="mb-7">
                <h2 className="text-2xl font-bold tracking-tight">{isSignup ? "Create your account" : "Welcome back"}</h2>
                <p className="mt-1.5 text-sm text-muted-foreground">
                  {isSignup ? "Start evaluating your agents in minutes." : "Log in to see how your agents are doing."}
                </p>
              </m.div>

              <form action={action} className="space-y-4" noValidate>
                {isSignup && (
                  <Field id="name" label="Name" icon={User} error={errs?.name}>
                    <Input
                      id="name" name="name" autoComplete="name" placeholder="Ada Lovelace" required
                      aria-invalid={!!errs?.name} aria-describedby={errs?.name ? "name-error" : undefined}
                      className={inputClass}
                    />
                  </Field>
                )}
                <Field id="email" label="Email" icon={Mail} error={errs?.email}>
                  <Input
                    id="email" name="email" type="email" autoComplete="email" placeholder="you@company.com"
                    defaultValue={state?.email} required
                    aria-invalid={!!errs?.email} aria-describedby={errs?.email ? "email-error" : undefined}
                    className={inputClass}
                  />
                </Field>
                <Field id="password" label="Password" icon={Lock} error={errs?.password}>
                  <Input
                    id="password" name="password" type={showPassword ? "text" : "password"}
                    autoComplete={isSignup ? "new-password" : "current-password"} placeholder="••••••••" required
                    aria-invalid={!!errs?.password} aria-describedby={errs?.password ? "password-error" : undefined}
                    className={cn(inputClass, "pr-11")}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="absolute top-1/2 right-2 flex size-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </Field>

                {state?.error && (
                  <m.div
                    initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                    role="alert"
                    className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
                  >
                    <AlertCircle className="mt-0.5 size-4 shrink-0" />
                    {state.error}
                  </m.div>
                )}

                <m.div variants={fadeUp} className="pt-2">
                  <m.button
                    type="submit"
                    disabled={pending}
                    whileHover={pending ? undefined : { y: -1 }}
                    whileTap={pending ? undefined : { scale: 0.98 }}
                    className="group relative flex h-11 w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-primary to-violet text-sm font-semibold text-white shadow-lg shadow-primary/30 transition-shadow hover:shadow-xl hover:shadow-primary/40 focus-visible:ring-4 focus-visible:ring-ring/40 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    <span className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/15 to-white/0 opacity-0 transition-opacity group-hover:opacity-100" />
                    {pending ? (
                      <><Loader2 className="size-4 animate-spin" /> Please wait…</>
                    ) : (
                      <>
                        {isSignup ? "Create account" : "Log in"}
                        <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                      </>
                    )}
                  </m.button>
                </m.div>
              </form>

              <m.div variants={fadeUp} className="mt-7 flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                {isSignup ? "Already have an account?" : "New to MTA?"}
                <span className="h-px flex-1 bg-border" />
              </m.div>
              <m.div variants={fadeUp} className="mt-4">
                <Link
                  href={isSignup ? "/login" : "/signup"}
                  className="flex h-11 w-full items-center justify-center rounded-xl border border-border bg-background/50 text-sm font-medium transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
                >
                  {isSignup ? "Log in instead" : "Create an account"}
                </Link>
              </m.div>
            </m.div>
          </div>
        </m.div>
      </section>
    </main>
  );
}
