import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon?: LucideIcon;
  tone?: "default" | "good" | "warn" | "bad";
}

const TONE_CLASS: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  default: "text-foreground",
  good: "text-success",
  warn: "text-warning-foreground dark:text-warning",
  bad: "text-critical",
};

export function KpiCard({ label, value, sub, icon: Icon, tone = "default" }: KpiCardProps) {
  return (
    <Card className="gap-2 py-4">
      <CardContent className="flex items-start justify-between px-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className={cn("mt-1 font-mono text-2xl font-semibold tabular-nums", TONE_CLASS[tone])}>{value}</p>
          {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
        </div>
        {Icon && <Icon className="size-4 text-muted-foreground" />}
      </CardContent>
    </Card>
  );
}
