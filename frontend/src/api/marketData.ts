import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  BackfillReport,
  BackfillRequest,
  BarSubscriptionRow,
  SubscribeRequest,
} from '../types/marketData';

export const SUBSCRIPTIONS_QUERY_KEY = ['market-data', 'subscriptions'] as const;

async function listSubscriptions(): Promise<BarSubscriptionRow[]> {
  const { data } = await apiClient.get<BarSubscriptionRow[]>('/market-data/subscriptions');
  return data;
}

async function subscribe(req: SubscribeRequest): Promise<BarSubscriptionRow> {
  const { data } = await apiClient.post<BarSubscriptionRow>(
    '/market-data/subscriptions',
    req,
  );
  return data;
}

async function backfill(req: BackfillRequest): Promise<BackfillReport> {
  const { data } = await apiClient.post<BackfillReport>(
    '/market-data/price-bars/backfill',
    req,
  );
  return data;
}

/**
 * The caller's subscriptions with coverage.
 *
 * Coverage moves whenever the hourly warmer runs, so unlike most lists here it
 * goes stale on its own: a short stale window keeps "last bar" from claiming
 * an old capture is current, without polling a read that costs index probes
 * per row.
 */
export function useSubscriptions() {
  return useQuery({
    queryKey: SUBSCRIPTIONS_QUERY_KEY,
    queryFn: listSubscriptions,
    staleTime: 60_000,
  });
}

export function useSubscribe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: subscribe,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SUBSCRIPTIONS_QUERY_KEY });
    },
  });
}

/**
 * Fill an explicit range.
 *
 * Invalidates the list because a fill is exactly what changes coverage, and
 * the number the user came to move is on that table.
 */
export function useBackfill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: backfill,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SUBSCRIPTIONS_QUERY_KEY });
    },
  });
}

export { listSubscriptions, subscribe, backfill };
