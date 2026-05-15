import { config } from "../config";
import { refdata } from "../refdata/cache";
import { claimNext, type ClaimedJob } from "./repo";

/**
 * Wakeup-driven queue manager (docs/design/backtest-queue.md §9.3).
 *
 * Single in-process channel: `wake()` sets a flag and resolves the gate
 * promise, `tick()` drains it. While the loop is busy, additional `wake()`
 * calls coalesce into one re-run after the current iteration finishes.
 *
 * Slice C scope: claim QUEUED → spawn worker → wait for exit → loop.
 * The supervisor is injected so tests can stub the spawn step.
 */
export type SpawnFn = (job: ClaimedJob) => Promise<number>; // resolves with worker exit code

export class Manager {
  private readonly maxWorkers: number;
  private active = 0;
  private pendingWake = false;
  private gate: { promise: Promise<void>; resolve: () => void } = this.makeGate();
  private running = false;
  private loopPromise: Promise<void> | null = null;

  constructor(private readonly spawn: SpawnFn, maxWorkers: number = config.MAX_WORKERS) {
    this.maxWorkers = maxWorkers;
  }

  /** Start the event loop. Idempotent. */
  start(): void {
    if (this.running) return;
    this.running = true;
    this.loopPromise = this.loop().catch((err) => {
      console.error("[manager] loop crashed:", err);
      this.running = false;
    });
  }

  /** Stop accepting new ticks. Active workers keep running. */
  async stop(): Promise<void> {
    this.running = false;
    this.wake(); // unblock the gate so loop() exits
    if (this.loopPromise) await this.loopPromise;
  }

  /** Signal that something may be claimable (HTTP enqueue, worker exit, watchdog). */
  wake(): void {
    this.pendingWake = true;
    this.gate.resolve();
  }

  // ── internal ────────────────────────────────────────────────────────────────

  private makeGate(): { promise: Promise<void>; resolve: () => void } {
    let resolve!: () => void;
    const promise = new Promise<void>((r) => (resolve = r));
    return { promise, resolve };
  }

  private async loop(): Promise<void> {
    while (this.running) {
      await this.gate.promise;
      this.gate = this.makeGate();
      this.pendingWake = false;
      try {
        await this.tick();
      } catch (err) {
        console.error("[manager] tick error:", err);
      }
      // If wake() fired during tick, loop again immediately.
      if (this.pendingWake) this.gate.resolve();
    }
  }

  /** One iteration: claim and spawn while slots are free. */
  private async tick(): Promise<void> {
    while (this.running && this.active < this.maxWorkers) {
      const queuedStatusId  = refdata.idByName("queue_status", "QUEUED",  "queue_status_id");
      const runningStatusId = refdata.idByName("queue_status", "RUNNING", "queue_status_id");
      const job = await claimNext(queuedStatusId, runningStatusId);
      if (!job) return;
      this.active += 1;
      // Fire-and-forget; on exit, free the slot and re-wake.
      this.runJob(job).finally(() => {
        this.active -= 1;
        this.wake();
      });
    }
  }

  private async runJob(job: ClaimedJob): Promise<void> {
    try {
      const exitCode = await this.spawn(job);
      if (exitCode !== 0) {
        // Slice C minimum: log only. Slice D adds coordinator-side FAILED write
        // when worker died without writing terminal state.
        console.warn(`[manager] worker for ${job.queue_id} exited with code ${exitCode}`);
      }
    } catch (err) {
      console.error(`[manager] worker for ${job.queue_id} threw:`, err);
    }
  }
}

