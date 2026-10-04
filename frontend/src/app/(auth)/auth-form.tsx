"use client";

import { useActionState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { login, signup, type AuthFormState } from "@/app/actions/auth";

function FieldError({ messages }: { messages?: string[] }) {
  if (!messages?.length) return null;
  return <p className="text-xs text-destructive">{messages[0]}</p>;
}

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const isSignup = mode === "signup";
  const [state, action, pending] = useActionState<AuthFormState, FormData>(isSignup ? signup : login, undefined);

  return (
    <main className="flex min-h-full flex-1 items-center justify-center px-4 py-16">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <div className="mb-2 flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Sparkles className="size-5" />
          </div>
          <CardTitle>{isSignup ? "Create your MTA account" : "Log in to MTA"}</CardTitle>
          <CardDescription>Evaluate an agent&apos;s quality in minutes.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={action} className="space-y-4" noValidate>
            {isSignup && (
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input id="name" name="name" autoComplete="name" placeholder="Ada Lovelace" required />
                <FieldError messages={state?.fieldErrors?.name} />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                defaultValue={state?.email}
                required
              />
              <FieldError messages={state?.fieldErrors?.email} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={isSignup ? "new-password" : "current-password"}
                placeholder="••••••••"
                required
              />
              <FieldError messages={state?.fieldErrors?.password} />
            </div>
            {state?.error && <p className="text-sm text-destructive">{state.error}</p>}
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "Please wait…" : isSignup ? "Create account" : "Log in"}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center text-sm text-muted-foreground">
          {isSignup ? (
            <span>
              Already have an account?{" "}
              <Link href="/login" className="text-foreground underline underline-offset-4">Log in</Link>
            </span>
          ) : (
            <span>
              New to MTA?{" "}
              <Link href="/signup" className="text-foreground underline underline-offset-4">Create an account</Link>
            </span>
          )}
        </CardFooter>
      </Card>
    </main>
  );
}
