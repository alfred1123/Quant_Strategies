import axios from 'axios';
import type { AxiosError } from 'axios';
import { queryClient } from '../lib/queryClient';
import { ME_QUERY_KEY } from './auth';

export const apiClient = axios.create({
  baseURL: '/api/v1',
  // Required so the browser sends/stores the HttpOnly `qs_token` cookie
  // set by POST /auth/login. Combined with the dev Vite proxy in vite.config.ts,
  // requests look same-origin and the cookie travels both ways.
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Error thrown by the response interceptor below. Carries the HTTP status
 * (when one was returned) so callers can branch on `err instanceof ApiError
 * && err.status === 401` rather than matching the message string.
 */
export class ApiError extends Error {
  readonly status: number | null;
  constructor(message: string, status: number | null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// Normalise all API errors: extract FastAPI detail message, log to console.
// On 401 (anywhere except the /auth/me probe itself), evict the cached
// current-user so the App-level route guard re-renders the login page.
apiClient.interceptors.response.use(
  response => response,
  (err: AxiosError<{ detail?: string | { msg: string }[] }>) => {
    const detail = err.response?.data?.detail;
    const message =
      Array.isArray(detail)
        ? detail.map(d => d.msg).join('; ')
        : (detail ?? err.message ?? 'Unknown error');
    const status = err.response?.status ?? null;
    console.error('[API]', err.config?.method?.toUpperCase(), err.config?.url, '→', message, err);

    if (status === 401) {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      // Push the browser to /login so a mid-session 401 doesn't leave the
      // user staring at a broken page. This runs outside React so we use
      // the History API directly.
      if (window.location.pathname !== '/login') {
        window.location.replace('/login');
      }
    }
    return Promise.reject(new ApiError(message, status));
  },
);
