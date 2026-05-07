import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { app } from "../../src/http/server";
import { refdata } from "../../src/refdata/cache";
import { enqueue } from "../../src/queue/repo";
import { MAX_QUEUED_PER_USER } from "../../src/types/queue";
import { isDbAvailable, cleanQueueRows, newUuid, TEST_USER_ID } from "../helpers";

const post = (body: unknown) =>
  app.fetch(new Request("http://localhost/api/v1/jobs", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-user-id": TEST_USER_ID,
    },
    body: JSON.stringify(body),
  }));

describe("POST /api/v1/jobs (integration)", () => {
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

  it("enqueues a normal-priority job and returns queue_pos=1 for the only QUEUED row", async () => {
    if (!available) return;
    const res = await post({
      strategy_id: newUuid(),
      strategy_vid: 1,
      priority: "normal",
    });
    expect(res.status).toBe(201);
    const body = (await res.json()) as { queue_id: string; queue_pos: number };
    expect(body.queue_id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(body.queue_pos).toBe(1);
  });

  it("high-priority job ranks ahead of an existing normal-priority job", async () => {
    if (!available) return;
    await cleanQueueRows();

    // First: enqueue one normal.
    const r1 = await post({
      strategy_id: newUuid(),
      strategy_vid: 1,
      priority: "normal",
    });
    const b1 = (await r1.json()) as { queue_pos: number };
    expect(b1.queue_pos).toBe(1);

    // Second: enqueue a high-priority job — should take position 1, push other to 2.
    const r2 = await post({
      strategy_id: newUuid(),
      strategy_vid: 1,
      priority: "high",
    });
    expect(r2.status).toBe(201);
    const b2 = (await r2.json()) as { queue_pos: number };
    expect(b2.queue_pos).toBe(1);
  });

  it("returns 429 when the user has reached MAX_QUEUED_PER_USER", async () => {
    if (!available) return;
    await cleanQueueRows();

    // Seed exactly MAX_QUEUED_PER_USER rows directly (faster than HTTP loop).
    const queuedId = refdata.idByName("queue_status", "QUEUED", "queue_status_id");
    for (let i = 0; i < MAX_QUEUED_PER_USER; i++) {
      await enqueue({
        queueId: newUuid(),
        strategyId: newUuid(),
        strategyVid: 1,
        statusId: queuedId,
        priority: 100,
        userId: TEST_USER_ID,
      });
    }

    const res = await post({
      strategy_id: newUuid(),
      strategy_vid: 1,
      priority: "normal",
    });
    expect(res.status).toBe(429);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/rate_limited/);
  });
});
