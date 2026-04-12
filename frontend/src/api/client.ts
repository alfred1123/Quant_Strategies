import axios from 'axios';
import type { AxiosError } from 'axios';

export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

// Normalise all API errors: extract FastAPI detail message, log to console.
apiClient.interceptors.response.use(
  response => response,
  (err: AxiosError<{ detail?: string | { msg: string }[] }>) => {
    const detail = err.response?.data?.detail;
    const message =
      Array.isArray(detail)
        ? detail.map(d => d.msg).join('; ')
        : (detail ?? err.message ?? 'Unknown error');
    console.error('[API]', err.config?.method?.toUpperCase(), err.config?.url, '→', message, err);
    return Promise.reject(new Error(message));
  },
);
