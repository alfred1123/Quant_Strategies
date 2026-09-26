# Code quality review — 2026-09-26

**Doc type:** platform review
**Status:** open findings. This page records the review. It does not change the code.
**Reviewed:** `main` at `9c1af3619` (2026-09-26).

A pass over structure, typing, tests, security, and the worker and scheduler. Correctness of the backtest itself is already in [Backtest review (2026-09-25)](2026-09-25-backtest-review.md). Stale stored metrics, strategy identity, and catalog visibility are already in [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md). Those are not repeated here.

This is not a decision-log entry. Adopting a fix is a later change, and a procedure or schema change still needs its own changeset.

## Summary

The tree is in better shape than a typical research repo that grew a production path. Routers are mounted behind `require_user` (or `require_user_or_service` where the scheduler Lambda must call), writes go through stored procedures, encrypted broker keys are redacted in database logs, and the UI submits backtests to the queue instead of running the grid in the browser. The unit suite plus the synthetic pipeline test is **1724 passed, 8 skipped**, and line coverage of `quant/` on that run is **87%**.

The gaps that matter are operational, not stylistic. A successful live apply whose schedule row fails to advance will **trade again** on the next tick, and the code already says there is no idempotent client order id. A worker process that dies after the loop has marked the job `RUNNING` is forgotten: the reaper logs the exit code and does not write `FAILED`, so the row stays `RUNNING` until the loop process itself restarts, and that restart fails every in-flight job, including the sibling. Python CI runs pytest and an offline Liquibase check. It does not run ruff or mypy. Both fail today. mypy's twenty errors include a real `None` dereference on the apply report. The production compose file sets `COOKIE_SECURE=0`, so the session cookie that authorizes trading is not marked Secure.

The object model is uneven, and that is what blocks the next research work. Brokers already have a substitutable `TradeAdapter`, a registry, and a `CcxtVenue` subclass per exchange. Indicators and signals do not. A strategy is two strings (`get_bollinger_band`, `momentum_band_signal`) resolved with `getattr` on `TechnicalAnalysis` and `SignalDirection`. The same resolution is copied in `Performance` and in `Objective`. A Donchian channel, a trailing stop, or a position size that is not −1/0/+1 cannot be added as a new class. Each one edits those two engines, and a channel indicator also has to notice that the multi-factor path throws away High and Low. [OOP Strategy Framework](../architecture/oop-framework.md) already draws the target (`Strategy`, `Indicator`, `ExecutionModel`). That page says the procedural modules are still production. This review measures that gap. It does not propose building the `on_bar` engine first.

## What I ran

Dependencies came from `requirements-dev.txt`. No local Postgres was available, so the database integration tests did not run. `frontend/node_modules` was not installed, so ESLint, `tsc`, and Vitest were not run here. The `frontend` job in `.github/workflows/tests.yml` already runs all three, plus `npm audit --audit-level=high`.

