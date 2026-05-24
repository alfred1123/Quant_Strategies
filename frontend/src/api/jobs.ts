import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { JobDetail, JobRow } from '../types/jobs';
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
