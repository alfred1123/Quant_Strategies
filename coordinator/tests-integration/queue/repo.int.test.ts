import { describe, it, expect, beforeAll, afterAll } from "bun:test";
import { enqueue, queryQueue } from "../../src/queue/repo";
import { refdata } from "../../src/refdata/cache";
import { isDbAvailable, cleanQueueRows, newUuid, TEST_USER_ID } from "../helpers";

describe("queue repo (integration)", () => {
  let available = false;
  let queuedId = 0;

  beforeAll(async () => {
    available = await isDbAvailable();
    if (!available) return;
    await refdata.load();
    queuedId = refdata.idByName("queue_status", "QUEUED", "queue_status_id");
    await cleanQueueRows();
  });

  afterAll(async () => {
    if (available) await cleanQueueRows();
  });

  it("enqueue inserts a row that queryQueue returns", async () => {
    if (!available) return;
    const queueId = newUuid();
    const strategyId = newUuid();

    await enqueue({
      queueId,
      strategyId,
      strategyVid: 1,
      statusId: queuedId,
      priority: 5,
      userId: TEST_USER_ID,
    });

    const rows = await queryQueue({ queueId });
    expect(rows).toHaveLength(1);
    const row = rows[0]!;
    expect(row.queue_id).toBe(queueId);
    expect(row.strategy_id).toBe(strategyId);
    expect(row.queue_vid).toBe(1);
    expect(row.queue_status_id).toBe(queuedId);
    expect(row.queue_status).toBe("QUEUED");
    expect(row.priority).toBe(5);
    expect(row.user_id).toBe(TEST_USER_ID);
  });

  it("queryQueue with userId filter returns only that user's rows", async () => {
    if (!available) return;
    // Previous test inserted at least one row; query by user.
    const rows = await queryQueue({ userId: TEST_USER_ID });
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row.user_id).toBe(TEST_USER_ID);
    }
  });

  it("queryQueue respects the limit parameter", async () => {
    if (!available) return;
    // Insert 3 jobs and ask for limit=2.
    for (let i = 0; i < 3; i++) {
      await enqueue({
        queueId: newUuid(),
        strategyId: newUuid(),
        strategyVid: 1,
        statusId: queuedId,
        priority: 5,
        userId: TEST_USER_ID,
      });
    }
    const rows = await queryQueue({ userId: TEST_USER_ID, limit: 2 });
    expect(rows.length).toBe(2);
  });
});
