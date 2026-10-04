import { prisma } from "@/lib/db";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";

type StoredReport = { data: Record<string, unknown>; markdown: string; html: string };

/**
 * The run's Final Evaluation Report (engines/report/final.py), stored in Run.finalReport.
 *   ?format=html (default)  the printable page, inline but sandboxed: no scripts, links open in a new tab
 *   ?format=md | json       downloads
 */
export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId } = await params;
  const run = await prisma.run.findFirst({
    where: { id: runId, ...visibleRuns(user.id) },
    select: { id: true, finalReport: true, project: { select: { name: true } } },
  });
  const report = run?.finalReport as unknown as StoredReport | null;
  if (!run || !report) return notFound();

  const format = new URL(request.url).searchParams.get("format") ?? "html";
  const base = `mta-report-${(run.project?.name ?? "run").replace(/[^A-Za-z0-9_-]+/g, "-").slice(0, 60)}-${run.id.slice(0, 8)}`;
  if (format === "md") {
    return new Response(report.markdown, {
      headers: { "Content-Type": "text/markdown; charset=utf-8", "Content-Disposition": `attachment; filename="${base}.md"` },
    });
  }
  if (format === "json") {
    return new Response(JSON.stringify(report.data, null, 2), {
      headers: { "Content-Type": "application/json; charset=utf-8", "Content-Disposition": `attachment; filename="${base}.json"` },
    });
  }
  // our own generated HTML (all content escaped server-side); sandboxed anyway so nothing in it can script
  const page = report.html.replace("<head>", "<head><base target=\"_blank\">");
  return new Response(page, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; " +
        "sandbox allow-popups allow-popups-to-escape-sandbox allow-modals",
      "X-Content-Type-Options": "nosniff",
      "Cache-Control": "private, no-store",
    },
  });
}
