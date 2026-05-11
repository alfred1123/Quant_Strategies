import { Hono } from "hono";
import { logger } from "hono/logger";
import { sql } from "../db/client";
import {
  queryQueue,
  queryTerminal,
  enqueue,
  countQueuedForUser,
} from "../queue/repo";
import { refdata } from "../refdata/cache";
import {
  EnqueueRequestSchema,
  PRIORITY_MAP,
  MAX_QUEUED_PER_USER,
  type EnqueueResponse,
} from "../types/queue";

export const app = new Hono();

app.use("*", logger());

// Liveness -- process is up
app.get("/health", (c) => c.json({ ok: "true" }));

// Readiness -- can connect to database
app.get("/health/ready", async (c) => {
  try {
    await sql`SELECT 1`;
    return c.json({ ok: "true" });
  } catch (err) {
    return c.json({ ok: "false", error: String(err) }, 503);
  }
});

// Smoke-test endpoint -- real DB rows, no auth yet
app.get("/api/v1/jobs", async (c) => {
    const rows = await queryQueue({ limit: 5 });
    return c.json({ ok: "true", rows });
});

// Enqueue a backtest job. See docs/design/backtest-queue.md §8.1–8.2.
// TODO(auth): replace x-user-id header with JWT qs_token cookie verification.
app.post("/api/v1/jobs", async (c) => {
  const userId = c.req.header("x-user-id");
  if (!userId) {
    return c.json({ error: "missing x-user-id header" }, 401);
  }

  const body = await c.req.json().catch(() => null);
  const parsed = EnqueueRequestSchema.safeParse(body);
  if (!parsed.success) {
    return c.json({ error: "invalid body", details: parsed.error.issues }, 400);
  }
  const req = parsed.data;

  const queuedStatusId = refdata.idByName("queue_status", "QUEUED", "queue_status_id");

  // Per-user rate limit (design §8.1).
  const queuedCount = await countQueuedForUser(userId, queuedStatusId);
  if (queuedCount >= MAX_QUEUED_PER_USER) {
    return c.json(
      { error: `rate_limited: at most ${MAX_QUEUED_PER_USER} QUEUED jobs per user` },
      429,
    );
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

  // Derive queue_pos from the same ordered list the UI consumes
  // (priority ASC, transact_from_ts ASC). 1 = next to run; 0 if not found.
  const queued = await queryTerminal({ statusId: queuedStatusId });
  const queuePos = queued.findIndex((r) => r.queue_id ==.env= queueId) + 1;
  const res: EnqueueResponse = { queue_id: queueId, queue_pos: queuePos };
  return c.json(res, 201);
});

//Generic error handler
app.onError((err, c) => {
  console.error("[http] unhandled:", err);
  return c.json({ error: String(err)}, 500);
});

