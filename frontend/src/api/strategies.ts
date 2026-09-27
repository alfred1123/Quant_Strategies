import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { StrategyListRow, StrategyListVersions, StrategyResult } from '../types/strategies';

export const STRATEGIES_QUERY_KEY = ['strategies'] as const;

async function listStrategies(
  versions: StrategyListVersions,
  limit: number,
): Promise<StrategyListRow[]> {
  const { data } = await apiClient.get<StrategyListRow[]>('/strategies', {
    params: { versions, limit },
  });
  return data;
}

/** Stored backtest for one version. ``SP_GET_RESULT`` keyed by strategy id and vid. */
export function fetchStrategyResult(
  strategyId: string,
  strategyVid: number,
): Promise<StrategyResult> {
  return apiClient
    .get<StrategyResult>(`/strategies/${strategyId}/result`, {
      params: { strategy_vid: strategyVid },
    })
    .then((r) => r.data);
}

/** Caller-owned strategy catalog for the Trade picker (Phase 1.6). */
export function useStrategies(versions: StrategyListVersions = 'best', limit = 200) {
  return useQuery({
    queryKey: [...STRATEGIES_QUERY_KEY, versions, limit],
    queryFn: () => listStrategies(versions, limit),
  });
}
