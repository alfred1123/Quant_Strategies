import { Hono } from "hono";
import { logger } from "hono/logger";
import { sql } from "../db/client";
import { queryQueue } from "../queue/repo";

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

//Generic error handler
app.onError((err, c) => {
  console.error("[http] unhandled:", err);
  return c.json({ error: String(err)}, 500);
});

