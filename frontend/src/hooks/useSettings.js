import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "../api";

export const SETTINGS_KEYS = {
  all: ["settings"],
  okta: ["settings", "okta"],
  azure: ["settings", "azure-ad"],
};

export function useOktaSettings() {
  return useQuery({
    queryKey: SETTINGS_KEYS.okta,
    queryFn: settingsApi.getOkta,
    staleTime: 30_000,
  });
}

export function useAzureSettings() {
  return useQuery({
    queryKey: SETTINGS_KEYS.azure,
    queryFn: settingsApi.getAzure,
    staleTime: 30_000,
  });
}

export function useSaveOkta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.saveOkta,
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.okta }),
  });
}

export function useSaveAzure() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.saveAzure,
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.azure }),
  });
}

export function useTestOkta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.testOkta,
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.okta }),
  });
}

export function useTestAzure() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.testAzure,
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.azure }),
  });
}

export function useToggleOkta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ enabled }) => enabled ? settingsApi.enableOkta() : settingsApi.disableOkta(),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.okta }),
  });
}

export function useToggleAzure() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ enabled }) => enabled ? settingsApi.enableAzure() : settingsApi.disableAzure(),
    onSuccess: () => qc.invalidateQueries({ queryKey: SETTINGS_KEYS.azure }),
  });
}
