import { apiClient } from './client';
import type {
  OptimizeRequest, OptimizeResponse,
  PerformanceRequest, PerformanceResponse,
  WalkForwardRequest, WalkForwardResponse,
} from '../types/backtest';

export async function runOptimize(req: OptimizeRequest): Promise<OptimizeResponse> {
  const { data } = await apiClient.post<OptimizeResponse>('/backtest/optimize', req);
  return data;
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
