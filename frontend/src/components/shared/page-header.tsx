import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export interface Crumb {
  label: string;
  href?: string;
}

/**
 * The one page header: optional breadcrumb, title (+ adornment such as a status pill), description, meta row, and the
 * page's actions on the right (below the title on phones). Always left-aligned at the content edge.
 */
export function PageHeader({
  title,
  description,
  actions,
  breadcrumb,
  meta,
  adornment,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  breadcrumb?: Crumb[];
  meta?: React.ReactNode;
  adornment?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between", className)}>
      <div className="min-w-0 space-y-1.5">
        {breadcrumb && breadcrumb.length > 0 && (
          <nav aria-label="Breadcrumb">
            <ol className="flex flex-wrap items-center gap-1 text-xs font-medium text-muted-foreground">
              {breadcrumb.map((c, i) => (
                <li key={`${c.label}-${i}`} className="flex items-center gap-1">
                  {c.href ? (
                    <Link href={c.href} className="rounded-sm transition-colors hover:text-foreground">{c.label}</Link>
                  ) : (
                    <span aria-current="page">{c.label}</span>
                  )}
                  {i < breadcrumb.length - 1 && <ChevronRight aria-hidden className="size-3" />}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h1 className="min-w-0 type-page-title break-words">{title}</h1>
          {adornment}
        </div>
        {description && <p className="max-w-2xl text-sm text-pretty text-muted-foreground">{description}</p>}
        {meta && <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 pt-0.5 text-sm text-muted-foreground">{meta}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Same footprint as a PageHeader with a one-line title and description (swap without a jump). */
export function PageHeaderSkeleton({ meta = false, actions = false }: { meta?: boolean; actions?: boolean }) {
  return (
    <div aria-hidden className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-1.5">
        <Skeleton className="h-7 w-56 max-w-full" />
        <Skeleton className="h-5 w-80 max-w-full" />
        {meta && <Skeleton className="mt-2 h-5 w-64 max-w-full" />}
      </div>
      {actions && <Skeleton className="h-9 w-36" />}
    </div>
  );
}
