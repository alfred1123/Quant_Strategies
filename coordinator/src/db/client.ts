import postgres, { type Sql, type TransactionSql, type PendingQuery, type Row } from "postgres";
import { config } from "../config";

/** Either the pool (`sql`) or a transaction handle (`tx` from `sql.begin`). */
export type SqlExecutor = Sql | TransactionSql;

/** Shared connection pool. */
export const sql: Sql = postgres(config.QUANTDB_URL, {
  max: 5,
  idle_timeout: 30,
  connect_timeout: 10,
  ssl: "require",
});

// ── Stored procedure helpers ──────────────────────────────────────────────────

/** Standard OUT params returned by every BT/REFDATA stored procedure. */
export interface SpResult {
  out_sqlstate: string;
  out_sqlmsg: string;
  out_sqlerrmc: string;
}

/** Thrown when a stored procedure returns a non-00000 SQLSTATE. */
export class StoredProcedureError extends Error {
  constructor(
    public readonly proc: string,
    public readonly sqlstate: string,
    public readonly sqlerrmc: string,
  ) {
    super(`${proc} failed (SQLSTATE ${sqlstate}): ${sqlerrmc}`);
    this.name = "StoredProcedureError";
  }
}

/**
 * Execute a CALL and throw StoredProcedureError on non-00000 SQLSTATE.
 *
 * The caller passes a `build(db)` callback that receives either the pool
 * (`sql`) or a transaction handle (`tx` from `sql.begin`) and returns the
 * tagged-template `CALL ...` query. This lets the same proc call be issued
 * inside or outside a transaction without changing the repo function:
 *
 *   await callProc<SpResult>(sql, "bt.sp_ins_queue", (db) => db`CALL ...`);
 *
 *   await sql.begin(async (tx) => {
 *     await callProc<SpResult>(tx, "bt.sp_ins_queue",  (db) => db`CALL ...`);
 *     await callProc<SpResult & { out_result_id: number }>(
 *       tx, "bt.sp_ins_result", (db) => db`CALL ...`,
 *     );
 *   });
 *
 * The generic `T` lets callers extract extra OUT params (e.g. `out_result_id`,
 * `out_strategy_vid`) returned by procs beyond the standard SpResult shape.
 */
export async function callProc<T extends SpResult = SpResult>(
  db: SqlExecutor,
  proc: string,
  build: (db: SqlExecutor) => PendingQuery<Row[]>,
): Promise<T> {
  const rows = (await build(db)) as unknown as T[];
  const result = rows[0];
  if (!result) {
    throw new StoredProcedureError(proc, "NO_RESULT", `${proc} returned no result row`);
  }
  if (result.out_sqlstate !== "00000") {
    throw new StoredProcedureError(proc, result.out_sqlstate, result.out_sqlerrmc);
  }
  return result;
}