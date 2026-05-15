import { config } from "../config";
import type { ClaimedJob } from "./repo";
import type { SpawnFn } from "./manager";

/**
 * Spawn one Python worker per claimed job. Worker contract:
 * docs/design/backtest-queue.md §10 — newline-JSON events on stdout,
 * exit code 0 = terminal state written to DB.
 */
export const pythonSpawn: SpawnFn = async (job: ClaimedJob): Promise<number> => {
  const proc = Bun.spawn(
    [config.PYTHON_BIN, "-m", "quant.queue.worker", job.queue_id],
    {
      cwd: config.REPO_ROOT,
      stdout: "pipe",
      stderr: "inherit",
      env: {
        ...process.env,
        // Worker reads QUANTDB_* / REDIS_URL exactly like the API does.
      },
    },
  );

  // Drain stdout line-by-line so the pipe doesn't fill and block the worker.
  // Slice D will fan these out via SSE; Slice C just logs.
  // IIFE keeps the drain running concurrently with `await proc.exited`
  // below, so we don't have to choose between draining and waiting.
  (async () => {
    const decoder = new TextDecoder();
    let buf = "";
    for await (const chunk of proc.stdout as ReadableStream<Uint8Array>) {
      buf += decoder.decode(chunk, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) console.info(`[worker ${job.queue_id}] ${line}`);
      }
    }
  })().catch((err) => console.error(`[spawn] stdout drain failed:`, err));

  return await proc.exited; // number
};
