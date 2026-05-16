import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import type { JobRow } from '../types/jobs';

export const JOBS_QUERY_KEY = ['jobs'] as const;

// Polling cadence — short enough for live status, long enough to keep
// DB load trivial. SSE per-row is a Phase-D upgrade.
const POLL_INTERVAL_MS = 3000;

async function listJobs(): Promise<JobRow[]> {
  const { data } = await apiClient.get<JobRow[]>('/jobs');
  return data;
}

async function cancelJob(queueId: string): Promise<JobRow> {
  const { data } = await apiClient.post<JobRow>(`/jobs/${queueId}/cancel`);
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
