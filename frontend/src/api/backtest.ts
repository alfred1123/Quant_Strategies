import { apiClient } from './client';
import type { OptimizeRequest, OptimizeResponse, PerformanceRequest, PerformanceResponse } from '../types/backtest';

export async function runOptimize(req: OptimizeRequest): Promise<OptimizeResponse> {
  const { data } = await apiClient.post<OptimizeResponse>('/backtest/optimize', req);
  return data;
}

export async function runPerformance(req: PerformanceRequest): Promise<PerformanceResponse> {
  const { data } = await apiClient.post<PerformanceResponse>('/backtest/performance', req);
  return data;
}
