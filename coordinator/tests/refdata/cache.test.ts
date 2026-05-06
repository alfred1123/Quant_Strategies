import { describe, it, expect, beforeEach } from "bun:test";
import { RefDataCache } from "../../src/refdata/cache";

/** Seed the private `store` Map without going through `load()` (which hits DB). */
function seed(cache: RefDataCache, table: string, rows: Record<string, unknown>[]): void {
  // `store` is private — bracket access bypasses TS visibility for tests only.
  (cache as unknown as { store: Map<string, Record<string, unknown>[]> })
    .store.set(table, rows);
}

describe("RefDataCache", () => {
  let cache: RefDataCache;

  beforeEach(() => {
    cache = new RefDataCache();
  });

  describe("raw", () => {
    it("returns rows for a known table", () => {
      seed(cache, "queue_status", [
        { queue_status_id: 1, name: "QUEUED" },
        { queue_status_id: 2, name: "RUNNING" },
      ]);
      expect(cache.raw("queue_status")).toHaveLength(2);
    });

    it("throws on unknown table", () => {
      expect(() => cache.raw("nope")).toThrow(/Unknown REFDATA table/);
    });

    it("throws on empty table", () => {
      seed(cache, "queue_status", []);
      expect(() => cache.raw("queue_status")).toThrow(/is empty/);
    });
  });

  describe("idByName", () => {
    beforeEach(() => {
      seed(cache, "queue_status", [
        { queue_status_id: 1, name: "QUEUED" },
        { queue_status_id: 2, name: "RUNNING" },
      ]);
    });

    it("resolves a known name to its ID", () => {
      expect(cache.idByName("queue_status", "QUEUED", "queue_status_id")).toBe(1);
      expect(cache.idByName("queue_status", "RUNNING", "queue_status_id")).toBe(2);
    });

    it("throws when name is not found", () => {
      expect(() => cache.idByName("queue_status", "MISSING", "queue_status_id"))
        .toThrow(/has no name=MISSING/);
    });

    it("includes the list of known names in the error", () => {
      expect(() => cache.idByName("queue_status", "MISSING", "queue_status_id"))
        .toThrow(/QUEUED, RUNNING/);
    });
  });

  describe("tables", () => {
    it("returns sorted table names", () => {
      seed(cache, "queue_status", [{ name: "X" }]);
      seed(cache, "asset_type", [{ name: "Y" }]);
      seed(cache, "indicator", [{ name: "Z" }]);
      expect(cache.tables()).toEqual(["asset_type", "indicator", "queue_status"]);
    });

    it("returns an empty array when nothing is loaded", () => {
      expect(cache.tables()).toEqual([]);
    });
  });
});
