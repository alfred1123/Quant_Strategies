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
    console.error('[API]', err.config?.method?.toUpperCase(), err.config?.url, '→', message, err);

    if (err.response?.status === 401) {
      queryClient.setQueryData(ME_QUERY_KEY, null);
    }
    return Promise.reject(new Error(message));
  },
);
