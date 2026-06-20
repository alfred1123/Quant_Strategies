import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { PromotionRow } from '../types/promotion';

export const PROMOTIONS_QUERY_KEY = ['promotions'] as const;

// Promotion decisions are written by the worker on backtest completion;
// a slow poll keeps the tab fresh without hammering the DB.
const POLL_INTERVAL_MS = 10000;

async function listPromotions(strategyId?: string): Promise<PromotionRow[]> {
  const { data } = await apiClient.get<PromotionRow[]>('/backtest/promotions', {
    params: strategyId ? { strategy_id: strategyId } : undefined,
  });
  return data;
}

/** List promotion decision-log rows (newest first), polled every 10s. */
export function usePromotions(strategyId?: string) {
  return useQuery({
    queryKey: strategyId ? [...PROMOTIONS_QUERY_KEY, strategyId] : PROMOTIONS_QUERY_KEY,
    queryFn: () => listPromotions(strategyId),
    // Global staleTime is Infinity — override so tab switches refetch after
    // a backtest completes and invalidation may have been missed.
    staleTime: POLL_INTERVAL_MS,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });
}
