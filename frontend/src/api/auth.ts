import { useMutation, useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { ApiError, apiClient } from './client';
import { queryClient } from '../lib/queryClient';

export const ME_QUERY_KEY = ['auth', 'me'] as const;

export interface CurrentUser {
  username: string;
  app_user_id: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

/** GET /api/v1/auth/me — returns null when unauthenticated or the probe cannot complete. */
async function fetchMe(): Promise<CurrentUser | null> {
  try {
    const { data } = await apiClient.get<CurrentUser>('/auth/me', {
      // Avoid an infinite shell spinner when the API or DB hangs (see App.tsx GuestOnly).
      timeout: 15_000,
    });
    return data;
  } catch (err) {
    // The 401 interceptor in client.ts has already evicted the cache.
    if (err instanceof ApiError && err.status === 401) return null;
    if (axios.isAxiosError(err)) {
      const noResponse = err.response === undefined;
      const timedOut = err.code === 'ECONNABORTED';
      if (timedOut || noResponse) return null;
    }
    throw err;
  }
}

/** Hook used by the route guard in App.tsx. */
export const useMe = () =>
  useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    staleTime: 60_000,
    retry: false,
  });

/** POST /api/v1/auth/login */
export const useLogin = () =>
  useMutation({
    mutationFn: async (body: LoginRequest): Promise<CurrentUser> => {
      const { data } = await apiClient.post<CurrentUser>('/auth/login', body);
      return data;
    },
    onSuccess: data => {
      // Flush stale per-user data from any previous session (e.g. expired
      // cookie followed by a different user logging in on the same browser).
      queryClient.clear();
      queryClient.setQueryData(ME_QUERY_KEY, data);
    },
  });

/** POST /api/v1/auth/logout */
export const useLogout = () =>
  useMutation({
    mutationFn: async () => {
      await apiClient.post('/auth/logout');
    },
    onSettled: () => {
      // Whether the call succeeded or failed (e.g. cookie already expired),
      // clear the entire client cache so no stale per-user data leaks.
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.clear();
    },
  });
