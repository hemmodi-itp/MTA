import { FileBarChart2, FlaskConical, FolderGit2, LayoutDashboard, PlayCircle, Settings, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  hint: string;          // tooltip / palette description
  shortcut?: string;     // g + key
}

export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, hint: "Portfolio health, risks and AI insights", shortcut: "D" },
  { href: "/projects", label: "Projects", icon: FolderGit2, hint: "Every repository you evaluate", shortcut: "P" },
  { href: "/runs", label: "Runs", icon: PlayCircle, hint: "Evaluation history and live runs", shortcut: "R" },
  { href: "/test-cases", label: "Test cases", icon: FlaskConical, hint: "BRD-traced tests and their verdicts", shortcut: "T" },
  { href: "/reports", label: "Reports", icon: FileBarChart2, hint: "Final evaluation reports", shortcut: "E" },
];

export const SETTINGS_NAV: NavItem = { href: "/settings", label: "Settings", icon: Settings, hint: "Workspace and account" };

export function titleFor(pathname: string): string {
  if (pathname.startsWith("/runs/")) return "Run";
  if (pathname.startsWith("/projects/new")) return "New evaluation";
  if (pathname.startsWith("/projects/")) return "Project";
  if (pathname.startsWith("/reports/")) return "Report";
  if (pathname.startsWith("/test-cases/")) return "Test case";
  return [...NAV, SETTINGS_NAV].find((n) => pathname.startsWith(n.href))?.label ?? "MTA";
}
