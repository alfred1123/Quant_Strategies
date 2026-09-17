# Database connections

How Python talks to Postgres: one process-wide pool, borrow and return on
every stored-procedure call.

See [Pipeline](../architecture/pipeline.md) for the `DbGateway` surface and
[decision #69](../decisions.md) for the log entry.

## The rule

Each **process** (API, `worker_loop`, one backtest worker) owns **one**
`psycopg_pool.ConnectionPool` per conninfo. A `DbGateway` subclass borrows a
connection for `_call_get` / `_call_write` / `_query` and returns it. Gateways
do not hold sockets and have no `close()`.

```
request / tick / worker step
  → DbGateway._run
  → pool.connection()     # borrow
  → CALL schema.procedure(...)
  → return to pool        # commit on success, rollback on error
```

Entry points call `open_pool(conninfo)` at boot so a down database fails the
process instead of the first request, and `close_pools()` on shutdown.

## What was rejected

| Shape | Why it failed |
|---|---|
| **`persistent=True` — one socket per cache, never returned** | `InstrumentCache`, `BacktestCache`, and `PriceBarRepo` each held a session for the process lifetime. Aurora idle timeout and `SP_TERM_STALE_CONNECTIONS` dropped the backend; the next dry-run failed with `the connection is lost`. |
| **Connect-per-call (`with psycopg.connect`)** | Disconnect was correct, but a dry-run that hits five procedures paid five handshakes. [Login §7.2](login.md#72-postgres-roles-vs-application-users-two-identity-layers) already described a pool. |
| **Reconnect-once on `OperationalError`** | A bandage on the persistent path. It hid a dead socket for one retry and left idle sessions unmanaged. |
| **A pool per gateway instance** | Per-request `TradeRepo` / `AuthRepo` would each open their own pool. The process reuses sockets, not the object. |
| **PgBouncer / RDS Proxy now** | One API replica + one worker loop stay well under Aurora `max_connections` at `max_size=10` each. Add a proxy when replica count grows. |

## Pool policy

Defaults, overridable via env ([Environment Variables](../env-vars.md)):

| Setting | Default | Why |
|---|---|---|
| `min_size` | 2 | Fail the boot if the database is down; keep one spare. |
| `max_size` | 10 | Cap per process. |
| `max_idle` | 600s | Extra connections above `min_size` close after ten idle minutes. |
| `max_lifetime` | 1800s | Recycle before the hourly stale-session sweeper (3600s). |
| `check` | `ConnectionPool.check_connection` | `SELECT 1` on checkout when the socket has been sitting. A killed backend is discarded and replaced. |
| `timeout` | 30s | Wait this long for a free slot. |

`/health/ready` uses the same pool (`DbGateway.health_check`). A side-channel
`psycopg.connect` would report ready while the pool was wedged.

## Who opens and closes

| Process | Opens | Closes |
|---|---|---|
| FastAPI | `lifespan` | `lifespan` `finally` |
| `quant.queue.worker_loop` | `main()` | `main()` `finally` |
| `quant.queue.worker` | `main()` | `main()` `finally` |
| `RefDataPublisher` CLI | `main()` | `main()` `finally` |

A worker is a new process (`subprocess.Popen`), so it does not inherit the
loop's pool.

## Stale-session sweeper

`SP_TERM_STALE_CONNECTIONS` still terminates `quant_app` backends idle longer
than one hour. That is a backstop for leaked scripts and killed processes.
The pool recycles its own sockets via `max_lifetime` and `check`.

## Identity

Unchanged from [Login §7.2](login.md#72-postgres-roles-vs-application-users-two-identity-layers):
every pooled connection logs in as `quant_app`. The human is `IN_USER_ID` on
the procedure call.
