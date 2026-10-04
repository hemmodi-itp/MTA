"use client";

import Link from "next/link";
import { Plus, FolderGit2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { StatusPill } from "@/components/shared/status-pill";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/lib/query/hooks";

export default function ProjectsPage() {
  const { data, isLoading, isError, refetch } = useProjects();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Projects</h1>
          <p className="text-sm text-muted-foreground">Your agents, plus sample projects to explore.</p>
        </div>
        <Button asChild className="gap-1.5">
          <Link href="/projects/new">
            <Plus className="size-4" />
            New Project
          </Link>
        </Button>
      </div>

      {isError ? (
        <ErrorState onRetry={refetch} />
      ) : isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      ) : !data?.length ? (
        <EmptyState
          icon={FolderGit2}
          title="No projects yet"
          description="Connect a repository to run your first evaluation."
          actionLabel="Connect Repository"
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((p) => (
            <Link key={p.id} href={`/projects/${p.id}`}>
              <Card className="h-full transition-colors hover:bg-muted/40">
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-medium">{p.name}</span>
                      {p.isSample && <Badge variant="secondary" className="shrink-0 font-normal">Sample</Badge>}
                    </p>
                    <StatusPill status={p.lastRunStatus} />
                  </div>
                  <p className="truncate text-xs text-muted-foreground">{p.githubUrl}</p>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Quality score</span>
                    <span className="font-mono font-semibold tabular-nums">
                      {p.lastQualityScore ?? "—"}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
