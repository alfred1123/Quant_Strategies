# Who fixes what

**Updated:** 22 Oct 2026, 11:55 PM HKT. Bot Coordinator keeps this page current.

## How to tell them apart

Alfred owns a change that can change application logic, the database, infrastructure, or a product decision that is still open, and he merges those pull requests.

Bots own a verified bug that is a small fix, plus docs, research notes, and an offline harness that does not change live behaviour.

A bot may merge its own pull request only when every changed file is on `.github/workflows/deploy.yml` `paths-ignore` (`docs/**`, root `*.md`, `tests/**`, `scripts/**`, `.github/skills/**`, `.github/instructions/**`, `.cursor/**`) or is `mkdocs.yml`. A test-only pull request still goes to Alfred.

A pull request stays a draft until review has passed, CI is green, and nothing is waiting on a decision.

Code rules for every code change: the fix lives in the owning class, no shims or fallbacks, no hard-coded business values, tests that fail on `main`, and reuse or extend existing utilities, classes, readers, and fields instead of adding new logic. A review fails a pull request that duplicates an existing object. The reuse rule is [`docs/design/coding-standards.md`](coding-standards.md).

## Alfred

In this order.

### 1. Pull request 86, spend the search budget on distinct parameter cells

Still a draft. Check Bugs has not passed it. `CONFIG.BACKTEST_SEARCH` uses Liquibase context `config,prod-deploy`, so a merge queues the production migrate, and there is no code fallback if the row is missing. Do not add the cache-page split into #86.

### 2. After 86 merges

Split [`docs/architecture/refdata-cache.md`](../architecture/refdata-cache.md) so the config cache is its own page. Docs only. The two caches are already separate in code.

### 3. Later, not a bot fix

One golden result per strategy (the comparison screen), fractional position sizing, stateful exits, flagging old stored AND results (and FILTER results with 3+ factors) whose numbers changed when #76 merged, the later design for at most two filter factors for daily use (not hard-coded; more can be turned on later), and the later Glassnode narrower metric store (keeps history; purge of closed copies; no live fetch in a harness-only change). #98 (compare two jobs dialog) merged on 8 Oct 2026, so the two-job compare that [`docs/design/2026-09-29-queue-frontend-aids.md`](2026-09-29-queue-frontend-aids.md) listed next is now in the Queue tab. It overlaps the still-open comparison screen (one golden result per strategy). Whether #98 is the first step toward that screen, and any further work on it, is Alfred's decision and not bot work.

### Open drafts awaiting Alfred

These drafts are not on the ordered list above. #86 stays item 1.

Draft pull request 89 (record the risk rule a backtest run reads) touches application code. Alfred merges it. Bots do not own it.

Draft pull request 91 (stage strategy-bar PnL reconcile and the fee coin) changes application code, the trade database, and the frontend. The code is `quant/trade/pnl_reconcile.py`, `quant/trade/db_repo.py`, `quant/trade/brokers/ccxt/confirm.py`, `quant/trade/live_apply.py`, and schemas. The database change is Liquibase trade release 1.11.0. It adds a `TRADE.DEPLOYMENT_PERFORMANCE` table and `SP_INS` and `SP_GET` procedures. It adds `FEE_CCY_CD` on `TRADE.TRANSACTION` and changes the `SP_INS_TRANSACTION` signature. Alfred merges it. Bots do not own it.

Draft pull request 125 (Keep the typed reject reason when a fill poll fails) changes `quant/trade/brokers/ccxt/confirm.py` and tests. It was ready for review and is a draft again as of 22 Oct 2026, about 11:32 PM HKT. Application code. Alfred merges it. Bots do not own it.

Draft pull request 127 (Stop order retries when a cancel returns failure) changes `quant/trade/order_policy.py`, `quant/trade/models/order.py`, docs, and tests. It was ready for review and is a draft again as of 22 Oct 2026, about 11:33 PM HKT. Application code. Alfred merges it. Bots do not own it.

Draft pull request 128 (Report a typed reason when a cancel is refused) stacks on #127. Review and merge #127 first. The diff against `main` includes both. It touches the `quant/trade` adapter, live apply, the scheduler tick, schemas, docs, and tests. Application code. Alfred merges it. Bots do not own it.

### Closed and merged

Pull request 90 merged on 10 Oct 2026. The docs now point at rules the application owns, not risk numbers.

Pull request 103 (frontend CompareJobsDialog fix: drawdown colouring, window/signal ranges, date keys) merged on 10 Oct 2026. Alfred merged it. Bots do not own it.

