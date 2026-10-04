"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import {
  CheckCircle2,
  FileText,
  Globe,
  Layers,
  Loader2,
  Lock,
  Rocket,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { cn } from "@/lib/utils";
import { useCreateProject } from "@/lib/query/hooks";
import { ApiError } from "@/lib/api/projects";
import { GITHUB_URL_RE, newProjectSchema, type NewProjectInput } from "@/lib/validation/project";
import type { SubmissionMode } from "@/lib/types";

const MODES: { value: SubmissionMode; title: string; description: string; icon: LucideIcon }[] = [
  {
    value: "brd_and_live",
    title: "BRD + live link",
    description: "The repo contains a BRD and the agent is deployed. MTA tests the live agent against your BRD.",
    icon: Layers,
  },
  {
    value: "live_only",
    title: "Only live link",
    description: "The agent is deployed but has no BRD. Gemini writes one from what the live app shows, then MTA tests the live agent against it.",
    icon: Globe,
  },
  {
    value: "brd_only",
    title: "Only BRD, not deployed",
    description: "The repo has a BRD but the agent isn't deployed. MTA reviews the code against the BRD and generates the tests.",
    icon: FileText,
  },
];

type RepoState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "public"; fullName: string; defaultBranch: string | null; verified: boolean }
  | { kind: "error"; message: string };

