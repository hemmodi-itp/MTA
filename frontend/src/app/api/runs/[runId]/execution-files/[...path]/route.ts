import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";

// Same default as the Python service (agents/test_execution/playwright_executor/agent.py): <repo>/.aqp_artifacts
const ARTIFACT_ROOT = path.resolve(process.env.AQP_ARTIFACT_DIR ?? path.join(process.cwd(), "..", ".aqp_artifacts"), "runs");

const MAX_BYTES = 50 * 1024 * 1024;

const INLINE: Record<string, string> = {
  ".png": "image/png",
  ".txt": "text/plain; charset=utf-8",
};

/**
 * A file the Playwright Executor saved for a run (screenshot, page text, downloaded document).
 * Only for viewers of the run; paths are confined to that run's artifact folder. Anything that is not a
 * screenshot or plain text is served as an attachment so app-produced files never render in MTA's origin.
 * Streamed from disk (never buffered whole), and refused with 413 above 50 MB.
 */
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string; path: string[] }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId, path: parts } = await params;
  const run = await prisma.run.findFirst({ where: { id: runId, ...visibleRuns(user.id) }, select: { id: true } });
  if (!run || !/^[A-Za-z0-9_-]+$/.test(runId)) return notFound();

  const base = path.join(ARTIFACT_ROOT, runId);
  const file = path.resolve(base, ...parts.map((p) => decodeURIComponent(p)));
  if (!file.startsWith(base + path.sep) || parts.some((p) => p.startsWith("."))) return notFound();
  let size: number;
  try {
    const info = await stat(file);
    if (!info.isFile()) return notFound();
    size = info.size;
  } catch {
    return notFound();
  }
  if (size > MAX_BYTES) {
    return NextResponse.json({ error: "This file is larger than 50 MB and can't be served here." }, { status: 413 });
  }

  const ext = path.extname(file).toLowerCase();
  const inline = INLINE[ext];
  const body = Readable.toWeb(createReadStream(file)) as ReadableStream<Uint8Array>;
  return new Response(body, {
    headers: {
      "Content-Length": String(size),
      "Content-Type": inline ?? "application/octet-stream",
      "Content-Disposition": `${inline ? "inline" : "attachment"}; filename="${path.basename(file).replace(/"/g, "")}"`,
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "sandbox; default-src 'none'",
      "Cache-Control": "private, max-age=300",
    },
  });
}
