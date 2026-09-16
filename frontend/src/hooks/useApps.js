import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { appsApi } from "../api";

export const APP_KEYS = {
  all: ["apps"],
  list: (filters) => ["apps", "list", filters],
  detail: (id) => ["apps", "detail", id],
};

/**
 * Fetch paginated/filtered app list.
 * @param {{ status?, category?, shadow_it?, department?, search?, skip?, limit? }} filters
 */
export function useApps(filters = {}) {
  return useQuery({
    queryKey: APP_KEYS.list(filters),
    queryFn: () => appsApi.list(filters),
    staleTime: 60_000, // 1 min
  });
}

export function useApp(id) {
  return useQuery({
    queryKey: APP_KEYS.detail(id),
    queryFn: () => appsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: appsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: APP_KEYS.all }),
  });
}

export function useUpdateApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => appsApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: APP_KEYS.all });
      qc.invalidateQueries({ queryKey: APP_KEYS.detail(id) });
    },
  });
}

export function useDeleteApp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: appsApi.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: APP_KEYS.all }),
  });
}
