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

export async function runPerformance(req: PerformanceRequest): Promise<PerformanceResponse> {
  const { data } = await apiClient.post<PerformanceResponse>('/backtest/performance', req);
  return data;
}

export async function runWalkForward(req: WalkForwardRequest): Promise<WalkForwardResponse> {
  const { data } = await apiClient.post<WalkForwardResponse>('/backtest/walk-forward', req);
  return data;
}
