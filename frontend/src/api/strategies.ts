import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import type { StrategyListRow, StrategyListVersions } from '../types/strategies';

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

/** Caller-owned strategy catalog for the Trade picker (Phase 1.6). */
export function useStrategies(versions: StrategyListVersions = 'best', limit = 200) {
  return useQuery({
    queryKey: [...STRATEGIES_QUERY_KEY, versions, limit],
    queryFn: () => listStrategies(versions, limit),
  });
}
