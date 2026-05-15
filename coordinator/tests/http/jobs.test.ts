import { describe, it, expect } from "bun:test";
import { createApp } from "../../src/http/server";
import type { JobsService } from "../../src/services/jobs";

// All assertions exercise validation that fails BEFORE jobs.enqueueJob is
// reached, so a throwing stub catches accidental regressions.
const stubJobs: JobsService = {
  enqueueJob: async () => { throw new Error("jobs.enqueueJob should not be called"); },
};
const app = createApp({ jobs: stubJobs });

// These tests exercise the validation/auth paths of POST /api/v1/jobs that
// run BEFORE any DB or refdata lookup, so they're safe in the unit suite.

const post = (body: unknown, headers: Record<string, string> = {}) =>
  app.fetch(new Request("http://localhost/api/v1/jobs", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  }));

describe("POST /api/v1/jobs (unit)", () => {
  it("returns 401 when x-user-id header is missing", async () => {
    const res = await post({
      strategy_id: "00000000-0000-0000-0000-000000000001",
      strategy_vid: 1,
      priority: "normal",
    });
    expect(res.status).toBe(401);
  });

  it("returns 400 when strategy_id is not a UUID", async () => {
    const res = await post(
      { strategy_id: "not-a-uuid", strategy_vid: 1, priority: "normal" },
      { "x-user-id": "u1" },
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 when strategy_vid is non-positive", async () => {
    const res = await post(
      { strategy_id: "00000000-0000-0000-0000-000000000001", strategy_vid: 0, priority: "normal" },
      { "x-user-id": "u1" },
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 when priority is unknown", async () => {
    const res = await post(
      { strategy_id: "00000000-0000-0000-0000-000000000001", strategy_vid: 1, priority: "urgent" },
      { "x-user-id": "u1" },
    );
    expect(res.status).toBe(400);
  });

  it("returns 400 on malformed JSON body", async () => {
    const res = await app.fetch(new Request("http://localhost/api/v1/jobs", {
      method: "POST",
      headers: { "content-type": "application/json", "x-user-id": "u1" },
      body: "not json",
    }));
    expect(res.status).toBe(400);
  });
});
