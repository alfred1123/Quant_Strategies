import { z } from "zod";

/** Frontend label → DB priority integer (lower = runs first). */
export const PRIORITY_MAP = {
  normal: 100,
  high: 0,
} as const;

export type PriorityLabel = keyof typeof PRIORITY_MAP;

/** POST /api/v1/jobs request body — see docs/design/backtest-queue.md §8.2. */
export const EnqueueRequestSchema = z.object({
  strategy_id: z.string().uuid(),
  strategy_vid: z.number().int().positive(),
  priority: z.enum(["normal", "high"]).default("normal"),
});

export type EnqueueRequest = z.infer<typeof EnqueueRequestSchema>;

/** POST /api/v1/jobs response. */
export interface EnqueueResponse {
  queue_id: string;
  queue_pos: number;
}

/** Max QUEUED jobs per user before POST /api/v1/jobs returns 429. */
export const MAX_QUEUED_PER_USER = 30;
