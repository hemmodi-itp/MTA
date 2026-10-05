import { prisma } from "@/lib/db";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";
import { BACKEND_URL, backendHeaders } from "@/lib/api/server/evaluation";

type StoredReport = { data: Record<string, unknown>; markdown: string; html: string };

/**
 * The run's Final Evaluation Report (engines/report/final.py), stored in Run.finalReport.
 *   ?format=html (default)  the printable page, inline but sandboxed: no scripts, links open in a new tab
 *   ?format=md | json | pdf downloads (the PDF is rendered by the evaluation service)
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
  if (format === "pdf") {
    // rendered by the evaluation service (Chromium); the access check above is the only gate
    let res: Response;
    try {
      res = await fetch(`${BACKEND_URL}/runs/${run.id}/report.pdf`, {
        headers: backendHeaders(), cache: "no-store", signal: AbortSignal.timeout(90_000),
      });
    } catch {
      return Response.json({ error: "The MTA evaluation service is not reachable, so the PDF can't be made right now." }, { status: 503 });
    }
    if (!res.ok || !res.body) {
      return Response.json({ error: "The PDF could not be generated. Try again, or open the report and print it." }, { status: 502 });
    }
    return new Response(res.body, {
      headers: { "Content-Type": "application/pdf", "Content-Disposition": `attachment; filename="${base}.pdf"`, "Cache-Control": "private, no-store" },
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
