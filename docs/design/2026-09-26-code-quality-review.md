# Code quality review — 2026-09-26

**Doc type:** platform review
**Status:** open findings. This page records the review. It does not change the code.
**Reviewed:** `main` at `9c1af3619` (2026-09-26).

A pass over structure, typing, tests, security, and the worker and scheduler. Correctness of the backtest itself is already in [Backtest review (2026-09-25)](2026-09-25-backtest-review.md). Stale stored metrics, strategy identity, and catalog visibility are already in [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md). Those are not repeated here.

This is not a decision-log entry. Adopting a fix is a later change, and a procedure or schema change still needs its own changeset.

## Summary

The tree is in better shape than a typical research repo that grew a production path. Routers are mounted behind `require_user` (or `require_user_or_service` where the scheduler Lambda must call), writes go through stored procedures, encrypted broker keys are redacted in database logs, and the UI submits backtests to the queue instead of running the grid in the browser. The unit suite plus the synthetic pipeline test is **1724 passed, 8 skipped**, and line coverage of `quant/` on that run is **87%**.

The gaps that matter are operational, not stylistic. A successful live apply whose schedule row fails to advance will **trade again** on the next tick, and the code already says there is no idempotent client order id. A worker process that dies after the loop has marked the job `RUNNING` is forgotten: the reaper logs the exit code and does not write `FAILED`, so the row stays `RUNNING` until the loop process itself restarts, and that restart fails every in-flight job, including the sibling. Python CI runs pytest and an offline Liquibase check. It does not run ruff or mypy. Both fail today. mypy's twenty errors include a real `None` dereference on the apply report. The production compose file sets `COOKIE_SECURE=0`, so the session cookie that authorizes trading is not marked Secure.

## What I ran

Dependencies came from `requirements-dev.txt`. No local Postgres was available, so the database integration tests did not run. `frontend/node_modules` was not installed, so ESLint, `tsc`, and Vitest were not run here. The `frontend` job in `.github/workflows/tests.yml` already runs all three, plus `npm audit --audit-level=high`.

| Check | Result |
|---|---|
| `python -m pytest tests/unit/ tests/integration/test_backtest_pipeline.py --cov=quant` | **1724 passed**, 8 skipped, 3 warnings, 19.7s. Line coverage of `quant/`: **6637 statements, 847 missed, 87%**. |
| `python -m ruff check quant tests scripts` (ruff 0.16.9, default rules, no config in the repo) | **327** findings. **135** are auto-fixable. The largest bucket is `B008` (103): a function call in a default argument, which is how FastAPI `Depends(...)` is written. Next: unsorted imports (46), verbose `Decimal` constructors (32), blind `except Exception` (25), unused `noqa` (17), unused imports (15). |
| `python -m mypy quant --ignore-missing-imports` (mypy 2.3.1, bodies of untyped functions not checked) | **20 errors in 9 files**, 128 source files checked. |
| `python -m pip_audit --local` | The environment that satisfies unpinned `pyjwt[crypto]` is **PyJWT 2.7.0**, flagged by `PYSEC-2025-183` and several `PYSEC-2026-*` fixed in 2.12.0 and 2.13.0. Other hits (`jinja2` 3.1.2, `pip` 24.0, `setuptools` 68.1.2, `wheel` 0.42.0) are the VM's system packages, not `requirements.txt`. `pip-audit -r requirements.txt` refuses to run because the file is unpinned. |
| `npm audit --package-lock-only` in `frontend/` | **0** vulnerabilities (info through critical). |

The three pytest warnings, confirmed on this run: Starlette says `httpx` with `TestClient` is deprecated in favor of `httpx2`; a class-scoped fixture in `tests/unit/test_scheduled_task_paths.py` is an instance method, which pytest 10 will reject; seaborn's `cmap.set_bad` is pending deprecation inside the CLI heatmap test.

`pytest-cov` is not in `requirements-dev.txt`. Coverage above was measured with a local install of the plugin. CI does not publish a coverage number.

## Findings

### 1. A successful apply can trade again if the schedule row does not advance

| | |
|---|---|
| Where | `quant/trade/scheduler/tick.py` lines 287–306 |
| What's wrong | `_advance` writes the next `PENDING` slot only after the broker call has returned success. If that write throws, the deployment stays due. The next tick applies it again. The comment on lines 298–300 says this is a re-trade, and that neither an in-flight lease nor an idempotent client order id exists. |
| Why it matters | The retry loop in `_run_one` (lines 188–218) is right for a broker error that happens *before* a fill. It is wrong for a database error *after* a fill. A second market order on the same signal doubles the position. The failure is logged at `critical`, so it is visible, and it is not prevented. |
| Direction | Give the order a client id derived from `(deployment_id, scheduled_ts)` and send that on every attempt, including the replay. Advance the schedule only after the venue has accepted that id, and treat "already filled" as success. |
| Effort | Large |
| How found | Read |