Pull request 110 (Write a missing provider xref from the exchange base) merged on 18 Oct 2026. Alfred merged it. Bots do not own it.

Pull request 109 (Keep Glassnode xref I/O off the instrument-create path) closed on 18 Oct 2026 without merge. It had been ready for review and was dirty against main after #110. Alfred owned it while it was open. Bots do not own a revive or a retarget unless Alfred asks. The provider series after #110, the deploy, and the next 06:15 UTC fill is not waiting on #109.

Pull request 115 (List a provider series from its subscription id) closed on 18 Oct 2026 without merge. Alfred owned it while it was open. Bots do not own a revive or a retarget unless Alfred asks.

Pull request 118 (List a provider series from a subscription) merged on 19 Oct 2026. `MARKET_DATA.PROVIDER_SUBSCR` is the Data tab list. The stored window is `MARKET_DATA.API_REQUEST`, joined on `PROVIDER_SUBSCR_ID`. The window tables move to `MARKET_DATA`. Decision #100. The change is Liquibase, `quant/`, and the frontend. Alfred merged it. Bots do not own it.

Pull request 121 (Store every source of a product on SERIES_SUBSCR, keyed by its id) merged on 20 Oct 2026. The change is Liquibase market_data 1.7.0, `quant/`, and the frontend Data tab. Venue bars and provider series share `MARKET_DATA.SERIES_SUBSCR`. Alfred merged it. Bots do not own it.

Pull request 126 (Refresh the frontend lockfile past the follow-redirects and vite advisories) merged on 22 Oct 2026, about 10:23 PM HKT. It changed only `frontend/package-lock.json`. That file is a dependency file, so the change is application code. Alfred merged it. Bots do not own it.

Pull request 129 (Read scalar knobs from CONFIG.SETTING, and the two label catalogs from REFDATA) merged on 22 Oct 2026, about 11:30 PM HKT. It changed Liquibase config 1.4.0 (`CONFIG.SETTING`) and refdata 1.31.0 (`QUEUE_PRIORITY`, `SCHEDULE_STATUS`), many `quant/` modules, and docs. Those changesets use context `config,prod-deploy` and `refdata,prod-deploy`, so the merge queues the production migrate. Application code and database. Alfred merged it. Bots do not own it.

Pull request 132 (Docs: reuse existing utilities before adding new logic) merged on 22 Oct 2026, about 11:54 PM HKT. It changed `.github/pull_request_template.md` and `docs/design/coding-standards.md`. Docs. Alfred merged it.

Pull request 124 (Fix the Bybit harness DB-key path for the M9 credential API) merged on 22 Oct 2026, about 11:54 PM HKT. It changed only `scripts/bybit_local_testnet.py` and `tests/unit/test_bybit_local_testnet.py`. It is an offline harness that does not change live behaviour. Every file is on `deploy.yml` `paths-ignore`. Alfred merged it.

None of the open drafts #89, #91, #125, #127, and #128, and none of the closed or merged pull requests #90, #103, #109, #110, #115, #118, #121, #124, #126, #129, and #132, is on the ordered list above.

## Bots, now

- **Quick Fix Bot.** Only a bug Check Bugs has verified, about 20 lines of real code, with tests. Alfred merges it. Do not edit #86 while that draft is the chosen fix.
- **Check Bugs.** Pass or fail #86.
- **Glassnode.** The offline harness and the sleeve note stay honest. Do not report a Sharpe. Do not build the narrower metric table — that is Alfred's later store. Do not self-merge an application-code pull request; Alfred reviews those. The scheduled fill is `fill_scheduled_providers` (decision 97). Payload partitions drop on the bound via `MARKET_DATA.SP_DETACH_API_REQUEST_PAYLOAD` (decision 96, moved in #100). Only point-in-time BTC exchange netflow covers 2021 to mid-2024. SOPR and MVRV z-score point-in-time start 27 Jun 2025. BNB is not on the netflow metric. The BNB stand-in, exchange net position change, has a point-in-time twin that starts 23 Jun 2025 and does not cover 2021 to 2024.
- **Research, not code.** The first child is point-in-time BTC exchange netflow as factor one and BTC Bollinger 60/2.25 as factor two. The gate indicator is an SMA with window 1; the signal threshold sits strictly between 0 and 1 (do not pick a number inside the range in docs). Nothing is scored until that series is a real column the engine reads.
