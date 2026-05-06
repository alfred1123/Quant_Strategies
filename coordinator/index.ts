import {config} from "./src/config";
import {sql} from "./src/db/client";
import {refdata} from "./src/refdata/cache";
import {app} from "./src/http/server";

async function main() {
  console.info("[boot] starting coordinator...");

  // Ping DB 
  console.info("[boot] checking database connectivity...");
  await sql`SELECT 1`;

  // Load REFDATA cache 
  console.info("[boot] loading REFDATA cache...");
  await refdata.load();

  // Start HTTP server
  console.info(`[boot] starting HTTP server on port ${config.PORT}...`);
  Bun.serve({
    port: config.PORT,
    fetch: app.fetch,
  });
}

main().catch((err) => {
  console.error("[boot] failed to start coordinator:", err);
  process.exit(1);
});