| Check | Result |
|---|---|
| `python -m pytest tests/unit/ tests/integration/test_backtest_pipeline.py --cov=quant` | **1724 passed**, 8 skipped, 3 warnings, 19.7s. Line coverage of `quant/`: **6637 statements, 847 missed, 87%**. |
| `python -m ruff check quant tests scripts` (ruff 0.16.9, default rules, no config in the repo) | **327** findings. **135** are auto-fixable. The largest bucket is `B008` (103): a function call in a default argument, which is how FastAPI `Depends(...)` is written. Next: unsorted imports (46), verbose `Decimal` constructors (32), blind `except Exception` (25), unused `noqa` (17), unused imports (15). |
| `python -m mypy quant --ignore-missing-imports` (mypy 2.3.1, bodies of untyped functions not checked) | **20 errors in 9 files**, 128 source files checked. |
| `python -m pip_audit --local` | The environment that satisfies unpinned `pyjwt[crypto]` is **PyJWT 2.7.0**, flagged by `PYSEC-2025-183` and several `PYSEC-2026-*` fixed in 2.12.0 and 2.13.0. Other hits (`jinja2` 3.1.2, `pip` 24.0, `setuptools` 68.1.2, `wheel` 0.42.0) are the VM's system packages, not `requirements.txt`. `pip-audit -r requirements.txt` refuses to run because the file is unpinned. |
| `npm audit --package-lock-only` in `frontend/` | **0** vulnerabilities (info through critical). |
| `python -m radon cc quant` (radon 6.0.1, 966 blocks) | Average complexity **A (2.51)**. Ranks: **A 892, B 63, C 11**, nothing at D or above. The eleven C blocks are listed under [Object-oriented design](#object-oriented-design). |
| `python -m radon mi quant` | **128** files. Median maintainability index **74**. Worst: `quant/trade/brokers/ccxt/gateway.py` **32.9**, `quant/strategy/optimizer.py` **38.3**, `quant/strategy/performance.py` **38.9**. Radon's low band starts at 19. No file is in it. Size, not branching, is the hotspot. |
| Import graph (AST walk of `quant/**/*.py`; `pydeps` and `import-linter` are not installed) | **190** classes. **0** module cycles. The upward edges are listed under [Boundaries](#boundaries). |

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

## Object-oriented design

The production strategy path is the procedural one named in [OOP Strategy Framework](../architecture/oop-framework.md): `TechnicalAnalysis`, `signals.py`, and `optimizer.py`. The trade path is further along. `SearchStrategy`, `Objective`, `TradeAdapter`, and `CcxtVenue` are real extension points. The research work that is next (a Donchian channel, a stateful stop, a size that is not a full unit) lands on the path that does not have one.

### What the numbers say

Measured on this commit with radon and an AST walk. Not estimated.

| Measure | Result |
|---|---|
| Blocks (functions, methods, classes) | 966. Average cyclomatic complexity **2.51** (rank A). **892** rank A, **63** rank B, **11** rank C. No rank D, E, or F. |
| Rank C (complexity 11–20) | `TradeService.update_deployment` 13 (`quant/trade/service.py:218`), `FutuTrader.apply_signal` 13 (`quant/trade/futu_trader.py:231`), `_parse_terminal` 13 (`quant/trade/brokers/ccxt/confirm.py:36`), `OptimizeResult.extract_plots` 12 (`quant/strategy/optimizer.py:64`), `fetch_df` 12 (`quant/strategy/backtest_service.py:170`), `KeyRouter.connect` 12 (`quant/trade/brokers/ccxt/routing.py:62`), and five at 11: `Performance.__init__`, `OrderRetryPolicy.is_retryable`, `CcxtTradeAdapter.place_order`, `CcxtTradeGateway.fetch_open_positions`, `_extract_metric`. |
| Maintainability index | Median **74** across 128 files. Lowest three: gateway **32.9** (428 lines), optimizer **38.3** (354), `performance.py` **38.9** (393). All still above radon's "low" cutoff of 19. |
| Largest classes | `PriceBarService` **647** lines, 19 methods (`quant/market_data/service.py:148`). `TradeRepo` **586** lines, 23 methods (`quant/trade/db_repo.py:33`). `CcxtTradeGateway` **364** lines, 25 methods (`quant/trade/brokers/ccxt/gateway.py:64`). `TradeService` **363** lines, 17 methods (`quant/trade/service.py:37`). `Performance` **292** lines, 27 methods (`quant/strategy/performance.py:99`). |
| Import cycles | **0** among `quant` modules. |

Complexity is not the reason a new indicator is hard. The reason is that the behavior lives in two classes addressed by string, and a second engine repeats the call.

### Responsibilities

**`TechnicalAnalysis` is a namespace, not a strategy object.** The class (`quant/strategy/indicators.py:12`) holds a DataFrame and exposes five methods: `get_sma`, `get_ema`, `get_rsi`, `get_bollinger_band`, `get_stochastic_oscillator` (lines 23–64). Nothing else in the platform implements an indicator. Callers do not receive an indicator. They `getattr` a method name:

- `quant/strategy/performance.py:185` and `:200` and `:214`
- `quant/strategy/objective.py:33`

That violates open/closed. Adding Donchian means editing `TechnicalAnalysis`. It does not mean adding a class. The five methods also do not share an interface beyond "takes a period and returns a Series". Stochastic reads `High`, `Low`, and `Close` (lines 54–63). The others read `factor`. A channel indicator is in the stochastic family, and the multi-factor helper does not pass that family what it needs (below).

**`SignalDirection` is the same shape for signals.** Eight static methods (`quant/strategy/signals.py:235–305`) all have the signature `(data_col, signal) -> ndarray` of −1, 0, or +1. `resolve_signal_func` (lines 312–335) picks `FUNC_NAME_BAND` or `FUNC_NAME_BOUNDED` from REFDATA and `getattr`s it. `SubStrategy.resolve_signal_func` (lines 37–39) does the same. [Adding Strategies](../guides/adding-strategies.md) tells the reader to add a method to this class. A trailing stop or a hysteresis band is not a function of one indicator value and one threshold. It needs the price path and the previous position. The signature cannot express it, so the guide's steps do not cover the research team's next signal.

**`Performance` and `Objective` are two engines.** `quant/strategy/objective.py:1–6` calls itself a twin of `Performance`: one returns a Sharpe, the other returns the curve, and both compute the indicator and the position. `Objective._validate_factor_coverage` (lines 103–116) is the same 80% rule as `Performance`. A behavior change that lands in one and not the other is how a column bug gets a second copy. Single responsibility would put "indicator then position" in one object both of them call. Today it is inlined in `_compute_single_factor_outputs` (`performance.py:190`), `_indicator_and_position` (`performance.py:176`), `SingleFactorObjective` (`objective.py:119`), and `MultiFactorObjective`.

**`Performance` itself mixes four jobs.** Construction normalizes window tuples (`performance.py:106`, complexity 11). The middle of the class builds indicators and positions. The rest computes PnL, Sharpe, drawdown, and the latest live position (`compute_latest_position`, line 156). Live apply depends on that last method through `quant/strategy/live_service.py:211`. A sizing change inside `_compute_pnl_columns` changes the number the scheduler trades. That coupling is why a refactor of this class is not a drive-by.

**`PriceBarService` is the widest class, and it is one service.** 647 lines from `quant/market_data/service.py:148`: freshness (`ensure_fresh`), backfill, coverage, and the window a signal is allowed to see. The module docstring (lines 1–15) states the rule that holds it together: fail closed when a signal window has holes, and tolerate holes on a maintenance backfill. Splitting it into four classes would not make Donchian easier. It is a size problem, and the file is at 99% coverage, so a split is safe later and useless first.

**`TradeRepo` is wide and single-purpose.** 586 lines, 23 methods, each a stored-procedure wrapper (`quant/trade/db_repo.py:33`). That is a catalog, not a god object. Leaving it alone is the right call.

**`CcxtTradeGateway` mixes transport and interpretation.** 364 lines, 25 methods (`quant/trade/brokers/ccxt/gateway.py:64`). It constructs the ccxt exchange, paginates, and parses balances and positions (the rank-C method is `fetch_open_positions` at line 336). The adapter above it is the seam. The gateway is not.

**`TradeService` is an application service that grew policy.** The constructor (`quant/trade/service.py:40–65`) takes its collaborators, which is the right shape, and then builds a `LiveApplyOrchestrator` with the same seven arguments. `update_deployment` (line 218, complexity 13) is the rank-C method: schedule alignment, enablement, and persistence in one function. `LiveApplyOrchestrator` (`quant/trade/live_apply.py:37`) is 288 lines with one public method. The privacy is good. The orchestrator still sequences credentials, bars, the signal, the order, and two audit writes.

**`fetch_df` is a switch, not a source object.** `quant/strategy/backtest_service.py:170` (complexity 12) branches on `data_source` and, for a provider, does `getattr` on a class name from REFDATA (line 236). A new vendor source is another branch in this function plus a class in `quant/data/sources.py`. Exchange bars already bypass it through `bar_services`. The branch is the closed part.

What is already open/closed, and should be the pattern for indicators:

- `SearchStrategy` with `ExhaustiveSearch` and `BayesianSearch` (`quant/strategy/optimizer.py:173`, `:194`, `:227`).
- `Objective.for_config` picking `SingleFactorObjective` or `MultiFactorObjective` (`quant/strategy/objective.py:60–68`).
- `CcxtVenue` / `BybitVenue` (`quant/trade/brokers/ccxt/config.py:38` and `:64`). A venue overrides `wire` and `classify_denial`. The gateway does not grow an `if exchange == "bybit"`.
- `AdapterRegistry` (`quant/trade/registry.py:22`).

### Boundaries

No module imports itself through a cycle. The layering violations are upward imports, measured by counting `from quant.<package>` edges.

| Edge | Count | What it is |
|---|---|---|
| `trade` → `api` | 8 imports in 4 files | `quant/trade/service.py:8–9`, `dry_run.py:8–9`, `live_apply.py:11–12`, `account.py:14–15` import `ApiCredentialRepo` and `CredentialService` from `quant.api.credentials`. The broker stack depends on the HTTP package. |
| `schemas` → `trade` | 3 | `quant/schemas/apply.py:7` and `quant/schemas/dry_run.py:8–9` import `IntendedAction`, `OrderRejectReason`, and `KeyProfile` from `quant.trade.models`. HTTP schemas depend on the trade package. The types are domain enums. They live on the wrong side of the line. |
| `refdata` → `trade` | 2 | `quant/refdata/bundle.py:12–13` imports `RedisKeyProfiles` and `RedisVenueLimits`. The cache bundle knows about broker caches. |
| `market_data` → `strategy` | 1 | `quant/market_data/warm.py:37` imports `live_lookback_bars` from `Performance`'s module. A bar warmer depends on the backtest engine for a window length. |
| `queue` → `promotion` and `promotion` → `queue` | 1 each | `quant/queue/worker.py:40` imports `PromotionRepo`. `quant/promotion/repo.py:15` imports `BtQueueRepo`. Not a cycle: promotion does not import the worker. It is the composition the repo rules ask for (one owner of `sp_get_strategy`). |

`strategy` does not import `trade` or `api`. A signal cannot see a broker. That boundary is intact, and it should stay intact. The leak is the other way: live evaluation is a function in `quant/strategy/live_service.py` that the trade stack calls, and that function's only implementation is `Performance`.

Routers are thin. `quant/api/routers/backtest.py` calls `run_optimize` / `run_performance` / `run_walk_forward`. `quant/api/routers/deployments.py` builds a `TradeService`. They do not open cursors. `DbGateway` subclasses (`TradeRepo`, `BtQueueRepo`, `PriceBarRepo`, `AuthRepo`, `ApiCredentialRepo`) are the only psycopg owners. That part of the layering holds.

### How a strategy is modelled

A fitted strategy is a frozen dataclass, which is the right kind of object, addressed by strings. `SubStrategy` (`quant/strategy/signals.py:27–35`) stores `indicator_name` (a `TechnicalAnalysis` method, such as `get_bollinger_band`), `signal_func_name` (a `SignalDirection` method), `window`, `signal`, and `data_column`.

`StrategyConfig` (`quant/strategy/signals.py:42`) stores both the callable and the name. Conjunction is the string `"AND"`, `"OR"`, or `"FILTER"`, dispatched inside `combine_positions` (line 185). There is no sub-strategy object with its own `on_bar`. "Multi-strategy" means several of these pairs combined into one position series.

Positions are the floats −1, 0, and +1. `TradeAdapter.intended_side` (`quant/trade/adapters/base.py:117`) maps that float and the current quantity onto buy, sell, or flat. `apply_signal` (line 104) takes a `qty` the deployment already stored. Nothing in `quant/strategy` computes a size. A volatility target or a fixed fraction has nowhere to live except inside `Performance._compute_pnl_columns` and, separately, inside the deployment's quantity field. Those two will not stay equal.

**Donchian, as the code is today.** A Donchian breakout is "long when close is above the prior N-bar high", not "threshold a z-score". Files that change:

| Change | File |
|---|---|
| New method on the one indicator class | `quant/strategy/indicators.py` |
| New static method, if the output is not a series the existing four signals can threshold | `quant/strategy/signals.py` (`SignalDirection`) |
| REFDATA row so the UI can name it | a Liquibase changeset for `REFDATA.INDICATOR`, and for `REFDATA.SIGNAL_TYPE` if the signal is new |
| The multi-factor frame, if the method needs High and Low | `quant/strategy/performance.py:183` builds `DataFrame({"factor": factor_vals})` and drops every other column. `quant/strategy/objective.py:31` computes on whatever frame the caller passed, and the single-factor path keeps the original frame (`objective.py:128–132`, `performance.py:198`) while the extra-factor path does not |
| Tests | `tests/unit/` around indicators, signals, and a numeric equality with `Performance` |
| The CLI's private copy of the catalog | `quant/cli.py:66–76`. `INDICATORS` lists bollinger, sma, ema, rsi. Stochastic is already missing. Donchian will be missing too unless this dict is edited. The API does not use it. REFDATA does. |

The single-factor path happens to work for stochastic because `TechnicalAnalysis` is built on the full price frame. The second factor does not. A Donchian on ETH used as a filter for BTC goes through `_indicator_and_position` and never sees ETH's high and low.

**A stateful signal, as the code is today.** Every call site passes `(indicator, threshold)`:

- `quant/strategy/performance.py:187` and `:203`
- `quant/strategy/objective.py:138`
- `SubStrategy.resolve_signal_func` (`quant/strategy/signals.py:37`)

There is no state object and no previous position. Hysteresis (enter at 2, exit at 0) and a trailing stop both need the path. Adding either means a new signature, then an edit at each of those call sites, in both engines, plus a REFDATA function name that `getattr` can find. `compute_latest_position` (`performance.py:156`) is what live uses (`live_service.py:211`), so a signal that is only implemented in the backtest loop will not be the signal that gets traded.

**Position sizing, as the code is today.** The backtest multiplies the −1/0/+1 series by the next return. Live trading sends the deployment quantity when the signal is non-zero (`quant/trade/order_policy.py:139–153` calls `intended_side` and `apply_signal`). A sizer has to sit in both places or the backtest and the order disagree. No interface exists between them.

Target sketch, small enough to land without the `on_bar` engine:

- `Indicator` with `compute(frame, window) -> Series`. The five current formulas become five classes, registered by the REFDATA `method_name` they already have. `TechnicalAnalysis` stays as a facade that looks up the registry, so `getattr(ta, name)` keeps working until the call sites move.
- `Signal` with `positions(frame, indicator, params) -> ndarray`. Today's threshold functions implement it and ignore the columns they do not use. A trailing stop is another class. It is allowed to read `Close` and its own running stop. `Performance` and `Objective` both call this object. They stop calling `getattr`.
- `Sizer` with `weights(positions, frame) -> ndarray`. The default returns the positions unchanged, so current Sharpes do not move. Live qty stays on the deployment until a sizer is explicitly selected. The backtest and the order then share one function.

`StrategyConfig` keeps the names it already serializes to JSON. The registry resolves them. Stored `CONFIG_JSON` does not change shape in this step.

### Brokers

The live crypto path has a clean interface. `TradeAdapter` (`quant/trade/adapters/base.py:33`) extends `BrokerSession` and is what `LiveApplyOrchestrator` and `OrderRetryPolicy` talk to: `place_order`, `get_position_qty`, `apply_signal`, `get_balances`. `CcxtTradeAdapter` implements it (`quant/trade/brokers/ccxt/adapter.py:60`) and delegates HTTP to `CcxtTradeGateway`. `AdapterRegistry.create` (`quant/trade/registry.py:32`) returns the `TradeAdapter` type. Tests of the orchestrator can pass a fake adapter. They do not have to.

The gateway is not substitutable without a patch. It imports ccxt and builds the exchange inside the class (`quant/trade/brokers/ccxt/gateway.py`). `tests/unit/test_bybit_adapter.py` patches `quant.trade.brokers.ccxt.gateway.ccxt` (15 patches in that file). A constructor argument for the exchange class would remove that.

`FutuTrader` (`quant/trade/futu_trader.py:37`) does not implement `TradeAdapter`. It has its own `OrderResult` (line 30) and its own `apply_signal` (line 231, complexity 13). The registry does not construct it. It is a second broker stack, and the design page for it is still a design. Leaving it unwired is fine. Making it the pattern for the next venue would throw away `CcxtVenue`.

Interface segregation on `TradeAdapter` is mild. `get_balances` and `get_open_positions` have concrete defaults so a broker without the endpoint returns nothing (`quant/trade/adapters/base.py:69–78`). The abstract surface is the order loop. That is the right width for one adapter. It is the wrong width for an indicator.

### Domain model, mutability, globals

Dataclasses and Pydantic are used where a boundary crosses a process: `OptimizeRequest` and the other API bodies in `quant/schemas/`, `OrderRequest` / `OrderResult`, `SubStrategy`, `StrategyConfig`. Inside the engine the currency is a `dict[str, DataFrame]` (`backtest_service._build_data_dict`) and a mutated frame. `Performance.__init__` copies the traded frame and then writes `factor1`, `indicator1`, `position1`, and `FinalPosition` onto `self.data`. Two `Performance` instances must not share that frame. They each copy. The risk is not a global DataFrame. The risk is that the result of a calculation is a column name agreed by convention.

Module-level state that is real:

- `quant/shared/db.py:36–37`, `_LOCK` and `_pools`. One connection pool per process per conninfo. Documented, and the right place for it.
- `quant/api/main.py:21`, `DB_CONNINFO = load_config()` at import. Importing the app loads `.env` and configures logging. Tests patch `open_pool` rather than constructing the app with a conninfo.
- `quant/cli.py:66–80`, `INDICATORS`, `STRATEGIES`, and `ASSET_TRADING_PERIODS`. A second catalog beside REFDATA. The API path does not read it. The CLI does. This is the hardcoded list the REFDATA rule exists to prevent, surviving in the entry point.

Inheritance is used where a hook varies (`CcxtVenue`, `SearchStrategy`, `Objective`, `DbGateway` repos) and is not used as a dumping ground. `WorkerRepo` and `WorkerLoopRepo` subclass `BtQueueRepo` to add a call. That is thin, and it is fine. The misuse is the opposite: composition that should exist (`Indicator`, `Signal`, `Sizer`) was never introduced, so the variation is a string.

### Injection and tests

`TradeService`, `LiveApplyOrchestrator`, `ScheduleTickRunner`, `PriceBarService`, and `WorkerLoop` take their repos and adapters as constructor arguments. Those are testable without a database, and the tick tests do it.

What is not injected:

- Redis clients are opened inside `RedisRefData`, `RedisKeyProfiles`, and `RedisVenueLimits`. Tests patch the module-level `_redis` helper (`tests/unit/test_venue_limits.py`).
- `CcxtTradeGateway` builds ccxt itself, as above.
- `run_optimize` takes caches as arguments, which is good, and then constructs `ParametersOptimization` and `Performance` internally. The API tests patch `fetch_df`, `ParametersOptimization`, and `Performance` on `quant.strategy.backtest_service` (`tests/unit/test_api.py`). The walk-forward tests patch `_build_data_dict`, `build_config`, and `_build_wf_response` the same way (`tests/unit/test_walk_forward.py`).

Across `tests/unit` and the synthetic pipeline file there are **187** `patch(` uses. The piles are `tests/unit/test_data.py` (45), `tests/unit/test_live_apply.py` (22), and `tests/unit/test_bybit_adapter.py` (15). Patching is the seam. A registry of indicators would be a smaller one: a test registers a fake indicator by name instead of patching `TechnicalAnalysis`.

### Frontend, briefly

The SPA is function components, MUI, and TanStack Query. Server state stays in the query cache. The one React context is the trade session (`frontend/src/trade/TradeSessionContext.tsx`): broker filter, account filter, and live versus paper. That is a reasonable scope.

The pages that got too big are the ones already named, and they are the UI version of the same problem. `PromotionTab` (775 lines) owns the list, the metric comparison, buy-and-hold, logical delete, and the deployment dialog, and it reimplements ranking. `ConfigDrawer` (581 lines) owns the form, the captured-range snapping, and validation. `BacktestPage` (about 480 lines) is a container: it enqueues, switches tabs, and refetches performance. It does not compute a signal. No frontend class hierarchy needs a redesign. Splitting those two components is the whole UI change, and it is independent of the Python protocol work.

### Refactor roadmap

Each step ships on its own and leaves live trading on the current `Performance.compute_latest_position` path. Do not start by implementing the `Strategy.on_bar` diagram. That would be a second engine beside the twin that already exists.

1. **Indicator registry, no behavior change.** Add `Indicator` and register the five current formulas under their existing `method_name`s. `TechnicalAnalysis` delegates to the registry. Pass the full frame, not a one-column `factor` frame, through `_indicator_and_position`. Pin current SMA, RSI, Bollinger, and stochastic numbers in tests before and after. Then Donchian is a new class, a REFDATA row, and a test. Delete the CLI `INDICATORS` dict in the same change, or make the CLI read the registry, so it cannot drift again. Effort: medium. The Donchian class itself is small once this exists.
2. **Signal registry with today's signature.** Register the eight `SignalDirection` methods under their existing function names. `Performance` and `Objective` call the registry once. Stored JSON and REFDATA do not change. Effort: small, and it is the seam step 3 needs.
3. **Let a signal see the frame.** Widen `positions` to accept the price frame and a params object. Threshold signals ignore both. A hysteresis band and a trailing stop are new classes plus REFDATA rows. Live picks them up because it calls `compute_latest_position`. Ship one stateful signal with a hand-computed series before inviting a catalog of them. Effort: medium.
4. **Identity sizer.** `weights` returns the position series unchanged. `Performance` multiplies by those weights. Live keeps using the deployment quantity until a deployment explicitly names a sizer. Sharpes on existing results must match. A fixed-fraction or volatility sizer is then a class, not an edit to the PnL loop. Effort: medium, and it must not be combined with step 3 in one release.
5. **Move credentials out of `quant.api`.** Put `ApiCredentialRepo` and `CredentialService` in a package `trade` already may import. Update the four importers and the router. Behavior unchanged. This removes the `trade` → `api` edge. Effort: small.
6. **Inject the ccxt exchange class into `CcxtTradeGateway`.** Adapter tests pass a fake. Stop patching `gateway.ccxt`. Do not fold `FutuTrader` into `TradeAdapter` in this step. Effort: small.
7. **Only then consider `on_bar`.** If a strategy still cannot be expressed as indicator, signal, and sizer, that is the evidence for the engine in the target doc. Until then the procedural path stays the one production runs.

Steps 1 through 4 are what the research team needs, in that order. Steps 5 and 6 are the boundary cleanup. The live-trading bugs in findings 1 and 2 are still fixes, not refactors, and they do not wait on this list.

## Top 5 to do first

1. **Stop a filled order from being sent again** when the schedule advance fails (`quant/trade/scheduler/tick.py` lines 297–300). This is the live-trading bug, and it is not solved by a new class diagram.
2. **Put indicators behind one registry and pass the full price frame through**, so a Donchian channel is a new class plus a REFDATA row. Today it is a new method on `TechnicalAnalysis`, a second edit in `Objective`, and a multi-factor path that drops High and Low (`quant/strategy/performance.py:183`).
3. **Reap a non-zero worker exit into `FAILED`** while the row is still `RUNNING` (`quant/queue/worker_loop.py` lines 192–199), and test exit code 1. Small, and independent of the registry work.
4. **Widen the signal call so a stateful rule can see the price path**, after the registry in step 2 exists. A trailing stop or hysteresis cannot be a `SignalDirection` static method of `(indicator, threshold)`.
5. **Add an identity sizer in front of PnL and keep live quantity on the deployment** until a sizer is explicitly chosen. Sizing has no object today. It would otherwise be edited into `Performance` and into `intended_side` separately.
