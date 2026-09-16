import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { licensesApi } from "../api";

export const LICENSE_KEYS = {
  all: ["licenses"],
  list: (filters) => ["licenses", "list", filters],
  detail: (id) => ["licenses", "detail", id],
};

export function useLicenses(filters = {}) {
  return useQuery({
    queryKey: LICENSE_KEYS.list(filters),
    queryFn: () => licensesApi.list(filters),
    staleTime: 60_000,
  });
}

export function useLicense(id) {
  return useQuery({
    queryKey: LICENSE_KEYS.detail(id),
    queryFn: () => licensesApi.get(id),
    enabled: !!id,
  });
}

export function useCreateLicense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: licensesApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: LICENSE_KEYS.all }),
  });
}

export function useUpdateLicense() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => licensesApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: LICENSE_KEYS.all });
      qc.invalidateQueries({ queryKey: LICENSE_KEYS.detail(id) });
    },
  });
}
