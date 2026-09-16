import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { authApi, ApiError } from "../api";

const TOKEN_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

function saveTokens(access, refresh) {
  localStorage.setItem(TOKEN_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function useAuth() {
  const qc = useQueryClient();
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => !!localStorage.getItem(TOKEN_KEY)
  );

  // Fetch current user (only when token is present)
  const {
    data: user,
    isLoading: userLoading,
    error: userError,
  } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: authApi.me,
    enabled: isAuthenticated,
    retry: false,
    staleTime: 5 * 60_000,
  });

  // If the /me call returns 401, clear tokens and sign out
  useEffect(() => {
    if (userError instanceof ApiError && userError.status === 401) {
      clearTokens();
      setIsAuthenticated(false);
      qc.clear();
    }
  }, [userError, qc]);

  const loginMutation = useMutation({
    mutationFn: ({ email, password }) => authApi.login(email, password),
    onSuccess: (data) => {
      saveTokens(data.access_token, data.refresh_token);
      setIsAuthenticated(true);
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });

  const logout = useCallback(() => {
    clearTokens();
    setIsAuthenticated(false);
    qc.clear();
  }, [qc]);

  return {
    user,
    isAuthenticated,
    userLoading,
    login: loginMutation.mutate,
    loginLoading: loginMutation.isPending,
    loginError: loginMutation.error,
    logout,
  };
}
