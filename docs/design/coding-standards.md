# Coding standards

**Doc type:** living standard
**Status:** active. Every pull request that changes app code is reviewed against this page.
**Written against:** `main` at `2d53b6f` (2026-09-29).

This page is the standard for code in this repository: the Python engine and API in `quant/`, the stored procedures in `db/liquidbase/`, and the React app in `frontend/`. It collects rules that already live in `AGENTS.md`, `.cursor/rules/`, and `.github/instructions/`, and adds the hard requirements that decide whether a pull request is merged.

The pull request template (`.github/pull_request_template.md`) walks through the same list. Fill it in; do not delete sections.

## Hard requirements

These five rules are not negotiable. A pull request that breaks one of them is not merged, however small or urgent it is. If a rule seems to block a change you need, raise it with Alfred before you write the code, not in review.

### 1. OOP ownership

A change goes in the class or module that owns the behaviour.

- Find the owner before you write code. The architecture pages and the design doc for the area usually name it. Prefer the existing owner over a new class.
- Do not patch callers to work around a bug in the callee. Fix the callee.
- Do not add cross-module coupling or import cycles. The import graph had zero module cycles in the [code quality review](2026-09-26-code-quality-review.md); keep it at zero.
- Do not duplicate logic. One fact has one owner: the stored-procedure wrapper, the REFDATA parser (`RedisRefData`), the frame builder. Call it; do not reimplement it beside it. If two repos need the same procedure, the wrapper lives on one repo and the other takes it by injection (for example, `bt.sp_get_strategy` lives only on `BtQueueRepo`).
- Respect the layers. From top to bottom: API routes (`quant/api/`), then services, then repos (`DbGateway` subclasses calling stored procedures), then brokers and adapters (`quant/trade/brokers/`, `quant/trade/adapters/`). A lower layer never imports an upper one. A route does not call a repo directly when a service owns that flow.
- Do not add a layer just to cut lines. A helper is justified only when it removes a real second copy or makes the policy readable.

### 2. No backward compatibility

When an interface changes, replace it and update every caller in the same pull request.

- No shims, aliases, re-export wrappers, deprecated parameters, fallback code paths, or "legacy" branches.
- After a rename, search the whole tree (Python, SQL, frontend, scripts, docs) for the old name and run the full suite. A stale name in a dispatch map is a latent bug.
- Remove dead imports and dependencies that the change leaves behind.

### 3. No hard-coded values

The default home for a value is the database. Values live in reference or config tables created by Liquibase, are published to Redis by `RefDataPublisher`, and are read through `RedisRefData` (`get()` for `REFDATA`, `get_config()` for `CONFIG`).

- Status ids, type ids, and names come from `REFDATA` tables, never literals. The pattern to copy is `RedisRefData.resolve_queue_status_id(name)`, which looks the id up in `REFDATA.QUEUE_STATUS` and raises if the row is missing.
- Business values are never magic numbers or strings in code. That covers limits, fees, thresholds, trial counts, result sizes, currencies, and anything a user or Alfred might want to tune.
- UI dropdowns, grid defaults, and promotion rules already come from `REFDATA` and `CONFIG` (see the table in `AGENTS.md` and [REFDATA Cache](../architecture/refdata-cache.md)). New ones follow the same path.
- Environment variables or config files are acceptable only where the design suits them: deployment settings (URLs, `APP_ENV`, `DB_TARGET`), secrets, and process tuning (pool sizes such as `DB_POOL_MAX`, worker concurrency such as `MAX_CONCURRENT_WORKERS`). Document each new variable in [Environment Variables](../env-vars.md).
- If you are unsure which home a value needs, choose the table and say so in the pull request.

**Known debt.** The values below exist on `main` today and are to be migrated. They are listed so nobody copies them. They are not allowed patterns, and a pull request that touches this code should move the value it touches rather than add another beside it.

| Where | Value | Why it is debt |
|---|---|---|
| `quant/strategy/optimizer.py` | `OPTUNA_MAX_TRIALS = 10_000`, `OPTUNA_SEED = 42` | Search budget and seed are research settings, fixed in code. |
| `quant/strategy/optimizer.py`, `_build_result` | `sorted_df.head(10)` (the `top10` result size) | Result size is a literal, and the field name `top10` bakes it into the API schema. |
| `quant/trade/live_apply.py` | `_FALLBACK_SETTLEMENT_CCY = "USDT"` | A live-trading currency guessed in code when `INST.PRODUCT.CCY` is empty. Also a fallback path, which rule 2 forbids. |
| `quant/queue/worker_loop.py`, `WorkerLoop` | `DEFAULT_JOB_TIMEOUT_S = 6000`, `BLPOP_TIMEOUT_S = 30`, `DRAIN_TIMEOUT_S = 30`, `CANCEL_GRACE_S = 10`, `WAKE_SOCKET_MARGIN_S = 5` | The job timeout is a business limit with an env override defaulting to a code constant. The other timings are process tuning with no config at all. |