### 2. A worker that exits non-zero leaves the queue row `RUNNING`

| | |
|---|---|
| Where | `quant/queue/worker_loop.py` lines 168–188 and 192–199; `quant/queue/worker.py` lines 197–208 |
| What's wrong | The loop marks a job `RUNNING` when it spawns the child. `_reap_children` drops the child from `_active` and logs `proc.returncode`. It does not look at the code, and it does not write a terminal status. `recover_stale` (lines 168–188) is the only sweep of leftover `RUNNING` rows, and it runs on boot. `BacktestWorker.main` returns 1 when an exception escapes before `FAILED` is written (lines 203–207). The unit test `test_reaps_finished_children_before_claiming` uses exit code 0 and only asserts the child was forgotten. |
| Why it matters | Prod runs `MAX_CONCURRENT_WORKERS=2` inside one loop (`docker-compose.prod.yml` lines 31–34). One child can crash and hold a `RUNNING` row, and the slot, until the loop process restarts. That restart then fails **every** `RUNNING` row, including the sibling that was healthy. A timeout kill is handled (`_enforce_timeouts`, lines 201–230). A clean non-zero exit is not. |
| Direction | In `_reap_children`, if the exit code is non-zero, re-read the row and call `mark_terminal` only while it is still `RUNNING`. Add a test with `FakeProc(returncode=1)`. |
| Effort | Small |
| How found | Read. The missing test is visible in `tests/unit/test_worker_loop.py` around lines 192–206. Coverage of `quant/queue/worker.py` is 55%, and lines 158–210 (result write, promote, terminal update, and the crash path) are in the missed set. |

The worker also returns **0** after it has written `FAILED` itself (`quant/queue/worker.py` line 156). Exit code alone does not mean "the job succeeded". The reap has to check the row.

### 3. Python CI does not type-check or lint, and both fail

| | |
|---|---|
| Where | `.github/workflows/tests.yml` lines 10–29 (pytest only). No `ruff.toml`, `mypy.ini`, or `pyproject.toml` tool section. |
| What's wrong | Frontend CI lints, type-checks, tests, and audits (`tests.yml` lines 77–88). The Python job does not. Default ruff reports 327 findings; about a third are the FastAPI `Depends(...)` pattern and should be ignored in a config rather than "fixed". mypy reports 20 errors. One of them is a crash: `quant/trade/live_apply.py` line 205 reads `result.message` when `result` is optional. If both `message` and `result` are `None`, building the apply report raises `AttributeError` after the broker call. The same run flags untyped Redis replies as `Awaitable \| Any` in `quant/refdata/reader.py` lines 67 and 78 and `quant/trade/venue_limits.py` lines 167 and 183, and a swapped dict shape in `quant/trade/venue_limits.py` lines 71 and 84. |
| Why it matters | The live-apply bug is on the path that records a fill. The Redis errors mean the client is typed as sync-or-async, so a later `await` mistake type-checks. Without a CI gate, the next change can add either. |
| Direction | Add a ruff config that ignores `B008` on FastAPI routes, and a mypy config with `ignore_missing_imports`. Run both in the pytest job. Fix `live_apply.py` line 205 to use `result.message if result else None`. Type the Redis client as the synchronous client. |
| Effort | Medium for the gate and the Redis typing. Small for the `None` dereference. |
| How found | Ran ruff and mypy. The line 205 error is mypy `union-attr` on this commit. |

### 4. Production compose turns the Secure cookie flag off

| | |
|---|---|
| Where | `docker-compose.prod.yml` line 23 (`COOKIE_SECURE=0` on the `api` service). The flag is read in `quant/api/auth/router.py` lines 40–56. |
| What's wrong | `APP_ENV=prod` would set `Secure` on its own (`_cookie_secure`, lines 40–44). The compose file overrides that to `0`, and `SameSite` stays `lax` rather than `strict` because `strict` is tied to the Secure flag (line 56). The cookie is `HttpOnly` and scoped to `Path=/api`, which is right. It is the credential for enqueue, promotion, and live apply. |
| Why it matters | A cookie without `Secure` is sent on plain HTTP. The earlier review already recorded that the host is published. This is the cookie attribute on that deploy. |
| Direction | Terminate TLS in front of nginx and drop `COOKIE_SECURE=0`. Until then, treat the override as an explicit risk in the deploy doc, not a default copied into every environment. |
| Effort | Medium (TLS). Small to stop treating the override as normal. |
| How found | Read |

JWT verification itself is in good shape: `decode_token` pins `algorithms=["HS256"]` and the issuer (`quant/api/auth/service.py` lines 108–114). That does not retire the PyJWT advisories below; it limits which of them apply.

