import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  BackfillReport,
  BackfillRequest,
  BarSubscriptionRow,
  SubscribeRequest,
  VenueDepth,
} from '../types/marketData';

/** Identity of one series — the `PRICE_BAR` key minus the timestamp. */
export interface SeriesKey {
  internal_cusip: string;
  tm_interval_id: number;
  source_app_id: number;
}

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
 * The oldest bar the venue itself will serve for a series.
 *
 * Costs a live exchange call, so it is only asked once a whole series is
 * identified, and cached for the session: retention moves by one bar per
 * interval, which never changes an answer a dialog is showing.
 *
 * Every dialog offering a date depends on this. A target the venue cannot
 * reach is not a gap waiting to be filled — it is history that does not exist,
 * and the difference is invisible until something asks.
 */
export function useVenueDepth(key: Partial<SeriesKey>) {
  const complete =
    key.internal_cusip !== undefined
    && key.tm_interval_id !== undefined
    && key.source_app_id !== undefined;
  return useQuery({
    queryKey: ['market-data', 'venue-depth', key] as const,
    enabled: complete,
    staleTime: Infinity,
    retry: false,
    queryFn: async (): Promise<VenueDepth> => {
      const { data } = await apiClient.get<VenueDepth>(
        '/market-data/price-bars/venue-depth',
        { params: key },
      );
      return data;
    },
  });
}

/**
 * Fill toward the venue's floor.
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