export default function NewProjectPage() {
  const router = useRouter();
  const createProject = useCreateProject();

  const form = useForm<NewProjectInput>({
    resolver: zodResolver(newProjectSchema),
    defaultValues: { githubUrl: "", mode: undefined, liveUrl: "", brdPath: "", branch: "", liveUsername: "", livePassword: "" },
  });
  const mode = useWatch({ control: form.control, name: "mode" });
  const githubUrl = useWatch({ control: form.control, name: "githubUrl" });

  // Check visibility as soon as the URL looks like a GitHub repo (debounced).
  const debouncedUrl = useDebounced(githubUrl?.trim() ?? "", 500);
  const urlLooksValid = GITHUB_URL_RE.test(debouncedUrl);
  const repoCheck = useQuery({
    queryKey: ["repo-check", debouncedUrl],
    queryFn: async () => {
      const res = await fetch(`/api/repos/check?url=${encodeURIComponent(debouncedUrl)}`);
      return (await res.json()) as
        | { ok: true; fullName: string; defaultBranch: string | null; verified: boolean }
        | { ok: false; error: string };
    },
    enabled: urlLooksValid,
    staleTime: 60_000,
  });
  const typing = (githubUrl?.trim() ?? "") !== debouncedUrl;
  const repo: RepoState = !GITHUB_URL_RE.test(githubUrl?.trim() ?? "")
    ? { kind: "idle" }
    : typing || repoCheck.isFetching || !repoCheck.data
      ? { kind: "checking" }
      : repoCheck.data.ok
        ? { kind: "public", ...repoCheck.data }
        : { kind: "error", message: repoCheck.data.error };

  async function onSubmit(values: NewProjectInput) {
    try {
      const result = await createProject.mutateAsync(values);
      if (result.alreadyRunning) {
        toast.info("An evaluation of this repository is already running", {
          description: "Your settings are saved for the next run. Opening the current one.",
        });
        router.push(`/runs/${result.runId}`);
        return;
      }
      toast.success("Evaluation queued", {
        description: result.backendReachable
          ? result.project.name
          : "The evaluation service isn't running yet — the run will start as soon as it is.",
      });
      router.push(`/runs/${result.runId}`);
    } catch (err) {
      if (err instanceof ApiError) {
        for (const [field, messages] of Object.entries(err.fieldErrors)) {
          if (messages?.[0]) form.setError(field as keyof NewProjectInput, { message: messages[0] });
        }
        toast.error(err.message);
      } else {
        toast.error("Could not start the evaluation. Please try again.");
      }
    }
  }

  const needsLive = mode === "brd_and_live" || mode === "live_only";
  const needsBrd = mode === "brd_and_live" || mode === "brd_only";

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Evaluate an agent</h1>
        <p className="text-sm text-muted-foreground">
          MTA downloads your agent&apos;s public GitHub repository and checks it against its BRD. If there is no BRD,
          Gemini writes one from your code. MTA then generates agent-specific and general test cases, runs them, and
          gives the agent a score.
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">1 · Repository</CardTitle>
              <CardDescription>The repository must be public, since MTA downloads it without credentials.</CardDescription>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="githubUrl"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>GitHub repository URL</FormLabel>
                    <FormControl>
                      <Input placeholder="https://github.com/acme/travel-agent" autoComplete="off" {...field} />
                    </FormControl>
                    <RepoStatus state={repo} />
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">2 · What does your repository contain?</CardTitle>
              <CardDescription>This decides how MTA gets the BRD and whether it can run tests against a live agent.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <FormField
                control={form.control}
                name="mode"
                render={({ field }) => (
                  <FormItem>
                    <div role="radiogroup" aria-label="Repository contents" className="grid gap-3 sm:grid-cols-3">
                      {MODES.map((m) => {
                        const selected = field.value === m.value;
                        return (
                          <button
                            key={m.value}
                            type="button"
                            role="radio"
                            aria-checked={selected}
                            onClick={() => field.onChange(m.value)}
                            className={cn(
                              "flex flex-col gap-2 rounded-lg border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                              selected ? "border-primary bg-primary/5 ring-1 ring-primary" : "border-border hover:bg-muted/50"
                            )}
                          >
                            <span className="flex items-center gap-2 text-sm font-medium">
                              <m.icon className={cn("size-4", selected ? "text-primary" : "text-muted-foreground")} />
                              {m.title}
                            </span>
                            <span className="text-xs leading-relaxed text-muted-foreground">{m.description}</span>
                          </button>
                        );
                      })}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {needsLive && (
                <FormField
                  control={form.control}
                  name="liveUrl"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Live agent URL</FormLabel>
                      <FormControl>
                        <Input placeholder="https://travel-agent.onrender.com" autoComplete="off" {...field} />
                      </FormControl>
                      <FormDescription>
                        An API base URL, a specific endpoint (e.g. …/chat) or a chat web page (Streamlit, Gradio…). MTA
                        works out how to talk to it. It must be reachable on the public internet: localhost, private
                        network and cloud-internal addresses are refused.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {needsLive && (
                <div className="space-y-3 rounded-lg border border-border p-4">
                  <div>
                    <p className="text-sm font-medium">
                      Test login for the live app <span className="font-normal text-muted-foreground">(optional)</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      If the app is behind a login, MTA signs in with this account to inspect and test it. It is stored
                      encrypted, used only by the evaluation service, and never shown again. Use a dedicated test account.
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="liveUsername"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Username or email</FormLabel>
                          <FormControl>
                            <Input autoComplete="off" placeholder="qa-bot@example.com" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="livePassword"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Password</FormLabel>
                          <FormControl>
                            <Input type="password" autoComplete="new-password" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </div>
              )}

              {needsBrd && (
                <FormField
                  control={form.control}
                  name="brdPath"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        BRD location in the repo <span className="font-normal text-muted-foreground">(optional)</span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="docs/BRD.pdf or https://github.com/owner/repo/blob/main/docs/BRD.pdf" autoComplete="off" {...field} />
                      </FormControl>
                      <FormDescription>
                        A path in the repo or the file&apos;s GitHub link. If you give one, MTA uses only that document,
                        and it can read scanned PDFs. If you leave it blank, MTA picks the document that matches your
                        agent (.md, .txt, .pdf or .docx).
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {mode && (
                <FormField
                  control={form.control}
                  name="branch"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Branch <span className="font-normal text-muted-foreground">(optional)</span>
                      </FormLabel>
                      <FormControl>
                        <Input
                          placeholder={repo.kind === "public" && repo.defaultBranch ? repo.defaultBranch : "default branch"}
                          autoComplete="off"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </CardContent>
          </Card>

          <div className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            You&apos;ll be taken to the live run view. It shows each step, the BRD, the generated test cases and, at the
            end, the agent&apos;s score. Expect{" "}
            <span className="font-medium text-foreground">
              {mode === "brd_only" ? "about 5–10 minutes" : "30–75 minutes"}
            </span>
            {mode === "brd_only"
              ? " for a code-only review."
              : " when MTA tests the live app in a browser (a code-only review takes about 5–10). The run view shows a live time-remaining estimate."}
          </div>

          <Button
            type="submit"
            className="w-full gap-2"
            disabled={createProject.isPending || repo.kind === "error" || repo.kind === "checking"}
          >
            {createProject.isPending ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}
            Start evaluation
          </Button>
        </form>
      </Form>
    </div>
  );
}

function RepoStatus({ state }: { state: RepoState }) {
  if (state.kind === "checking") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> Checking repository…
      </p>
    );
  }
  if (state.kind === "public") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-success">
        <CheckCircle2 className="size-3.5" />
        {state.verified
          ? `${state.fullName} is public${state.defaultBranch ? ` · default branch ${state.defaultBranch}` : ""}`
          : `Couldn't reach GitHub to confirm ${state.fullName} is public. MTA will check again before downloading it.`}
      </p>
    );
  }
  if (state.kind === "error") {
    return (
      <p className="flex items-center gap-1.5 text-xs text-critical">
        <Lock className="size-3.5" /> {state.message}
      </p>
    );
  }
  return <FormDescription>Only public repositories are supported.</FormDescription>;
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}
