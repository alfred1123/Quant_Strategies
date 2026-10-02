import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { BacktestSearchRow, PromotionMetricRow } from '../types/config';

async function fetchConfig<T>(table: string): Promise<T[]> {
  const { data } = await apiClient.get<T[]>(`/config/${table}`);
  return data;
}

export const useBacktestSearch = () =>
  useQuery({
    queryKey: ['config', 'backtest_search'],
    queryFn: () => fetchConfig<BacktestSearchRow>('backtest_search'),
    staleTime: Infinity,
  });

export const usePromotionMetrics = () =>
  useQuery({
    queryKey: ['config', 'promotion_metric'],
    queryFn: () => fetchConfig<PromotionMetricRow>('promotion_metric'),
    staleTime: Infinity,
  });
