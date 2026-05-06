import { describe, it, expect } from "bun:test";
import type { Sql } from "postgres";
import { callProc, StoredProcedureError, type SpResult } from "../../src/db/client";

// The `db` argument to callProc is unused in these tests because the `build`
// callback returns a fake awaitable directly. Cast a sentinel through `unknown`.
const fakeDb = {} as unknown as Sql;

/** Build a fake PendingQuery that resolves to the given rows. */
const fakeBuild = (rows: SpResult[]) =>
  () => Promise.resolve(rows) as unknown as ReturnType<Parameters<typeof callProc>[2]>;

describe("callProc", () => {
  it("returns the first row when SQLSTATE is 00000", async () => {
    const result = await callProc(fakeDb, "test.sp_ok", fakeBuild([
      { out_sqlstate: "00000", out_sqlmsg: "0", out_sqlerrmc: "ok" },
    ]));
    expect(result.out_sqlstate).toBe("00000");
    expect(result.out_sqlerrmc).toBe("ok");
  });

  it("throws StoredProcedureError on non-00000 SQLSTATE", async () => {
    const promise = callProc(fakeDb, "test.sp_fail", fakeBuild([
      { out_sqlstate: "P0001", out_sqlmsg: "10", out_sqlerrmc: "validation failed" },
    ]));
    await expect(promise).rejects.toBeInstanceOf(StoredProcedureError);
    await expect(promise).rejects.toMatchObject({
      proc: "test.sp_fail",
      sqlstate: "P0001",
      sqlerrmc: "validation failed",
    });
  });

  it("throws StoredProcedureError when no rows are returned", async () => {
    const promise = callProc(fakeDb, "test.sp_empty", fakeBuild([]));
    await expect(promise).rejects.toBeInstanceOf(StoredProcedureError);
    await expect(promise).rejects.toMatchObject({
      proc: "test.sp_empty",
      sqlstate: "NO_RESULT",
    });
  });

  it("preserves extra OUT params via generic", async () => {
    type Extra = SpResult & { out_result: string };
    const result = await callProc<Extra>(fakeDb, "test.sp_cursor", fakeBuild([
      { out_sqlstate: "00000", out_sqlmsg: "0", out_sqlerrmc: "ok", out_result: "cur1" } as Extra,
    ]));
    expect(result.out_result).toBe("cur1");
  });
});
