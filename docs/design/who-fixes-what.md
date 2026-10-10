# Who fixes what

**Updated:** 10 Oct 2026, HKT. Bot Coordinator keeps this page current.

## How to tell them apart

Alfred owns a change that can change application logic, the database, infrastructure, or a product decision that is still open, and he merges those pull requests.

Bots own a verified bug that is a small fix, plus docs, research notes, and an offline harness that does not change live behaviour.

A bot may merge its own pull request only when every changed file is on `.github/workflows/deploy.yml` `paths-ignore` (`docs/**`, root `*.md`, `tests/**`, `scripts/**`, `.github/skills/**`, `.github/instructions/**`, `.cursor/**`) or is `mkdocs.yml`. A test-only pull request still goes to Alfred.

A pull request stays a draft until review has passed, CI is green, and nothing is waiting on a decision.

Code rules for every code change: the fix lives in the owning class, no shims or fallbacks, no hard-coded business values, and tests that fail on `main`.

## Alfred

In this order.

### 1. Pull request 86, spend the search budget on distinct parameter cells

Still a draft. Check Bugs has not passed it. `CONFIG.BACKTEST_SEARCH` uses Liquibase context `config,prod-deploy`, so a merge queues the production migrate, and there is no code fallback if the row is missing. Do not add the cache-page split into #86.

### 2. After 86 merges

Split [`docs/architecture/refdata-cache.md`](../architecture/refdata-cache.md) so the config cache is its own page. Docs only. The two caches are already separate in code.

### 3. Later, not a bot fix

One golden result per strategy (the comparison screen), fractional position sizing, stateful exits, flagging old stored AND results (and FILTER results with 3+ factors) whose numbers changed when #76 merged, the later design for at most two filter factors for daily use (not hard-coded; more can be turned on later), and the later Glassnode narrower metric store (keeps history; purge of closed copies; no live fetch in a harness-only change). #98 (compare two jobs dialog) merged on 8 Oct 2026, so the two-job compare that [`docs/design/2026-09-29-queue-frontend-aids.md`](2026-09-29-queue-frontend-aids.md) listed next is now in the Queue tab. It overlaps the still-open comparison screen (one golden result per strategy). Whether #98 is the first step toward that screen, and any further work on it, is Alfred's decision and not bot work.

Draft pull request 89 (record the risk rule a backtest run reads) touches application code. Alfred merges it. Bots do not own it. Draft pull request 91 (stage strategy-bar PnL reconcile and the fee coin) changes application code, the trade database, and the frontend. The code is `quant/trade/pnl_reconcile.py`, `quant/trade/db_repo.py`, `quant/trade/brokers/ccxt/confirm.py`, `quant/trade/live_apply.py`, and schemas. The database change is Liquibase trade release 1.11.0. It adds a `TRADE.DEPLOYMENT_PERFORMANCE` table and `SP_INS` and `SP_GET` procedures. It adds `FEE_CCY_CD` on `TRADE.TRANSACTION` and changes the `SP_INS_TRANSACTION` signature. Alfred merges it. Bots do not own it. Pull request 90 merged on 10 Oct 2026. The docs now point at rules the application owns, not risk numbers. Pull request 103 (frontend CompareJobsDialog fix: drawdown colouring, window/signal ranges, date keys) merged on 10 Oct 2026. Alfred merged it. Bots do not own it. None of #89, #91, and #103 is on the ordered list above.

## Bots, now

- **Quick Fix Bot.** Only a bug Check Bugs has verified, about 20 lines of real code, with tests. Alfred merges it. Do not edit #86 while that draft is the chosen fix.
- **Check Bugs.** Pass or fail #86.
- **Glassnode.** The offline harness and the sleeve note stay honest. Do not report a Sharpe. Do not build the metric table or a live fetch — that is Alfred's later store. Payload partitions drop on the bound via `BT.SP_DETACH_API_REQUEST_PAYLOAD` (decision 96). Only point-in-time BTC exchange netflow covers 2021 to mid-2024. SOPR and MVRV z-score point-in-time start 27 Jun 2025. BNB is not on the netflow metric. The BNB stand-in, exchange net position change, has a point-in-time twin that starts 23 Jun 2025 and does not cover 2021 to 2024.
- **Research, not code.** The first child is point-in-time BTC exchange netflow as factor one and BTC Bollinger 60/2.25 as factor two. The gate indicator is an SMA with window 1; the signal threshold sits strictly between 0 and 1 (do not pick a number inside the range in docs). Nothing is scored until that series is a real column the engine reads.
