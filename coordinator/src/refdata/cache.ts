import { sql, callProc, type SpResult } from "../db/client";
import {
  getRedis,
  REFDATA_INVALIDATE_CHANNEL,
  REFDATA_KEY,
  REFDATA_VERSION_KEY,
} from "../redis/client";

export class RefDataCache {
  private store = new Map<string, Record<string, unknown>[]>();
  private async discoverTables(): Promise<string[]> {
    const rows = await sql<{ table_name: string }[]>`
      SELECT table_name
        FROM information_schema.tables
       WHERE table_schema = 'refdata'
         AND table_type   = 'BASE TABLE'
         and table_name NOT IN ('databasechangelog', 'databasechangeloglock')
       ORDER BY table_name
    `;
    return rows.map((r) => r.table_name);
  }

  /** CALL refdata.sp_get_enum(table) → drain refcursor → return rows. */
  private async fetchEnum(table: string): Promise<Record<string, unknown>[]> {
    return sql.begin(async (tx) => {
      const out = await callProc<SpResult & { out_result: string }>(
        tx,
        "refdata.sp_get_enum",
        (db) => db`CALL refdata.sp_get_enum(${table}, NULL, NULL, NULL, NULL)`,
      );
      const cursorName = out.out_result;
      // FETCH ALL FROM "<cursor>" — name is dynamic, use unsafe with quoting
      const rows = await tx.unsafe<Record<string, unknown>[]>(
        `FETCH ALL FROM "${cursorName.replace(/"/g, '""')}"`,
      );
      // Cursor closes automatically when the tx ends.
      return rows;
    });
  }

  async load(): Promise<void> {
    const tables = await this.discoverTables();
    const next = new Map<string, Record<string, unknown>[]>();
    for (const t of tables) {
      try {
        const rows = await this.fetchEnum(t);
        next.set(t, rows);
      } catch (err) {
        console.warn(`[refdata] failed to load ${t}:`, err);
        next.set(t, []);
      }
    }
    this.store = next;
    console.info(
      `[refdata] loaded ${next.size} tables: ${[...next.keys()].sort().join(", ")}`,
    );
    await this.publish();
  }

  /** Push the in-memory snapshot to Redis so Python readers see the same data.
   *
   * Coordinator is the *only* writer to these keys. FastAPI / workers only
   * GET. A pipeline keeps the per-table SETs and the version bump atomic
   * from the writer's perspective (one round-trip).
   */
  private async publish(): Promise<void> {
    let redis;
    try {
      redis = await getRedis();
    } catch (err) {
      console.warn("[refdata] redis unavailable, skipping publish:", err);
      return;
    }
    const tx = redis.multi();
    for (const [table, rows] of this.store) {
      tx.set(REFDATA_KEY(table), JSON.stringify(rows));
    }
    tx.incr(REFDATA_VERSION_KEY);
    await tx.exec();
    // Best-effort fan-out for long-lived subscribers (FastAPI). Workers
    // re-read on every spawn, so they don't need the channel.
    await redis.publish(REFDATA_INVALIDATE_CHANNEL, "*");
    console.info(`[refdata] published ${this.store.size} tables to redis`);
  }

  /** Generic accessor — used by GET /api/v1/refdata/:table later. */
  raw(table: string): Record<string, unknown>[] {
    if (!this.store.has(table)) {
      throw new Error(`Unknown REFDATA table: ${table}`);
    }
    const rows = this.store.get(table)!;
    if (rows.length === 0) {
      throw new Error(`REFDATA.${table.toUpperCase()} is empty`);
    }
    return rows;
  }

  /** Look up an integer ID by NAME column.
   *  e.g. idByName("queue_status", "QUEUED", "queue_status_id") → 1 */
  idByName(table: string, name: string, idCol: string): number {
    const hit = this.raw(table).find((r) => r["name"] === name);
    if (!hit) {
      const known = this.raw(table).map((r) => r["name"]).join(", ");
      throw new Error(`REFDATA.${table} has no name=${name} (known: ${known})`);
    }
    return Number(hit[idCol]);
  }
  /** List loaded table names — for the future refresh/list endpoint. */
  tables(): string[] {
    return [...this.store.keys()].sort();
  }
}

export const refdata = new RefDataCache();