### 5. The synchronous optimize route is still a full grid inside the API

| | |
|---|---|
| Where | `quant/api/routers/backtest.py` lines 35–40. Client: `frontend/src/api/backtest.ts` lines 8–11. |
| What's wrong | The Backtest page enqueues (`frontend/src/pages/BacktestPage.tsx` lines 227–233). Nothing in the SPA calls `runOptimize` except `frontend/src/api/backtest.test.ts`. `POST /api/v1/backtest/optimize` is still mounted behind `require_user` and calls `run_optimize` in the API process. FastAPI runs that sync function on the thread pool. |
| Why it matters | Any logged-in caller can occupy an API thread for a large grid while the queue, the per-user cap, and the worker timeout exist specifically to prevent that. The dead client function will drift from `OptimizeRequest`. |
| Direction | Remove the route and `runOptimize`, or keep a thin handler that enqueues and returns the queue id. Leave `POST /backtest/performance`, which the page still uses to redraw a finished result. |
| Effort | Small |
| How found | Read |

`run_optimize` still swallows an inline performance failure with a warning and a `None` performance block (`quant/strategy/backtest_service.py` lines 570–575), while a walk-forward failure now sets `walk_forward_error` (lines 586–588). The earlier review asked for the failure to be visible. Half of that landed.

### 6. The money paths are the under-tested ones

| | |
|---|---|
| Where | Coverage from the run above. Lowest modules: `quant/promotion/repo.py` **41%** (misses 98–104 and 126–159), `quant/api/auth/service.py` **48%** (misses the Argon2 verify path, lines 129–151), `quant/api/auth/router.py` **46%**, `quant/queue/worker.py` **55%**, `quant/api/services/jobs.py` **56%** (cancel, re-enqueue, and promote, lines 160–224), `quant/trade/brokers/ccxt/gateway.py` **64%** (95 statements, including order submit and the private fetch helpers). |
| What's wrong | The suite is broad. The holes sit on login, the worker's completion write, promotion persistence, job cancel, and the ccxt order gateway. `quant/strategy/objective.py` and `quant/trade/scheduler/tick.py` are at 100% and 98%. |
| Why it matters | A regression in the gateway or in `ins_result` is what a green unit run would miss. Auth's dummy-hash path (constant-time login for an unknown user) is uncovered, so a change that returns early on a missing user would still pass. |
| Direction | Add unit tests that drive `BacktestWorker.run` through the result write with a fake repo, and gateway tests around submit and the `except` branches at lines 144–149. Put `--cov=quant` and a floor under the current 87% in the pytest job once `pytest-cov` is a dev dependency. |
| Effort | Medium |
| How found | Ran pytest with coverage |

### 7. `PromotionTab` re-implements ranking, and it is the largest UI file

| | |
|---|---|
| Where | `frontend/src/components/PromotionTab.tsx`, 775 lines. `compareMetric` is lines 33–40, used at lines 404, 480, and 528. The server copy is `quant/promotion/evaluate.py` `_compare`, lines 71–75. |
| What's wrong | The tab renders the promotion list, the metric-by-metric comparison, buy-and-hold, logical delete, and the deployment dialog. `compareMetric` returns 1, -1, or 0 from the same idea as `_compare`, with its own null and tie rules. The server now also reads `OOS Sharpe Ratio` and `Sharpe Excess` (`evaluate.py` lines 59–67). The tab has to stay in step by hand. |
| Why it matters | Two rankings that disagree will show a winner the gate did not pick. The file is also past the size where a metric-cell change is local. |
| Direction | Render the decision the API already returns. Split the comparison table from the deploy action. |
| Effort | Medium |
| How found | Read |

`quant/market_data/service.py` is the matching backend hotspot: 794 lines, and `PriceBarService` starts at line 148 and runs to the end of the file. Freshness, backfill planning, and the signal window are one class. Splitting it is a larger change and less urgent than the tab, because the fail-closed rule is documented at the top of the module and the file is at 99% coverage.

### 8. PyJWT is unpinned and the resolved version is behind its advisories

| | |
|---|---|
| Where | `requirements.txt` (`pyjwt[crypto]`, unpinned). Installed on this run: 2.7.0. |
| What's wrong | `pip-audit --local` reports `PYSEC-2025-183` and `PYSEC-2026-120`, `175`, `177`, and `179` against 2.7.0, with fixes in 2.12.0 and 2.13.0. The app pins the algorithm at decode time, which closes the classic "accept any `alg`" hole. It does not make 2.7.0 a version the advisory database still accepts. The earlier review already asked for pins. This is the advisory that pin would have made visible in CI. |
| Why it matters | The JWT is the session. A floor of `pyjwt[crypto]>=2.13.0` is the small move. A hash-pinned lockfile is the durable one, and it is also what lets `pip-audit -r` run. npm's lockfile already audits clean. |
| Direction | Bump PyJWT and add `pip-audit` (or an equivalent) to the Python job once requirements are pinned tightly enough for it to run. |
| Effort | Small for the floor. Medium for a hashed lock. |
| How found | Ran `pip-audit --local` and `npm audit --package-lock-only` |

