"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProjects, fetchProject, createProject, deleteLiveAuth, rerunProject, type CreateProjectInput } from "@/lib/api/projects";
import {
  cancelRun,
  fetchActivity,
  fetchRun,
  fetchRunArtifacts,
  fetchRunLogs,
  fetchRunProgress,
  fetchRuns,
  LogCursorError,
} from "@/lib/api/runs";
import { fetchTestCases, fetchTestCasePage, fetchTestCase, fetchScenarios, fetchRecommendations } from "@/lib/api/test-cases";
import { isActiveStatus } from "@/lib/run-status";
import type { RunLogs, RunStatus } from "@/lib/types";

export { isActiveStatus };

/** Run detail + pipeline progress while the run is in flight; nothing once it has finished. */
const RUN_POLL_MS = 4000;
/** The shared run list, only while some visible run is active. */
const RUNS_POLL_MS = 15_000;

const pollWhileActive = (status?: RunStatus) => (isActiveStatus(status) ? RUN_POLL_MS : false);

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: fetchProjects });
}

export function useProject(id: string) {
  return useQuery({ queryKey: ["projects", id], queryFn: () => fetchProject(id), enabled: !!id });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateProjectInput) => createProject(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useRerunProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => rerunProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useDeleteLiveAuth() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => deleteLiveAuth(projectId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useCancelRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => cancelRun(runId),
    onSuccess: (_res, runId) => {
      queryClient.invalidateQueries({ queryKey: ["runs", runId] });
      queryClient.invalidateQueries({ queryKey: ["runs"], exact: true });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

const RUNS_QUERY = { queryKey: ["runs"], queryFn: () => fetchRuns() } as const;

/**
 * The run list, read by the sidebar, top bar, notifications, ⌘K, Copilot and the pages. Every caller shares one cached
 * query and none of them polls: <RunsPoller/> (mounted once in the app shell) is its only timer, so N components
 * mean one request per interval, not N. Refreshed on window focus too.
 */
export function useRuns() {
  return useQuery({ ...RUNS_QUERY, refetchOnWindowFocus: true });
}

/** The single poller behind useRuns: every 15 s while any visible run is queued or running, otherwise idle. */
export function useRunsPoller() {
  useQuery({
    ...RUNS_QUERY,
    refetchOnWindowFocus: true,
    refetchInterval: (q) => (q.state.data?.some((r) => isActiveStatus(r.status)) ? RUNS_POLL_MS : false),
    refetchIntervalInBackground: false,
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: ["runs", id],
    queryFn: () => fetchRun(id),
    enabled: !!id,
    refetchInterval: (q) => pollWhileActive(q.state.data?.status),
  });
}

/** Steps + activity log. Pass the run's status so polling stops when it finishes. */
export function useRunProgress(id: string, status?: RunStatus) {
  return useQuery({
    queryKey: ["runs", id, "progress"],
    queryFn: () => fetchRunProgress(id),
    enabled: !!id,
    refetchInterval: pollWhileActive(status),
  });
}

/** Newest pipeline events across your runs (dashboard timeline); live every 8 s. */
export function useActivity() {
  return useQuery({ queryKey: ["activity"], queryFn: fetchActivity, refetchInterval: 8000 });
}

/**
 * The run log (Logs tab). The first fetch loads the whole log; every later fetch asks only for the lines after the
 * newest one held (`?after=<event id>`) and appends them, so a long run's log is never re-downloaded every 3 s.
 */
export function useRunLogs(id: string, status?: RunStatus) {
  const queryClient = useQueryClient();
  const key = ["runs", id, "logs"];
  return useQuery({
    queryKey: key,
    queryFn: async (): Promise<RunLogs> => {
      const prev = queryClient.getQueryData<RunLogs>(key);
      const last = prev?.events[prev.events.length - 1];
      if (!prev || !last) return fetchRunLogs(id);
      try {
        const next = await fetchRunLogs(id, last.id);
        const seen = new Set(prev.events.map((e) => e.id));
        return { ...next, events: [...prev.events, ...next.events.filter((e) => !seen.has(e.id))] };
      } catch (err) {
        if (err instanceof LogCursorError) return fetchRunLogs(id); // log was rewritten: start over
        throw err;
      }
    },
    enabled: !!id,
    refetchInterval: isActiveStatus(status) ? 3000 : false,
  });
}

/** Run artifacts (BRD, requirements, live-app evidence): every 10 s while the run is producing them, then never. */
export function useRunArtifacts(id: string, status?: RunStatus) {
  return useQuery({
    queryKey: ["runs", id, "artifacts"],
    queryFn: () => fetchRunArtifacts(id),
    enabled: !!id,
    refetchInterval: isActiveStatus(status) ? 10_000 : false,
  });
}

/** One run's tests, refreshed while the run executes them. */
export function useTestCases(runId: string, status?: RunStatus) {
  return useQuery({
    queryKey: ["test-cases", runId],
    queryFn: () => fetchTestCases(runId),
    enabled: !!runId,
    refetchInterval: isActiveStatus(status) ? 5000 : false,
  });
}

/** Every visible test case, 200 at a time (Test cases page). */
export function useAllTestCases() {
  return useInfiniteQuery({
    queryKey: ["test-cases", "all"],
    queryFn: ({ pageParam }) => fetchTestCasePage(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}

export function useTestCase(id: string) {
  return useQuery({ queryKey: ["test-cases", "detail", id], queryFn: () => fetchTestCase(id), enabled: !!id });
}

export function useScenarios(runId?: string) {
  return useQuery({ queryKey: ["scenarios", runId ?? "all"], queryFn: () => fetchScenarios(runId) });
}

export function useRecommendations(runId?: string, status?: RunStatus) {
  return useQuery({
    queryKey: ["recommendations", runId ?? "all"],
    queryFn: () => fetchRecommendations(runId),
    refetchInterval: runId && isActiveStatus(status) ? 10_000 : false,
  });
}
