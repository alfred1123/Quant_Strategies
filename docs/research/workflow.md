# Research workflow

How the research bots work together on Alfred's crypto strategies: who does what, how an idea moves from source to finalist, the shared test conventions, and the gates a strategy must pass before it counts as confirmed.

**Flow.** Scout finds and screens an idea offline, then hands a spec to the researcher. The researcher backtests it on AlgoDaemon and reports a verdict. Check Bugs verifies any platform claim or bug against the code. Risk Guardian sets sizing, drawdown limits and monitoring for strategies that survive. Bot Coordinator merges everyone's findings into one ranked list for Alfred. Alfred makes every decision about code changes, money and live trading.

**Standing rules.**
- No code changes to Quant_Strategies or AlgoDaemon without Alfred's approval. Docs PRs, offline research and backtests are fine.
- Nothing is traded, deployed, promoted or bought by a bot.
- Offline numbers and platform numbers are always labelled separately.

## Sourcing and screening (Crypto Strategy Scout)

**Role.** Scout finds strategy ideas in English, Chinese and other-language sources (papers, Patreon, Zhihu, FMZ, Xueqiu, broker notes), screens them offline and writes them up under the Research tab. Scout never trades and never changes app code. Its offline numbers are a screen only. Only the researcher's platform numbers make a finalist.

**Screening steps** (saved as the skill "Vet a trading strategy idea")
1. Check the knowledge file first: sources already covered or blocked, families already tested and their verdicts, and current engine limits.
2. Extract the rules exactly as the source states them. Quote the source's numbers and say whether they are in-sample, out-of-sample or full period. Never fill gaps with guesses.
3. Classify the idea by family (trend, mean reversion, carry, relative value, volatility, flow), estimate its correlation to the current finalists, and check whether the engine can express it. Ideas with low correlation to the BTC-trend sleeves rank higher.
4. Run the offline gate (below). Every figure is labelled "offline approximation, not AlgoDaemon platform results".
5. Decide: reject (and record why), document only (and name the platform feature it needs), or hand off to the researcher.

**Hand-off spec to the researcher**
- Rules in engine terms: indicator, data column (capital-V `Volume`), momentum or reversion, signal sign.
- FILTER for two conditions, never AND (B1). Three or more factors go offline only.
- Parameter ranges with steps and the combination count (under 10,000, B23).
- Which finalist it should beat or diversify, the source link and any out-of-sample evidence.
- The offline gate result: one-day delay, neighbourhood median, correlation to the sleeves.
- Anything the engine can't express, flagged.

**Where things go.** Research pages go in `docs/research/` (linked from `docs/research/README.md` and `mkdocs.yml`) as docs-only PRs that must pass `mkdocs build --strict`. Ideas that need new platform features are written up as proposals. Building them is Alfred's decision.

## Validation gates (all bots)

These come from the [persistence validation study](strategy-persistence-validation.md). A strategy counts as confirmed only when it passes all of them.

1. **Same-close and one-day-delay fills.** The engine fills at the close that produced the signal. A strategy whose Sharpe collapses with a one-day delay is rejected.
2. **Neighbourhood, not the best cell.** Report the median of the ±1-step neighbours. Picking the best cell from a grid does not carry forward (the correlation between train rank and next-test rank is about 0).
3. **Block bootstrap error bars.** Use a stationary block bootstrap with blocks of about 10 days, never iid resampling, which is too narrow when returns cluster. Report the 95% interval for out-of-sample Sharpe.
4. **Probabilistic and Deflated Sharpe.** Report PSR against 0 and against 0.5, and DSR at a conservative trial count (N=1000 unless the effective count is known). Report the minimum track record length.
5. **Walk-forward over a single split.** Prefer an expanding window refit quarterly. A single train/test split mostly reflects where you cut, and a bigger test share alone doesn't fix that.
6. **Regime split.** Report each regime separately (2018-19, the 2020-21 boom, the 2022 bust, 2023 to mid-2024, July 2024 onwards) and the result with 2020-22 removed. Keep 2020-22 in training, but also report it as a stress test. Don't choose parameters on post-2023 data alone.
7. **Overfitting across the family.** PBO/CSCV of about 0.30 or less as a guide. Above that, expect the family-median Sharpe, not the best cell's.
8. **Concentration and benchmark.** Time in market, skew, Sortino, the effect of removing the top 1-3 days, and buy-and-hold over the same windows.

**Live monitoring.** A rolling Sharpe is a dashboard, not a test (a 1-year window has a standard error of about ±0.8-1.0). Alarms (CUSUM, or drawdown past a bootstrap quantile) mean "review and cut size", not "switch off". Blend-level sizing, drawdown limits and the kill switch belong to Risk Guardian.

## Platform backtesting (AlgoDaemon Quant Researcher)

**Conventions**
- One common range for every compared run: 2021-07-01 to 2026-09-25, extended at re-checks. Bybit spot daily bars, BTC/ETH/BNB, 10 bps fees.
- Splits: in-sample (IS) to 2024-06-30, out-of-sample (OOS) from 2024-07-01, late from 2024-11-19.
- Metrics start after the longest indicator warm-up. Deltas are measured against the baseline on the same post-warm-up sample.
- Multi-factor rules use FILTER, never AND. With 3 or more factors, the non-gate factors act as OR (B1), so those are tested offline only.

**Robustness gates (a finalist must pass all)**
1. Neighbourhood median: median Sharpe of the ±1-step neighbours, for IS, OOS and late. The best cell alone never qualifies.
2. Improves both IS and OOS against the current finalist. An OOS-only gain goes on the watch list.
3. 1-bar fill delay (plus intraday delays where relevant). The engine fills at the same close that produced the signal, so a strategy that collapses under a delay is rejected.
4. Concentration: time in market, skew, Sortino, and the effect of removing the top 1–3 days.
5. Family PBO (CSCV) of 0.30 or less at several split counts and both delays, used as a guide (warm-up trimming moves it by about ±0.1).
6. Buy-and-hold benchmark over the same windows.

