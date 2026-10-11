import { AlertTriangle, ChevronDown, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  title?: string;
  message?: React.ReactNode;
  /** Raw technical text (an exception, a server message): kept out of the way in a collapsible block. */
  details?: string | null;
  onRetry?: () => void;
  className?: string;
}

/** Something failed: a plain-language title and message first, the raw details on request, and a retry. */
export function ErrorState({
  title = "Something went wrong",
  message = "Couldn't load this data. Check your connection and try again.",
  details,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div role="alert" className={cn("rounded-2xl border tone-critical tone-border bg-card/80 p-5", className)}>
      <div className="flex gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg tone-tint tone-text">
          <AlertTriangle aria-hidden className="size-4" />
        </span>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium tone-text">{title}</p>
          {message && <div className="text-sm text-pretty text-muted-foreground">{message}</div>}
          {details && (
            <details className="group pt-1">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm text-xs font-medium text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
                <ChevronDown aria-hidden className="size-3.5 transition-transform duration-(--dur-micro) ease-enter group-open:rotate-180" />
                Technical details
              </summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-lg border border-border bg-muted/50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-foreground">
                {details}
              </pre>
            </details>
          )}
          {onRetry && (
            <Button size="sm" variant="outline" className="mt-2 gap-1.5" onClick={onRetry}>
              <RotateCw aria-hidden className="size-3.5" /> Retry
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
