import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { contractsApi } from "../api";

export const CONTRACT_KEYS = {
  all: ["contracts"],
  list: (filters) => ["contracts", "list", filters],
  detail: (id) => ["contracts", "detail", id],
};

export function useContracts(filters = {}) {
  return useQuery({
    queryKey: CONTRACT_KEYS.list(filters),
    queryFn: () => contractsApi.list(filters),
    staleTime: 60_000,
  });
}

/** Convenience: contracts expiring within N days */
export function useExpiringContracts(days = 90) {
  return useContracts({ expiring_within_days: days });
}

export function useContract(id) {
  return useQuery({
    queryKey: CONTRACT_KEYS.detail(id),
    queryFn: () => contractsApi.get(id),
    enabled: !!id,
  });
}

export function useCreateContract() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: contractsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: CONTRACT_KEYS.all }),
  });
}

export function useUpdateContract() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }) => contractsApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: CONTRACT_KEYS.all });
      qc.invalidateQueries({ queryKey: CONTRACT_KEYS.detail(id) });
    },
  });
}

export function useUploadContractFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ contractId, file }) => contractsApi.uploadFile(contractId, file),
    onSuccess: (_, { contractId }) => {
      qc.invalidateQueries({ queryKey: CONTRACT_KEYS.detail(contractId) });
      qc.invalidateQueries({ queryKey: CONTRACT_KEYS.all });
    },
  });
}
