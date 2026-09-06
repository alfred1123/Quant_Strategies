import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import { PROMOTIONS_QUERY_KEY } from './promotion';
import type { JobDetail, JobRow, JobStatus } from '../types/jobs';
import type { OptimizeRequest } from '../types/backtest';

export const JOBS_QUERY_KEY = ['jobs'] as const;

// Polling cadence — short enough for live status, long enough to keep
// DB load trivial. SSE per-row is a Phase-D upgrade.
const POLL_INTERVAL_MS = 3000;

export interface EnqueueRequest {
  strategy_nm: string;
  config_json: OptimizeRequest;
  priority?: 'normal' | 'high';
}

export interface EnqueueResponse {
  queue_id: string;
  queue_pos: number;
}

async function listJobs(): Promise<JobRow[]> {
  const { data } = await apiClient.get<JobRow[]>('/backtest/jobs');
  return data;
}

async function cancelJob(queueId: string): Promise<JobRow> {
  const { data } = await apiClient.post<JobRow>(`/backtest/jobs/${queueId}/cancel`);
  return data;
}

async function reenqueueJob(queueId: string): Promise<EnqueueResponse> {
  const { data } = await apiClient.post<EnqueueResponse>(
    `/backtest/jobs/${queueId}/reenqueue`,
  );
  return data;
}

async function enqueueJob(req: EnqueueRequest): Promise<EnqueueResponse> {
  const { data } = await apiClient.post<EnqueueResponse>('/backtest/jobs', req);
  return data;
}

async function getJob(queueId: string): Promise<JobDetail> {
  const { data } = await apiClient.get<JobDetail>(`/backtest/jobs/${queueId}`);
  return data;
}

/** List the current user's jobs, polled every 3s. */
export function useJobs() {
  return useQuery({
    queryKey: JOBS_QUERY_KEY,
    queryFn: listJobs,
    refetchInterval: POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });
}

/**
 * When a job transitions to COMPLETED, refresh the promotion log and optionally
 * invoke ``onCompleted`` (e.g. switch to the Promotion tab).
 *
 * Mount on BacktestPage so it runs while the user watches the Queue tab.
 */
export function useJobCompletionEffects(onCompleted?: (queueId: string) => void) {
  const jobs = useJobs();
  const qc = useQueryClient();
  const prevStatusRef = useRef<Map<string, JobStatus>>(new Map());

  useEffect(() => {
    const rows = jobs.data;
    if (!rows) return;

    for (const row of rows) {
      const prev = prevStatusRef.current.get(row.queue_id);
      const next = row.queue_status;
      if (prev && prev !== 'COMPLETED' && next === 'COMPLETED') {
        qc.invalidateQueries({ queryKey: PROMOTIONS_QUERY_KEY });
        onCompleted?.(row.queue_id);
      }
      prevStatusRef.current.set(row.queue_id, next);
    }
  }, [jobs.data, onCompleted, qc]);
}

/** Cancel a job → invalidate the list so the next poll repaints. */
export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
    },
  });
}

/**
 * Re-enqueue a FAILED / CANCELLED job — server submits a new QUEUE row
 * reusing the original strategy + priority and returns the new queue_id.
 */
export function useReenqueueJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reenqueueJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
    },
  });
}

/** Submit a new backtest job — server creates BT.STRATEGY then BT.QUEUE. */
export function useEnqueueJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: enqueueJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
    },
  });
}

/** Fetch one job's frozen config + completion payload (on-demand). */
export function fetchJob(queueId: string): Promise<JobDetail> {
  return getJob(queueId);
}

/** Fetch one job's frozen config + payload reactively (skips when no id). */
export function useJob(queueId?: string) {
  return useQuery({
    queryKey: [...JOBS_QUERY_KEY, queueId],
    queryFn: () => getJob(queueId as string),
    enabled: Boolean(queueId),
  });
}

// ── promote strategy ────────────────────────────────────────────────

interface PromoteParams {
  strategyId: string;
  strategyVid: number;
}

async function promoteStrategy({ strategyId, strategyVid }: PromoteParams): Promise<void> {
  await apiClient.post(`/backtest/jobs/strategies/${strategyId}/promote`, {
    strategy_vid: strategyVid,
  });
}

/** Promote a VID to IS_BEST_IND = 'Y' — invalidates the jobs list on success. */
export function usePromoteStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: promoteStrategy,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
    },
  });
}

// ── logical delete ──────────────────────────────────────────────────

interface LogicalDeleteParams {
  strategyId: string;
  logicalDeleteInd: 'Y' | 'N';
  strategyVid?: number | null;
}

async function setStrategyLogicalDelete({
  strategyId, logicalDeleteInd, strategyVid,
}: LogicalDeleteParams): Promise<void> {
  await apiClient.post(`/backtest/jobs/strategies/${strategyId}/logical-delete`, {
    logical_delete_ind: logicalDeleteInd,
    strategy_vid: strategyVid ?? null,
  });
}

/** Retire or restore a strategy — invalidates jobs + promotions on success. */
export function useSetStrategyLogicalDelete() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: setStrategyLogicalDelete,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: PROMOTIONS_QUERY_KEY });
    },
  });
}
