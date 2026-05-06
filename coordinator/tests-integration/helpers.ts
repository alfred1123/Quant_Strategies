// Shared helpers for integration tests.
import { sql } from "../src/db/client";

/** Stable user-id for all integration test rows — makes cleanup trivial. */
export const TEST_USER_ID = "__integration_test__";

/** Generate a random UUID for test rows (Bun has crypto.randomUUID globally). */
export const newUuid = (): string => crypto.randomUUID();

let dbAvailable: boolean | null = null;

/**
 * Returns true if the DB pings within ~3s. Cached after first call so we
 * don't pay the timeout on every test.
 */
export async function isDbAvailable(): Promise<boolean> {
  if (dbAvailable !== null) return dbAvailable;
  try {
    await Promise.race([
      sql`SELECT 1`,
      new Promise((_, rej) => setTimeout(() => rej(new Error("ping timeout")), 3000)),
    ]);
    dbAvailable = true;
  } catch {
    dbAvailable = false;
  }
  return dbAvailable;
}

/** Delete every BT.QUEUE row owned by the test user (all VIDs). */
export async function cleanQueueRows(): Promise<void> {
  await sql`DELETE FROM bt.queue WHERE user_id = ${TEST_USER_ID}`;
}
