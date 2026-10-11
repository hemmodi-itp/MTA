import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

/*
 * Loading layouts shaped like the content they stand in for, so swapping them for real data moves nothing that was
 * already on screen (no layout shift). Each is announced once to screen readers as "Loading…".
 */

function Loading({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-live="polite" className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** A card-shaped block with the same radius and border as a real card. */
export function CardSkeleton({ className, children }: { className?: string; children?: React.ReactNode }) {
  return (
    <div aria-hidden className={cn("rounded-2xl border border-border bg-card/60 p-5", className)}>
      {children ?? (
        <div className="space-y-3">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      )}
    </div>
  );
}

export function KpiRowSkeleton({ count = 4, dense = false, className }: { count?: number; dense?: boolean; className?: string }) {
  return (
    <div aria-hidden className={className}>
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} className={dense ? "p-4" : undefined}>
          <Skeleton className={cn("h-3", dense ? "mb-5 w-20" : "w-24")} />
          <Skeleton className={cn("mt-3", dense ? "h-7 w-14" : "h-9 w-24")} />
          <Skeleton className="mt-2.5 h-3 w-32 max-w-full" />
        </CardSkeleton>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6, label = "Loading…", className }: { rows?: number; label?: string; className?: string }) {
  return (
    <Loading label={label} className={cn("overflow-hidden rounded-2xl border border-border bg-card/60", className)}>
      <div className="border-b border-border px-5 py-3"><Skeleton className="h-3 w-40" /></div>
      <div className="divide-y divide-border/60">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-5 py-3.5">
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-3.5 w-40 max-w-full" />
              <Skeleton className="h-3 w-20" />
            </div>
            <Skeleton className="hidden h-5 w-20 rounded-full sm:block" />
            <Skeleton className="hidden h-2 w-40 rounded-full md:block" />
            <Skeleton className="h-3 w-12" />
          </div>
        ))}
      </div>
    </Loading>
  );
}

export function CardGridSkeleton({ count = 6, label = "Loading…", className }: { count?: number; label?: string; className?: string }) {
  return (
    <Loading label={label} className={className}>
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} className="h-[136px]">
          <div className="flex items-center justify-between gap-3">
            <Skeleton className="h-4 w-40 max-w-[60%]" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <Skeleton className="mt-3 h-3 w-28" />
          <div className="mt-6 flex items-center justify-between">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-10" />
          </div>
        </CardSkeleton>
      ))}
    </Loading>
  );
}

/** Body of a run while its steps, artifacts and tests load (the header is rendered by the page). */
export function RunBodySkeleton() {
  return (
    <Loading label="Loading the run…" className="space-y-6">
      <CardSkeleton className="h-40" />
      <KpiRowSkeleton count={6} dense className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6" />
      <CardSkeleton>
        <Skeleton className="h-4 w-24" />
        <div className="mt-5 space-y-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex gap-3">
              <Skeleton className="size-6 shrink-0 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3.5 w-48 max-w-full" />
                <Skeleton className="h-3 w-72 max-w-full" />
              </div>
            </div>
          ))}
        </div>
      </CardSkeleton>
    </Loading>
  );
}
