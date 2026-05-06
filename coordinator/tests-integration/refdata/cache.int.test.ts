import { describe, it, expect, beforeAll } from "bun:test";
import { refdata } from "../../src/refdata/cache";
import { isDbAvailable } from "../helpers";

describe("RefDataCache (integration)", () => {
  let available = false;

  beforeAll(async () => {
    available = await isDbAvailable();
    if (available) await refdata.load();
  });

  it("loads at least one table from REFDATA", () => {
    if (!available) return;
    expect(refdata.tables().length).toBeGreaterThan(0);
  });

  it("includes queue_status and exposes QUEUED -> 1", () => {
    if (!available) return;
    expect(refdata.tables()).toContain("queue_status");
    const queuedId = refdata.idByName("queue_status", "QUEUED", "queue_status_id");
    expect(typeof queuedId).toBe("number");
    expect(queuedId).toBeGreaterThan(0);
  });
});
