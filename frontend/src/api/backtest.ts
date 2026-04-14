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

/**
 * Stream optimization via SSE. Calls onProgress per trial, resolves with the
 * final OptimizeResponse. Supports cancellation via AbortSignal.
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    })
      .then((response) => {
        if (!response.ok) {
          return response.json().then(
            (body) => reject(new Error(body.detail ?? `HTTP ${response.status}`)),
            () => reject(new Error(`HTTP ${response.status}`)),
          );
        }
        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        function processChunk() {
          reader.read().then(({ done, value }) => {
            if (done) {
              reject(new Error('Stream ended without result'));
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop()!;

            for (const part of parts) {
              let eventType = '';
              let eventData = '';
              for (const line of part.split('\n')) {
                if (line.startsWith('event: ')) eventType = line.slice(7);
                else if (line.startsWith('data: ')) eventData = line.slice(6);
              }
              if (!eventType || !eventData) continue;
              const parsed = JSON.parse(eventData);
              if (eventType === 'init' || eventType === 'progress') {
                onProgress(parsed);
              } else if (eventType === 'result') {
                resolve(parsed as OptimizeResponse);
                return;
              } else if (eventType === 'error') {
                reject(new Error(parsed.detail ?? 'Optimization failed'));
                return;
              }
            }
            processChunk();
          }).catch(reject);
        }
        processChunk();
      })
      .catch(reject);
  });
}

export async function runPerformance(req: PerformanceRequest): Promise<PerformanceResponse> {
  const { data } = await apiClient.post<PerformanceResponse>('/backtest/performance', req);
  return data;
}

export async function runWalkForward(req: WalkForwardRequest): Promise<WalkForwardResponse> {
  const { data } = await apiClient.post<WalkForwardResponse>('/backtest/walk-forward', req);
  return data;
}
