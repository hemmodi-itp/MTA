import { z } from "zod";

export const GITHUB_URL_RE = /^https:\/\/(www\.)?github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9._-]+?(\.git)?\/?$/;

export const SUBMISSION_MODES = ["brd_and_live", "live_only", "brd_only"] as const;

/**
 * Syntax-level check of a live URL, shared by the form and the API: a full http(s) URL without "user:pass@".
 * Whether the host is allowed (public internet only) is decided server-side in lib/api/server/url-safety.ts,
 * which also resolves the hostname.
 */
export function liveUrlSyntaxError(value: string): string | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return "Must be a full http(s):// URL";
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return "Only http:// and https:// URLs are supported";
  if (url.username || url.password) {
    return "Don't put a username or password in the URL. Use the test login fields below instead";
  }
  if (!url.hostname) return "Must be a full http(s):// URL";
  return null;
}

/** Shared by the New Project form (client) and POST /api/projects (server). */
export const newProjectSchema = z
  .object({
    githubUrl: z
      .string()
      .trim()
      .min(1, "Repository URL is required")
      .regex(GITHUB_URL_RE, "Must be a GitHub repository URL like https://github.com/owner/repo"),
    mode: z.enum(SUBMISSION_MODES, { message: "Choose what your repository contains" }),
    liveUrl: z.string().trim().max(500).optional().or(z.literal("")),
    brdPath: z
      .string()
      .trim()
      .max(300)
      .refine((v) => !v.includes(".."), "Path must stay inside the repository")
      .optional()
      .or(z.literal("")),
    branch: z.string().trim().max(200).optional().or(z.literal("")),
    // Optional test account for a live app behind a login (encrypted server-side, never returned).
    liveUsername: z.string().trim().max(200).optional().or(z.literal("")),
    livePassword: z.string().max(200).optional().or(z.literal("")),
  })
  .superRefine((v, ctx) => {
    if (!!v.liveUsername !== !!v.livePassword) {
      ctx.addIssue({ code: "custom", path: [v.liveUsername ? "livePassword" : "liveUsername"],
        message: "Enter both the username and the password, or neither" });
    }
    if (v.mode === "brd_only") return;
    if (!v.liveUrl) {
      ctx.addIssue({ code: "custom", path: ["liveUrl"], message: "A live URL is required for this option" });
      return;
    }
    const urlError = /^https?:\/\/[^\s/$.?#].[^\s]*$/i.test(v.liveUrl) ? liveUrlSyntaxError(v.liveUrl) : "Must be a full http(s):// URL";
    if (urlError) ctx.addIssue({ code: "custom", path: ["liveUrl"], message: urlError });
  });

export type NewProjectInput = z.infer<typeof newProjectSchema>;
