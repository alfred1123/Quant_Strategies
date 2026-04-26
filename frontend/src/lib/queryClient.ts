import { QueryClient } from '@tanstack/react-query';

/**
 * Shared TanStack Query client.
 *
 * Defined here (rather than inline in main.tsx) so non-React modules — most
 * importantly the axios 401 response interceptor — can call
 * `queryClient.setQueryData(['auth', 'me'], null)` when a request comes back
 * 401. This is what redirects the SPA to the login screen mid-session
 * (login.md §9.4).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: Infinity },
  },
});
