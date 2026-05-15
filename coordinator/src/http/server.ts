import { Hono } from "hono";
import { logger } from "hono/logger";
import { sql } from "../db/client";
import { queryQueue } from "../queue/repo";
import { EnqueueRequestSchema } from "../types/queue";
import { RateLimitError, type JobsService } from "../services/jobs";

/** Dependencies injected into the HTTP layer. Add new collaborators here. */
export interface ServerDeps {
  jobs: JobsService;
}

/**
 * Build the Hono app from explicit dependencies. The HTTP layer owns transport
 * concerns only — request parsing, status codes, response shaping. All domain
 * policy (rate limit, ID generation, queue ranking, manager wake) lives in the
 * service layer.
 */
export function createApp(deps: ServerDeps): Hono {
  const app = new Hono();

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

    try {
      const res = await deps.jobs.enqueueJob(userId, parsed.data);
      return c.json(res, 201);
    } catch (err) {
      if (err instanceof RateLimitError) {
        return c.json({ error: err.message }, 429);
      }
      throw err;
    }
  });

  // Generic error handler
  app.onError((err, c) => {
    console.error("[http] unhandled:", err);
    return c.json({ error: String(err) }, 500);
  });

  return app;
}

