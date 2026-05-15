import { refdata } from "../refdata/cache";
import {
  enqueue,
  countQueuedForUser,
  queryTerminal,
} from "../queue/repo";
import {
  PRIORITY_MAP,
  MAX_QUEUED_PER_USER,
  type EnqueueRequest,
  type EnqueueResponse,
} from "../types/queue";
import type { Manager } from "../queue/manager";

/** Domain errors. The HTTP layer maps these to status codes. */
export class RateLimitError extends Error {
  constructor(public readonly limit: number) {
    super(`rate_limited: at most ${limit} QUEUED jobs per user`);
    this.name = "RateLimitError";
  }
}

/** Service contract — HTTP-agnostic. CLI / gRPC / SSE handlers can reuse it. */
export interface JobsService {
  enqueueJob(userId: string, req: EnqueueRequest): Promise<EnqueueResponse>;
}

export function createJobsService(manager: Manager): JobsService {
  return {
    async enqueueJob(userId, req) {
      const queuedStatusId = refdata.idByName(
        "queue_status",
        "QUEUED",
        "queue_status_id",
      );

      // Per-user rate limit (design §8.1).
      const queuedCount = await countQueuedForUser(userId, queuedStatusId);
      if (queuedCount >= MAX_QUEUED_PER_USER) {
        throw new RateLimitError(MAX_QUEUED_PER_USER);
      }

      const queueId = crypto.randomUUID();
      await enqueue({
        queueId,
        strategyId: req.strategy_id,
        strategyVid: req.strategy_vid,
        statusId: queuedStatusId,
        priority: PRIORITY_MAP[req.priority],
        userId,
      });

      // Nudge the queue loop so the new row is claimed immediately rather
      // than waiting for the next worker exit / external wake.
      manager.wake();

      // Derive queue_pos from the same ordered list the UI consumes
      // (priority ASC, transact_from_ts ASC). 1 = next to run; 0 if not found.
      // TODO: race-prone under concurrent enqueues; eventually push into
      // BT.SP_INS_QUEUE so the position is returned atomically.
      const queued = await queryTerminal({ statusId: queuedStatusId });
      const queuePos = queued.findIndex((r) => r.queue_id === queueId) + 1;
      return { queue_id: queueId, queue_pos: queuePos };
    },
  };
}