### 9. A few failures are swallowed with no record

| | |
|---|---|
| Where | `quant/strategy/optimizer.py` lines 79–114 (`except Exception: pass` around every Optuna plot). `quant/api/auth/service.py` lines 149–150 (`except Exception: pass` on the rehash check). `quant/api/main.py` lines 183–185 (`/health/ready` returns `str(exc)` with no auth). |
| What's wrong | A plot that fails disappears from the result with no log line, so a missing contour looks like "Optuna had nothing to draw". The rehash check failing is also silent, so a hash that should be rotated never is. Readiness is unauthenticated and puts the database exception text in the JSON body. |
| Why it matters | The plot case hides a broken optional dependency. The readiness case is a small information leak (host, auth failure, timeout) on a public health URL. Login's own failure path is better: lines 135–137 log and return `None`. |
| Direction | Log the plot and rehash failures at warning. Return `{"status": "degraded", "db": "unavailable"}` from readiness and keep `str(exc)` in the log line that is already there. |
| Effort | Small |
| How found | Read. Ruff `S110` flags the `pass` sites. |

### 10. Small cleanups

| | |
|---|---|
| Where | `quant/queue/worker.py` line 189 still says `python -m src.worker`. `quant/cli.py` line 55 imports `NasdaqDataLink` and does not use it. `quant/trade/live_apply.py` lines 5 and 8 import `functools` and `timedelta` unused. `frontend/package.json` still depends on `tailwindcss` and `@tailwindcss/vite`; no `frontend/src` file references Tailwind. There is no Makefile. `scripts/setup.sh` and `docs/getting-started.md` are the setup path. |
| What's wrong | Stale entry points and unused imports. Tailwind is install weight and a lint surface the frontend audit already called out; it is still in the lockfile. |
| Why it matters | The usage string is what a failing worker prints. The rest is noise that a ruff job (finding 3) would delete. |
| Direction | Fix the usage string with the reap change. Let ruff remove the unused imports. Drop Tailwind in a frontend change if the audit follow-up is still wanted. |
| Effort | Small |
| How found | Ruff `F401` for the Python imports. Tailwind: searched `frontend/src` and found no uses. |

## What is already in good shape

- **Authz on routers.** `quant/api/main.py` lines 154–169 mount every data router behind `require_user`, and the three Lambda-facing routers behind `require_user_or_service`. Market-data mutations add `require_user` again on the route (`quant/api/market_data/router.py`).
- **Database access.** `DbGateway` borrows a pooled connection per call and commits or rolls back with the pool context (`quant/shared/db.py` lines 152–158). Fernet tokens are redacted before they reach a log line (lines 99–125). Application code calls procedures rather than writing SQL.
- **Worker isolation.** One subprocess per job, a timeout kill that does write `FAILED`, and cancel that the loop now observes (`worker_loop.py` `_enforce_cancels`). Two children in one loop is the supported shape. Two *loop* processes are not: `recover_stale` would steal the other loop's jobs (lines 171–176). Prod is one container.
- **Frontend CI.** Lint, `tsc`, Vitest, and `npm audit` already run. `tsconfig.app.json` keeps `strict: true`.
- **Login rate limit.** `POST /auth/login` is `5/15minutes` (`quant/api/auth/router.py` line 72), and an unknown username still pays for an Argon2 verify.

The CI gap the earlier review noted for `tests/integration/test_backtest_pipeline.py` is closed: `tests.yml` line 29 runs it with the unit suite.

## Top 5 to do first

1. **Stop a filled order from being sent again** when the schedule advance fails (`quant/trade/scheduler/tick.py` lines 297–300). This is the live-trading bug.
2. **Reap a non-zero worker exit into `FAILED`** while the row is still `RUNNING` (`quant/queue/worker_loop.py` lines 192–199), and test exit code 1.
3. **Run ruff and mypy in the Python CI job**, and fix `quant/trade/live_apply.py` line 205 in that same change. Set a PyJWT floor of 2.13.0 while the requirements pin is still open.
4. **Turn the session cookie's Secure flag back on** (`docker-compose.prod.yml` line 23) once TLS terminates in front of the API. Do not keep `COOKIE_SECURE=0` as the production default.
5. **Remove `POST /backtest/optimize`** (and `runOptimize`), and add a unit test for the worker's result-write path. That is the uncovered half of the queue.
