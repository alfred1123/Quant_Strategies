import { config } from "./src/config";
import { sql } from "./src/db/client";
import { refdata } from "./src/refdata/cache";
import { createApp } from "./src/http/server";
import { Manager } from "./src/queue/manager";
import { pythonSpawn } from "./src/queue/spawn";
import { createJobsService } from "./src/services/jobs";

async function main() {
  console.info("[boot] starting coordinator...");

  // Ping DB
  console.info("[boot] checking database connectivity...");
  await sql`SELECT 1`;

  // Load REFDATA cache
  console.info("[boot] loading REFDATA cache...");
  await refdata.load();

  // Wire layers: repo → service → http. Manager is the only collaborator
  // shared between the queue loop and the enqueue service.
  console.info("[boot] starting queue manager...");
  const manager = new Manager(pythonSpawn);
  const jobs = createJobsService(manager);
  const app = createApp({ jobs });
  manager.start();
  manager.wake(); // pick up any rows already QUEUED from a previous run

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