**Grid and platform limits**
- Grids stay under 10,000 combinations, because larger ones are silently TPE-sampled (B23). Window minimum 1 or more.
- Wide ranges with sensible steps. Sync optimise calls of 150 trials or fewer, one at a time.
- At most 2 queued jobs, since there are 2 workers. Queue only real finalists, and never promote by hand.
- The offline replica is used only after it reproduces the platform exactly.

**What I need in a hand-off**
- Exact rules in engine terms: indicator, data column (capital-V `Volume`), momentum or reversion, signal sign.
- Parameter ranges with steps and the combination count.
- The finalist it should beat or diversify, and the source with any OOS evidence.
- Your offline screen result: delay-1, neighbourhood and correlation to the current sleeves.
- Flag anything the engine can't express.

**Reporting**
- Verdict first (finalist, watch list or rejected).
- Then a table of IS, OOS, late and delayed-OOS Sharpe, neighbourhood medians, max drawdown, time in market, buy-and-hold and the delta against the finalist. Offline and platform numbers are labelled separately.
- Results go to /workspace/algodaemon/roundN/README.md, the group chat and #algo-system. New bugs are appended to BUGS_FOR_PR.md for Check Bugs to verify.
- The method is saved as the skill "Validate a strategy backtest" (validate-a-strategy-backtest).

## Code verification (Check Bugs)

**Role.** Check Bugs checks claims about the platform against the code in `alfred1123/Quant_Strategies`. It doesn't backtest or change app code, and it never trades, deploys or promotes. Only one bot's view of a code change counts, and it's this one.

**Review steps**
1. Take the claim as written, from the researcher's bug list, a room post or `#algo-system`.
2. Find the code path on current `main` and note the SHA. Cite each file, function and line with a short quote.
3. Where possible, reproduce the behaviour on synthetic data with the engine code from that commit. Live `algodaemon.com` and production data are never touched.
4. Mark how each point was checked:
   - **Ran**: reproduced with the engine code.
   - **Read**: the cause is visible in the source.
   - **Raw**: read from the stored job rows the researcher saved.
   - **Offline/Researcher**: the researcher's measurement, not re-run.
5. Give a verdict: confirmed and open, fixed (cite the commit), milder than reported, or not a bug. Then add a fix direction in words, never code.
6. Write it up as a docs-only PR under `docs/design/`, linked from `mkdocs.yml` and `docs/design/README.md`. `mkdocs build --strict` must pass. Check Bugs merges its own docs-only PRs. Anything that touches code waits for Alfred.

**Paths watched (proposed, pending Alfred's OK).** Any PR that changes `quant/` (the engine, optimizer, API and queue), `db/` (procedures and tables) or `frontend/src/` (the config drawer and request builders). Each one is checked against the open bug list, and Check Bugs posts a verdict in the group room: which B-numbers it fixes, and whether it changes numbers that backtests depend on. Bot Coordinator relays that verdict and updates the blockers list.

**Bug log and feedback loop**
- The researcher adds new entries to `BUGS_FOR_PR.md`, and only adds.
- Check Bugs owns the "verified" status column. Nobody else edits it.
- Every verified item gets a stable B-number and a section in a dated `docs/design/` report. So far that's #64 for B1–B21 and #67 for B22–B26 and rounds 3–4.
- When a fix is merged, Check Bugs confirms it on `main` and flips the status to fixed with the commit. It then tells the researcher which tests to re-run and tells Scout if an engine limit that blocked an idea has been lifted.
- Current limits Scout's hand-off specs should respect:
  - SMA/EMA are raw levels (B22).
  - Grids over 10,000 cells are sampled (B23).
  - FILTER with 3+ factors acts like OR (B1).
  - Fills happen on the same close, with no delay option.
  - A factor reads one column (B26).
  - Use capital-V `Volume`, never lowercase.

## Coordination (Bot Coordinator)
- **Priority list.** Each bot keeps its top items in `/workspace/priorities/<bot>.md`. Each item has evidence (ran, read in code, or reported), effort, what it unblocks, and whether it needs Alfred. I merge them into one ranked list for Alfred and flag disagreements and the decisions only he can make.
- **Ranking order.** First, anything touching real money or live trading. Then anything that makes current results untrustworthy. Then what unblocks the most work. Then cost against benefit. Items touching the production database or needing a migration are marked higher risk.
- **Blockers.** I keep `/workspace/priorities/blockers.md`, listing each blocker, who is waiting, what it unblocks and what counts as cleared. When a PR merges I check it against that list and tell the waiting bot what research or backtest it can now run. A docs PR that only describes a fix doesn't clear a code blocker.
- **Ownership.** Scout sources and screens ideas offline. Researcher's platform numbers are the only ones that make a finalist. Researcher adds bugs to `BUGS_FOR_PR.md`, and Check Bugs owns the verified column. I own the ranked list, the blockers file and sequencing PR merges.
- **Rules.** No code changes without Alfred's approval; docs PRs, research and backtests are fine. Nothing is traded, deployed, promoted or bought by a bot.

## Risk control (Risk Guardian)

Risk Guardian owns sleeve sizing and caps, drawdown limits based on bootstrap resampling rather than the single historical path, the blend-level kill switch, and return concentration. It builds on the validation gates above rather than re-running them, and it tests sizing offline until the platform supports fractional positions (PR #63 proposals). Its priorities are in `/workspace/priorities/risk-guardian.md`. This section will be expanded by Risk Guardian.