Other module constants of the same shape should be classified the same way when their module is next changed, for example `DEFAULT_RETRY_BACKOFF_S` in `quant/trade/scheduler/tick.py` and `DEFAULT_SETTLE_S`, which is defined twice (`quant/market_data/warm.py` and `quant/trade/scheduler/sweep.py`).

### 4. Thorough testing

Every fix or feature pull request carries all of the following, with evidence in the description.

- **(a) A test that fails on `main` and passes with the change.** Run it against `main` first and quote the failure (the assertion or traceback) in the pull request description. A test that was never seen failing proves nothing.
- **(b) Edge-case tests.** Cover empty and `None` inputs, boundaries (zero, one, the limit, one past it), and paths that interact or race (two workers, a retry after a partial write, a cancel during a run).
- **(c) The full suite and CI green, plus ruff and mypy.** Run `python -m pytest tests/ -v` locally and quote the summary line. CI (`.github/workflows/tests.yml`) runs pytest on `tests/unit/` and `tests/integration/test_backtest_pipeline.py`, an offline Liquibase validation, and the frontend lint, build, audit, and tests. **CI does not run ruff or mypy**, and the repo has no config for either, so run them yourself: `python -m ruff check quant tests scripts` and `python -m mypy quant --ignore-missing-imports`. Neither is clean on `main` today (see the [code quality review](2026-09-26-code-quality-review.md#3-python-ci-does-not-type-check-or-lint-and-both-fail)). The rule is that your change adds no new findings: quote the counts before and after, or the output for the files you touched.
- **(d) Backtest comparison.** Anything that can change backtest results (indicators, signals, performance metrics, the optimizer, data loading, bar alignment, fees) needs a before-and-after comparison on a real backtest: the same instrument, interval, date range, and parameters on `main` and on the branch, with the key metrics side by side and an explanation of every difference.

### 5. Long-term fixes over quick fixes

The platform is meant to last. A fix that works today and breaks in a month is not a fix. When the harder change is the better one long term, choose it.

- **Triage.** A bug is a quick fix only if a small change fixes the root cause, in the class that owns the behaviour. If the only small change treats a symptom, or lives in a caller, it is not a quick fix. It becomes a design item under `docs/design/` that describes the long-term fix, and Alfred picks the approach.
- **The 20-line limit decides who takes a bug, never how small the fix should be.** A bug that fits in about 20 lines at the root cause can go to Quick Fix Bot. A bug that does not becomes a design item. Never shrink a fix to fit the limit.
- **How did this happen?** Every bug write-up and every fix pull request traces the cause to the point where the wrong behaviour starts, not where it shows up. The description has a "How did this happen? (root cause)" section for that trace. A fix that removes or hides bad output (dropping duplicate rows after the fact, filtering bad values, or catching and ignoring an error) must explain why that output cannot be stopped at its source. If it cannot, the bug becomes a design item under `docs/design/`, not a quick fix. Repeated top-10 rows in the optimizer are the example: they come from the TPE sampler re-proposing already-tested parameter cells, so the fix belongs in the search, not in de-duplicating `_build_result`'s output.
- **Long-term check.** Every pull request description has a "Long-term check" section. It says whether the change fixes the root cause or a symptom, and what would break it within a month. Walk through at least these: a new strategy type, a new coin, hourly bars, a database schema change, and a new broker.

## Professional standards

These are the working standards for every change. Reviewers flag departures from them. Unlike the hard requirements, a reviewer and Alfred can agree an exception, but the pull request must say why.

### Types and names

- Put type hints on every function and method signature, including the return type. Use `X | None`, not a bare default of `None` with no type.
- Name things by what they do or mean in the domain, not by a category label. `_check_hard` says nothing; a name that says "must pass" does.
- Keep functions and classes small and single-purpose. As a review trigger, not a hard limit, a reviewer asks about any class over about 300 lines or function over about 50. The fix is usually to separate policy from mechanics, not to add a wrapper.

### Errors

- No bare `except:` and no silent swallowing (`except Exception: pass`). Catch the narrowest exception you can handle, and let the rest propagate.
- The "best-effort, never fails the cycle" pattern is allowed only where the docstring says so and explains why, as in `LiveApplyOrchestrator._audit_attempts` and `_write_transaction` in `quant/trade/live_apply.py`. Such a handler must log with `logger.exception(...)` so the traceback is kept.
- Raise with a message that names the missing thing, for example `RuntimeError(f"REFDATA.QUEUE_STATUS missing NAME={name!r}")`.

### Logging

- Every module declares `logger = logging.getLogger(__name__)` at the top and logs through it.
- Logging is configured once, by `setup_logging()` in `quant/shared/logging.py`, called only from entry points. Library code never calls `setup_logging()` or `logging.basicConfig()`.
- Do not use `print()` for status output. The one deliberate exception is the backtest worker's newline-delimited JSON event stream on stdout (`BacktestWorker._emit`), which is a protocol, not logging.
- Use lazy formatting (`logger.info("x=%s", x)`), not f-strings, in log calls.

### Database access

- All database access goes through a repo class that subclasses `DbGateway` (`quant/shared/db.py`) and calls stored procedures with `_call_get`, `_call_get_one`, or `_call_write`.
- No raw `SELECT`, `INSERT`, `UPDATE`, or `DELETE` in application code. As `quant/queue/repo.py` puts it: "no direct `SELECT` in application code". The only exception is `information_schema` catalog queries. Liquibase seed changesets may insert directly.
- If the procedure you need does not exist, write it first, with its own changeset (see [Database](../architecture/database.md) and [Database Connections](db-connections.md)). Editing a procedure body does nothing on its own; it needs a new changeset, and a schema-only context unless Alfred has approved `prod-deploy`.

### Secrets

- No secrets in code, tests, fixtures, logs, or pull request text. Keys live in `.env` (gitignored) locally and in SSM in production.
- Process entry points call `load_config()` once. That loads SSM (`USE_SSM=1`) or `.env` into the environment. Library code, including data-source classes, reads `os.environ` and does not call `load_dotenv()`.
- Do not log credentials or encrypted keys. `DbGateway` already redacts Fernet tokens in procedure logs; do not add a log line that bypasses it.

### Docstrings

- Public classes and public methods have docstrings.
- A docstring explains why the code is shaped the way it is: the contract, the invariant, the trap it avoids. It does not restate what the next line does.

### Tests

- Unit tests live in `tests/unit/test_<module>.py`, one file per source module, so the test for a module is easy to find. Integration tests that need Postgres or run the full pipeline live in `tests/integration/`. Live-provider tests live in `tests/e2e/` and are excluded by default (`-m 'not e2e'` in `pyproject.toml`).
- Reuse the fixtures in `tests/conftest.py` before adding new ones.
- Prefer fakes over `MagicMock` where the behaviour matters. `StubRefData` in `tests/conftest.py` and `FakeRefData` / `FakeProc` in `tests/unit/test_worker_loop.py` are the models: a real reader over a fixed snapshot tests the shipped parsing, while a `MagicMock` agrees with every call and hides the bug.
- Never call live APIs in unit tests. Mock responses must match the real response shape.
- Name tests `test_<what>_<expected_behaviour>` and use `pytest.approx()` for floats. See [Running Tests](../guides/testing.md).

### Pull requests and commits

- One fix per pull request. Keep diffs small enough to review in one sitting.
- Write commit messages in the imperative mood ("Mark a crashed job FAILED"), and say what changed and why.
- The pull request description covers what changed, why, how it was tested (with the evidence from rule 4), risk and rollback, which hard rules the change could affect, and the long-term check from rule 5. The template has a section for each.
- Update the docs in the same pull request when behaviour changes: the matching page in `docs/`, `README.md` for usage or setup, and `docs/decisions.md` for a decision. Add new pages to `nav:` in `mkdocs.yml` and keep `mkdocs build --strict` at zero warnings.

### Live trading

Anything under `quant/trade/` can place real orders. Take extra care.

- Test the failure paths, not only the happy path: the broker rejects, times out, or partly fills; the position read lags; the database write after a successful order fails.
- Never mutate production to test a change: no orders on live accounts, no writes to production tables, no production deploys from a branch.
- Say in the pull request which live paths the change can reach.

## How reviews use this

- Check Bugs reviews every pull request that changes app code (`quant/`, `db/`, `frontend/src/`) against this page, starting with the five hard requirements.
- A pull request without the testing evidence from rule 4 (the fails-on-`main` test, the full suite result, and the ruff and mypy results) is blocked until the evidence is added.
- Alfred merges every code pull request himself.
