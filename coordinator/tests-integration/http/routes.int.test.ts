import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { app } from "../../src/http/server";
import { refdata } from "../../src/refdata/cache";
import { enqueue } from "../../src/queue/repo";
import { isDbAvailable, cleanQueueRows, newUuid, TEST_USER_ID } from "../helpers";

describe("HTTP routes (integration)", () => {
  let available = false;

  beforeAll(async () => {
    available = await isDbAvailable();
    if (!available) return;
    await refdata.load();
    await cleanQueueRows();
  });

  afterAll(async () => {
    if (available) await cleanQueueRows();
  });

  it("GET /health/ready returns 200 when DB is reachable", async () => {
    if (!available) return;
    const res = await app.fetch(new Request("http://localhost/health/ready"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: "true" });
  });

  it("GET /api/v1/jobs returns rows array", async () => {
    if (!available) return;
    // Seed one row.
    const queuedId = refdata.idByName("queue_status", "QUEUED", "queue_status_id");
    await enqueue({
      queueId: newUuid(),
      strategyId: newUuid(),
      strategyVid: 1,
      statusId: queuedId,
      priority: 5,
      userId: TEST_USER_ID,
    });

    const res = await app.fetch(new Request("http://localhost/api/v1/jobs"));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: string; rows: unknown[] };
    expect(body.ok).toBe("true");
    expect(Array.isArray(body.rows)).toBe(true);
    expect(body.rows.length).toBeGreaterThan(0);
  });
});
