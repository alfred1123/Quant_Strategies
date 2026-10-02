# Who fixes what

**Updated:** 3 Oct 2026, HKT. Bot Coordinator keeps this page current.

## How to tell them apart

Alfred owns a change that can change application logic, the database, infrastructure, or a product decision that is still open, and he merges those pull requests.

Bots own a verified bug that is a small fix, plus docs, research notes, and an offline harness that does not change live behaviour.

A bot may merge its own pull request only when every changed file is on `.github/workflows/deploy.yml` `paths-ignore` (`docs/**`, root `*.md`, `tests/**`, `scripts/**`, `.github/skills/**`, `.github/instructions/**`, `.cursor/**`) or is `mkdocs.yml`. A test-only pull request still goes to Alfred.

A pull request stays a draft until review has passed, CI is green, and nothing is waiting on a decision.

Code rules for every code change: the fix lives in the owning class, no shims or fallbacks, no hard-coded business values, and tests that fail on `main`.

## Alfred

In this order.

### 1. Pull request 86, spend the search budget on distinct parameter cells

Still a draft. Check Bugs has not passed it. `CONFIG.BACKTEST_SEARCH` uses Liquibase context `config,prod-deploy`, so a merge queues the production migrate, and there is no code fallback if the row is missing. Do not add the cache-page split into this pull request.

### 2. Pull request 87, narrower Glassnode store

A draft on purpose. He still decides whether a stored point keeps only the latest value, or also the previous value once a real revision shows up. No revision has been observed. The narrower metric table is the recommendation and is not built. Do not purge `API_REQUEST`. Do not turn the offline harness into a live fetch in this pull request.

### 3. After 86 merges

Split [`docs/architecture/refdata-cache.md`](../architecture/refdata-cache.md) so the config cache is its own page. Docs only. The two caches are already separate in code.

### 4. Later, not a bot fix

One golden result per strategy (the comparison screen), fractional position sizing, stateful exits, flagging old stored AND results (and FILTER results with 3+ factors) whose numbers changed when #76 merged, and the later design for at most two filter factors for daily use (not hard-coded; more can be turned on later).

## Bots, now

- **Quick Fix Bot.** Only a bug Check Bugs has verified, about 20 lines of real code, with tests. Alfred merges it. Do not edit 86 or 87 while those drafts are the chosen fix.
- **Check Bugs.** Pass or fail 86. 87 stays a draft until Alfred picks the revision rule.
- **Glassnode.** The offline harness and the sleeve note stay honest. Do not report a Sharpe. Do not build the metric table until the revision rule is chosen. Only point-in-time BTC exchange netflow covers 2021 to mid-2024. SOPR and MVRV z-score point-in-time start 27 Jun 2025. BNB is not on the netflow metric. The BNB stand-in, exchange net position change, has a point-in-time twin that starts 23 Jun 2025 and does not cover 2021 to 2024.
- **Research, not code.** The first child is point-in-time BTC exchange netflow as factor one and BTC Bollinger 60/2.25 as factor two. The gate is any non-zero day. Nothing is scored until that series is a real column the engine reads.
