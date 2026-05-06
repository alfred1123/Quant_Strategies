// Integration-test bootstrap.
//
// Loaded once via bunfig.toml -> [test.integration] preload. Reads the
// project-root `.env` so QUANTDB_URL points at the live DB (localhost:5433
// via SSM tunnel, same target the coordinator uses at runtime).
//
// If the DB is not reachable, individual tests use `skipIfNoDb()` from
// helpers.ts to bail out gracefully — this lets the suite pass when the
// SSM tunnel is down (e.g. on CI without AWS creds).

import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const envPath = resolve(import.meta.dir, "..", "..", ".env");
if (existsSync(envPath)) {
  const text = readFileSync(envPath, "utf8");
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const noExport = line.startsWith("export ") ? line.slice(7) : line;
    const eq = noExport.indexOf("=");
    if (eq < 1) continue;
    const key = noExport.slice(0, eq).trim();
    let val = noExport.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    // Don't overwrite values already set in the shell.
    if (process.env[key] === undefined) process.env[key] = val;
  }
}

// Sanity defaults so config.ts doesn't throw if .env is missing entirely.
process.env["JWT_SECRET"] ??= "integration-test-secret";
