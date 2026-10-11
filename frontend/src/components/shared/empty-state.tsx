import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  /** One clear next step: a link (`actionHref`) or a button (`onAction`). */
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
  /** "page" for a whole empty page or list, "inline" inside a card or tab. */
  size?: "page" | "inline";
  className?: string;
}

/** Nothing to show yet: what this place is for, and what to do next. Static on purpose — no looping animation. */
export function EmptyState({ icon: Icon, title, description, actionLabel, actionHref, onAction, size = "page", className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 text-center",
        size === "page" ? "rounded-2xl border border-dashed border-border px-6 py-14" : "px-4 py-8",
        className
      )}
    >
      <div className={cn("flex items-center justify-center rounded-xl bg-muted text-muted-foreground", size === "page" ? "size-11" : "size-9")}>
        <Icon aria-hidden className={size === "page" ? "size-5" : "size-4"} />
      </div>
      <div className="space-y-1">
        <p className="font-medium text-balance">{title}</p>
        {description && <p className="max-w-sm text-sm text-pretty text-muted-foreground">{description}</p>}
      </div>
      {actionLabel && actionHref && (
        <Button asChild size="sm" className="mt-1">
          <Link href={actionHref}>{actionLabel}</Link>
        </Button>
      )}
      {actionLabel && !actionHref && onAction && (
        <Button size="sm" onClick={onAction} className="mt-1">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
