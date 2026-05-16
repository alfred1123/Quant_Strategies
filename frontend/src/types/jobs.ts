// Mirrors api/schemas/jobs.py — keep in sync.

export type JobStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCEL_REQUESTED'
  | 'CANCELLED';

export interface JobRow {
  queue_id: string;
  queue_vid: number;
  strategy_id: string;
  strategy_vid: number;
  strategy_nm: string | null;
  queue_status_id: number;
  queue_status: JobStatus;
  priority: number;
  user_id: string;
  transact_from_ts: string;
  error_text: string | null;
}
