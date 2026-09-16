import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { syncApi, dashboardApi } from "../api";

// ── Dashboard ──────────────────────────────────────────────────────────────
export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.getStats,
    staleTime: 30_000,      // 30s — stats refresh often
    refetchInterval: 60_000, // auto-refresh every 60s
  });
}

// ── Sync jobs ──────────────────────────────────────────────────────────────
export const SYNC_KEYS = {
  all: ["sync"],
  jobs: (filters) => ["sync", "jobs", filters],
};

export function useSyncJobs(params = {}) {
  return useQuery({
    queryKey: SYNC_KEYS.jobs(params),
    queryFn: () => syncApi.listJobs(params),
    staleTime: 15_000,
    refetchInterval: 30_000, // poll for in-progress jobs
  });
}

export function useTriggerOktaSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: syncApi.triggerOkta,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNC_KEYS.all });
      // Also invalidate apps — new apps may appear after sync
      qc.invalidateQueries({ queryKey: ["apps"] });
    },
  });
}

export function useTriggerAzureSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: syncApi.triggerAzureAD,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNC_KEYS.all });
      qc.invalidateQueries({ queryKey: ["apps"] });
    },
  });
}

// ── CSV import ─────────────────────────────────────────────────────────────
export function useImportCsv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, importType }) => syncApi.importCsv(file, importType),
    onSuccess: (_, { importType }) => {
      // Invalidate the relevant entity list after import
      if (importType === "apps") qc.invalidateQueries({ queryKey: ["apps"] });
      if (importType === "licenses") qc.invalidateQueries({ queryKey: ["licenses"] });
      if (importType === "contracts") qc.invalidateQueries({ queryKey: ["contracts"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
