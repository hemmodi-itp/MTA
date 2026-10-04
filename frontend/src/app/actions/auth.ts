"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { hashPassword, verifyPassword, verifyDummyPassword } from "@/lib/auth/password";
import { createSession, deleteSession, purgeExpiredSessions } from "@/lib/auth/session";
import { hit } from "@/lib/auth/rate-limit";

export type AuthFormState = {
  error?: string;
  fieldErrors?: Partial<Record<"name" | "email" | "password", string[]>>;
  email?: string;
} | undefined;

const signupSchema = z.object({
  name: z.string().trim().min(1, "Name is required.").max(100),
  email: z.email("Enter a valid email.").trim().toLowerCase(),
  password: z.string().min(8, "Password must be at least 8 characters.").max(200),
});

const loginSchema = z.object({
  email: z.email("Enter a valid email.").trim().toLowerCase(),
  password: z.string().min(1, "Password is required.").max(200),
});

// 10 attempts per 10 minutes, counted per client IP and per email address (whichever runs out first).
const LIMIT = 10;
const WINDOW_MS = 10 * 60_000;

async function clientIp() {
  const h = await headers();
  return h.get("x-forwarded-for")?.split(",")[0]?.trim() || h.get("x-real-ip")?.trim() || "unknown";
}

/** null when allowed, otherwise the message to show. Both counters are charged, so neither can be bypassed alone. */
async function rateLimited(action: "login" | "signup", email: string): Promise<string | null> {
  const byIp = hit(`${action}:ip:${await clientIp()}`, LIMIT, WINDOW_MS);
  const byEmail = hit(`${action}:email:${email}`, LIMIT, WINDOW_MS);
  if (byIp.ok && byEmail.ok) return null;
  const minutes = Math.ceil(Math.max(byIp.retryAfterSec, byEmail.retryAfterSec) / 60);
  return `Too many ${action === "login" ? "sign-in" : "sign-up"} attempts. Please wait ${minutes} minute${minutes === 1 ? "" : "s"} and try again.`;
}

export async function signup(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const parsed = signupSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return { fieldErrors: z.flattenError(parsed.error).fieldErrors, email: String(formData.get("email") ?? "") };
  }
  const { name, email, password } = parsed.data;

  const limited = await rateLimited("signup", email);
  if (limited) return { error: limited, email };

  // Same answer whether or not the email is registered, so sign-up can't be used to probe for accounts.
  const generic = { error: "Could not create an account with this email. If you already have one, try signing in.", email };
  const existing = await prisma.user.findUnique({ where: { email }, select: { id: true } });
  if (existing) return generic;

  let userId: string;
  try {
    const user = await prisma.user.create({ data: { name, email, passwordHash: await hashPassword(password) }, select: { id: true } });
    userId = user.id;
  } catch {
    return generic; // e.g. a concurrent sign-up with the same email won the unique constraint
  }
  await createSession(userId);
  redirect("/dashboard");
}

export async function login(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const parsed = loginSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) {
    return { fieldErrors: z.flattenError(parsed.error).fieldErrors, email: String(formData.get("email") ?? "") };
  }
  const { email, password } = parsed.data;

  const limited = await rateLimited("login", email);
  if (limited) return { error: limited, email };

  const user = await prisma.user.findUnique({ where: { email }, select: { id: true, passwordHash: true } });
  // Unknown email: still pay for one scrypt so the response time doesn't reveal whether the account exists.
  const valid = user ? await verifyPassword(password, user.passwordHash) : await verifyDummyPassword(password);
  if (!user || !valid) {
    return { error: "Invalid email or password.", email };
  }

  await purgeExpiredSessions().catch(() => undefined); // opportunistic housekeeping; never blocks a sign-in
  await createSession(user.id);
  redirect("/dashboard");
}

export async function logout() {
  await deleteSession();
  redirect("/login");
}
