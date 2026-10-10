import { FileBarChart2, FolderGit2, LayoutDashboard, PlayCircle, Settings, type LucideIcon } from "lucide-react";

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
  { href: "/reports", label: "Reports", icon: FileBarChart2, hint: "Final evaluation reports", shortcut: "E" },
];

export const SETTINGS_NAV: NavItem = { href: "/settings", label: "Settings", icon: Settings, hint: "Workspace and account" };
