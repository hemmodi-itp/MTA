import Link from "next/link";
import { ArrowRight, GitBranch, Sparkles, Wand2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ExecutionStepper } from "@/components/runs/execution-stepper";

const FEATURES = [
  {
    icon: GitBranch,
    title: "Point at a repo",
    body: "Paste a GitHub URL — MTA clones it, installs dependencies, and boots the app for you.",
  },
  {
    icon: Wand2,
    title: "Tests write themselves",
    body: "Discovery and comprehension turn business scenarios into a full Playwright suite, no manual scripting.",
  },
  {
    icon: ShieldCheck,
    title: "Self-healing execution",
    body: "Flaky locators and timing issues get patched and re-verified automatically — real defects surface instead.",
  },
];

export default function LandingPage() {
  return (
    <main className="flex min-h-full flex-col">
      <header className="flex items-center justify-between px-6 py-4 sm:px-10">
        <div className="flex items-center gap-2 font-semibold">
          <div className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="size-4" />
          </div>
          MTA
        </div>
        <div className="flex items-center gap-3">
          <Button variant="ghost" asChild>
            <Link href="/login">Log in</Link>
          </Button>
          <Button asChild>
            <Link href="/signup">Get started</Link>
          </Button>
        </div>
      </header>

      <section className="mx-auto flex max-w-3xl flex-1 flex-col items-center px-6 pt-16 text-center sm:pt-24">
        <h1 className="text-balance text-4xl font-bold tracking-tight sm:text-5xl">
          Autonomous QA for the agents you ship
        </h1>
        <p className="mt-4 max-w-xl text-balance text-muted-foreground sm:text-lg">
          Give MTA a GitHub URL. It discovers business scenarios, writes and runs a Playwright suite,
          heals what breaks, and scores the result — no manual test authoring.
        </p>
        <div className="mt-8 flex gap-3">
          <Button size="lg" asChild>
            <Link href="/login" className="gap-2">
              Start an evaluation <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>

        <div className="mt-14 w-full max-w-sm rounded-xl border border-border bg-card p-5 text-left shadow-sm">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Run #129 · acme/checkout-agent
          </p>
          <ExecutionStepper currentStage="ui_execution" isComplete={false} />
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-4xl gap-6 px-6 py-20 sm:grid-cols-3">
        {FEATURES.map((f) => (
          <div key={f.title} className="space-y-2">
            <f.icon className="size-5 text-primary" />
            <p className="font-medium">{f.title}</p>
            <p className="text-sm text-muted-foreground">{f.body}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
