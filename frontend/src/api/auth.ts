import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError, apiClient } from './client';
import { queryClient } from '../lib/queryClient';

export const ME_QUERY_KEY = ['auth', 'me'] as const;

export interface CurrentUser {
  username: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

/** GET /api/v1/auth/me — returns null when unauthenticated (401 swallowed). */
async function fetchMe(): Promise<CurrentUser | null> {
  try {
    const { data } = await apiClient.get<CurrentUser>('/auth/me');
    return data;
  } catch (err) {
    // Swallow 401 specifically (= "show login page"). Anything else is real.
    // The 401 interceptor in client.ts has already evicted the cache.
    if (err instanceof ApiError && err.status === 401) return null;
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
