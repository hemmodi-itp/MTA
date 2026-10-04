import { create } from "zustand";
import { persist } from "zustand/middleware";

export type TestCaseStatusFilter = "all" | "passed" | "failed" | "inconclusive" | "not_executed" | "pending" | "healed" | "skipped";
/** Which projects the dashboard looks at: your own, the shared samples, or both. */
export type WorkspaceScope = "all" | "mine" | "samples";

interface UIState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
  testCaseStatusFilter: TestCaseStatusFilter;
  setTestCaseStatusFilter: (filter: TestCaseStatusFilter) => void;
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
  copilotOpen: boolean;
  setCopilotOpen: (open: boolean) => void;
  copilotPrompt: string | null;           // a question queued for the Copilot (e.g. from ⌘K)
  askCopilot: (prompt: string) => void;
  clearCopilotPrompt: () => void;
  workspace: WorkspaceScope;
  setWorkspace: (scope: WorkspaceScope) => void;
  notificationsSeenAt: string | null;     // ISO; notifications newer than this are "unread"
  markNotificationsSeen: () => void;
}

// Pure client/UI state only — nothing here is server-derived. Server data always
// goes through TanStack Query (see lib/query/hooks.ts), never through this store.
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      mobileNavOpen: false,
      setMobileNavOpen: (open) => set({ mobileNavOpen: open }),
      testCaseStatusFilter: "all",
      setTestCaseStatusFilter: (filter) => set({ testCaseStatusFilter: filter }),
      commandPaletteOpen: false,
      setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
      copilotOpen: false,
      setCopilotOpen: (open) => set({ copilotOpen: open }),
      copilotPrompt: null,
      askCopilot: (prompt) => set({ copilotOpen: true, copilotPrompt: prompt }),
      clearCopilotPrompt: () => set({ copilotPrompt: null }),
      workspace: "all",
      setWorkspace: (scope) => set({ workspace: scope }),
      notificationsSeenAt: null,
      markNotificationsSeen: () => set({ notificationsSeenAt: new Date().toISOString() }),
    }),
    {
      name: "aqp-ui",
      // only preferences persist; transient UI (open panels) starts closed on every load
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, workspace: s.workspace, notificationsSeenAt: s.notificationsSeenAt }),
    }
  )
);
