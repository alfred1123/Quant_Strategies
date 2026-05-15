import { describe, it, expect } from "bun:test";
import { createApp } from "../../src/http/server";
import type { JobsService } from "../../src/services/jobs";

// Health/404 routes never invoke jobs; an empty stub is sufficient.
const stubJobs: JobsService = {
  enqueueJob: async () => { throw new Error("jobs.enqueueJob should not be called"); },
};
const app = createApp({ jobs: stubJobs });

describe("GET /health", () => {
  it("returns 200 and ok payload (liveness)", async () => {
    const res = await app.fetch(new Request("http://localhost/health"));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: "true" });
  });
});

describe("404 handling", () => {
  it("returns 404 for unknown routes", async () => {
    const res = await app.fetch(new Request("http://localhost/does-not-exist"));
    expect(res.status).toBe(404);
  });
});
