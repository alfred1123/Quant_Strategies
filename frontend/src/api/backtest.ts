import { apiClient } from './client';
import type {
  OptimizeRequest, OptimizeResponse, OptimizeProgress,
  PerformanceRequest, PerformanceResponse,
  WalkForwardRequest, WalkForwardResponse,
} from '../types/backtest';

export async function runOptimize(req: OptimizeRequest): Promise<OptimizeResponse> {
  const { data } = await apiClient.post<OptimizeResponse>('/backtest/optimize', req);
  return data;
}

// ─── SSE payload validation ─────────────────────────────────────────────
// Hand-written shape checks (deliberately no Zod dep). Each parser narrows
// `unknown` JSON into the typed shape we expect, or returns null so the
// caller can reject with a precise error rather than crashing on `as`.

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null;
}

function parseProgress(x: unknown): OptimizeProgress | null {
  if (!isObj(x)) return null;
  const trial = typeof x.trial === 'number' ? x.trial : null;
  const total = typeof x.total === 'number' ? x.total : null;
  if (trial === null || total === null) return null;
  const best_sharpe =
    typeof x.best_sharpe === 'number' ? x.best_sharpe :
    x.best_sharpe === null ? null :
    null;
  return { trial, total, best_sharpe };
}

/** `init` events use `{ total }` only — surface as a progress with trial=0. */
function parseInit(x: unknown): OptimizeProgress | null {
  if (!isObj(x)) return null;
  const total = typeof x.total === 'number' ? x.total : null;
  if (total === null) return null;
  return { trial: 0, total, best_sharpe: null };
}

function parseResult(x: unknown): OptimizeResponse | null {
  if (!isObj(x)) return null;
  if (typeof x.total_trials !== 'number') return null;
  if (typeof x.valid !== 'number') return null;
  if (!isObj(x.best)) return null;
  if (!Array.isArray(x.top10)) return null;
  if (!Array.isArray(x.grid)) return null;
  return x as unknown as OptimizeResponse;
}

function parseError(x: unknown): string {
  if (isObj(x) && typeof x.detail === 'string') return x.detail;
  return 'Optimization failed';
}

/**
 * Stream optimization via SSE. Calls onProgress per trial and resolves with
 * the final OptimizeResponse. Cancellation: pass an AbortSignal — aborting
 * tears down the underlying fetch and rejects with an `AbortError`.
 *
 * Errors from the server are surfaced as `Error(detail)`. Malformed payloads
 * reject explicitly rather than crash the chunk loop.
 */
export function runOptimizeStream(
  req: OptimizeRequest,
  onProgress: (p: OptimizeProgress) => void,
  signal?: AbortSignal,
): Promise<OptimizeResponse> {
  return new Promise((resolve, reject) => {
    const baseUrl = apiClient.defaults.baseURL ?? '/api/v1';
    fetch(`${baseUrl}/backtest/optimize/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    })
      .then((response) => {
        if (!response.ok) {
          return response.json().then(
            (body) => reject(new Error(body?.detail ?? `HTTP ${response.status}`)),
            () => reject(new Error(`HTTP ${response.status}`)),
          );
        }
        if (!response.body) {
          reject(new Error('Stream response has no body'));
          return;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let settled = false;

        const settleReject = (err: Error) => {
          if (settled) return;
          settled = true;
          reader.cancel().catch(() => { /* ignore */ });
          reject(err);
        };
        const settleResolve = (v: OptimizeResponse) => {
          if (settled) return;
          settled = true;
          reader.cancel().catch(() => { /* ignore */ });
          resolve(v);
        };

        function processChunk() {
          reader.read().then(({ done, value }) => {
            if (settled) return;
            if (done) {
              settleReject(new Error('Stream ended without result'));
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() ?? '';

            for (const part of parts) {
              let eventType = '';
              let eventData = '';
              for (const line of part.split('\n')) {
                if (line.startsWith('event: ')) eventType = line.slice(7);
                else if (line.startsWith('data: ')) eventData = line.slice(6);
              }
              if (!eventType || !eventData) continue;

              let parsed: unknown;
              try {
                parsed = JSON.parse(eventData);
              } catch {
                settleReject(new Error(`Malformed SSE payload for event '${eventType}'`));
                return;
              }

              if (eventType === 'init') {
                const p = parseInit(parsed);
                if (!p) {
                  settleReject(new Error('Invalid SSE init payload'));
                  return;
                }
                onProgress(p);
              } else if (eventType === 'progress') {
                const p = parseProgress(parsed);
                if (!p) {
                  settleReject(new Error('Invalid SSE progress payload'));
                  return;
                }
                onProgress(p);
              } else if (eventType === 'result') {
                const r = parseResult(parsed);
                if (!r) {
                  settleReject(new Error('Invalid SSE result payload'));
                  return;
                }
                settleResolve(r);
                return;
              } else if (eventType === 'error') {
                settleReject(new Error(parseError(parsed)));
                return;
              }
            }
            processChunk();
          }).catch((err) => {
            // AbortError is expected on user-initiated cancellation — surface as-is.
            if (err instanceof Error) settleReject(err);
            else settleReject(new Error(String(err)));
          });
        }
        processChunk();
      })
      .catch((err) => {
        if (err instanceof Error) reject(err);
        else reject(new Error(String(err)));
      });
  });
}

export async function runPerformance(
  req: PerformanceRequest,
  signal?: AbortSignal,
): Promise<PerformanceResponse> {
  // Only forward an axios config when a signal is actually provided —
  // keeps `apiClient.post` calls clean for callers that don't need cancel.
  const { data } = signal
    ? await apiClient.post<PerformanceResponse>('/backtest/performance', req, { signal })
    : await apiClient.post<PerformanceResponse>('/backtest/performance', req);
  return data;
}

export async function runWalkForward(
  req: WalkForwardRequest,
  signal?: AbortSignal,
): Promise<WalkForwardResponse> {
  const { data } = signal
    ? await apiClient.post<WalkForwardResponse>('/backtest/walk-forward', req, { signal })
    : await apiClient.post<WalkForwardResponse>('/backtest/walk-forward', req);
  return data;
}
