import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { PromotionMetricRow } from '../types/config';

async function fetchConfig<T>(table: string): Promise<T[]> {
  const { data } = await apiClient.get<T[]>(`/config/${table}`);
  return data;
}

export const usePromotionMetrics = () =>
  useQuery({
    queryKey: ['config', 'promotion_metric'],
    queryFn: () => fetchConfig<PromotionMetricRow>('promotion_metric'),
    staleTime: Infinity,
  });
