# Glassnode market data

**Status:** Draft. The narrower metric store is the option this page argues for. Alfred has rejected latest-only storage. The later store keeps history and purges closed copies. That purge is a later pull request. Release `refdata/1.28.0` seeds the catalog rows. The fetch is unchanged.
**Date:** 2026-10-03
**Scope:** how a Glassnode series should be fetched and stored. Parent: [Alternative data sources](alt-data-sources.md).

Alfred has rejected latest-only storage. The later Glassnode store keeps history. Alfred's archive path is a purge of closed copies, not a delete of the live rows and not a vague archive. That store is a later pull request and is not built here. Keeping that history is not the point-in-time series. Point-in-time is a different Glassnode series. No revision has been observed. A later report will record a data delay or a changed stored point, and this pull request does not build that report.

## Recommendation

Store each Glassnode series in a **narrower metric store**: one row per `(metric, asset, interval, timestamp)` holding `v`. Do not write those series into `BT.API_REQUEST_PAYLOAD`.

Leave the `BT.API_REQUEST` and `BT.API_REQUEST_PAYLOAD` rows that already exist where they are. Do not purge them, do not rewrite them, and do not drop a partition.

`MARKET_DATA.PRICE_BAR` is the wrong table for this. A price bar there is an immutable fact (see [Scheduler, price bars](scheduler-price-bars.md)). A Glassnode point is a vendor series that may be rewritten later. The first write would own the primary key, and a later correction would hit the same unique-violation path the bar service treats as a lost race.

The narrower store is not in this change. The [harness](#harness) is, so a later copy of the same window can show a rewrite. The later store keeps history and purges closed copies. That purge is not a delete of the live rows and not a vague archive. It is a later pull request and is not built here.

## What was checked

Read in the repo:

- `quant/data/sources.py` — `Glassnode.get_historical_price`
- `quant/strategy/backtest_service.py` — `fetch_df`
- `quant/data/backtest_cache.py` — `read_payload` / `refresh_payload`
- `quant/strategy/performance.py` — `_factor_series_for_sub`
- `db/liquidbase/bt/tables/API_REQUEST.sql` and `API_REQUEST_PAYLOAD.sql`
- `db/liquidbase/bt/procedures/SP_INS_API_REQUEST.sql`, `SP_GET_API_REQUEST.sql`, `SP_GET_API_LIMIT_CHK.sql`
- `db/liquidbase/refdata/data/APP_METRIC.sql`, `API_LIMIT.sql`, `DATA_COLUMN.sql`
- [Alternative data sources](alt-data-sources.md), [Separate underlying](separate-underlying.md), [Scheduler, price bars](scheduler-price-bars.md)

A live check was already done on a machine outside the repo, at 2026-10-03 02:13 HKT. This change did not repeat it and did not use an API key. The Professional plan has been in use since 28 Sep 2026 18:00 HKT. The six metric paths below answered on that plan, for BTC, interval `24h`, unix window `1577836800`–`1579046400` (1 Jan 2020 through 14 Jan 2020 UTC). Each successful body was a JSON list of `{t, v}`, 14 points. `market/price_usd_close` with `a=NOTACOIN` was HTTP 400, `text/plain`, body starting `parameter a=NOTACOIN is invalid, allowed values=[`. Response headers on the successful calls included `x-rate-limit-limit: 600`, `x-rate-limit-remaining` decrementing by 1 per call, and `x-rate-limit-reset` around 20 seconds.

Not checked, so not claimed:

- The live catalog. The source DDL and `SP_INS_API_REQUEST` disagree on `API_REQUEST_PAYLOAD` columns (below). Which one production matches is unknown here.
- Row counts or byte sizes of `API_REQUEST` / `API_REQUEST_PAYLOAD`.
- A second fetch of the same window. No historical rewrite has been seen.
- The success `Content-Type` header, the absolute `x-rate-limit-remaining`, the exact reset timestamp, a 429 body, and the rest of the 400 allowed-values list.
- Values for MVRV, active count, exchange-transfer volume, and hash rate. Those four returned 200 with the `{t, v}` shape. The numbers were not retained.
- Any sub-daily body. The captured interval is `24h`.

The real 2026-10-03 bodies stay outside the repo so a later fetch of the same window can be compared with them. The files under `tests/fixtures/glassnode/` are an offline shape contract, generated without a live call. Where a number was retained, the fixture keeps that literal. Every other `v` is the synthetic filler `0`.

## What the client does

`Glassnode` in `quant/data/sources.py` has one method, `get_historical_price`. It GETs `https://api.glassnode.com/v1/metrics/` plus the `metric_path` argument, with query params `a`, `s`, `u`, `i` and the key in the `X-Api-Key` header. `GLASSNODE_API_KEY` is already in the process environment: `load_config()` loads it from SSM when `USE_SSM=1`, otherwise from `.env`. The class reads that variable and does not load a file. The default `i` is `24h`. `fetch_df` takes that path from the `REFDATA.APP_METRIC` row for the data source the request named. Choosing Glassnode in the UI is that request. The method does not fill in a path when the row has none. It then calls `raise_for_status()` and `pd.read_json`. There is no page loop and no read of the rate-limit headers. `fetch_df` increments `CONFIG.API_LIMIT.CALL_COUNT` before this method on the provider path. The method itself does not.

`s` and `u` are built with `time.mktime`, which is the machine's local timezone. The 3 Oct window was UTC unix time. The harness stores that unix window and does not call `mktime`. A backtest on a host that is not UTC asks Glassnode for a different window than the fixture.

`fetch_df` in `quant/strategy/backtest_service.py` resolves the metric name `"price"` and, when refresh is on, calls the provider once for the whole `[start, end]`. It then clears the method's `lru_cache`. The frame it stores has `price` and `factor`, both set from `v`. Columns `Open`, `High`, `Low`, `Close`, and `Volume` are copied only when the provider frame already has them. Glassnode's `{t, v}` body does not.

A provider interval shorter than one day is refused before that call. The class will forward `i=1h` if something calls it directly (the unit test does). The backtest path will not.

`refresh_dataset` false reads `BT.API_REQUEST` through `BacktestCache.read_payload` and does not call Glassnode. `refresh_dataset` true fetches the full requested range and inserts a new version. The payload-table comment says the app fetches a delta and merges. The Python replaces the whole range. `SP_GET_API_REQUEST` returns the current row (`TRANSACT_TO_TS = 9999-12-31`) inner-joined to its payload. Closed versions are not what the next backtest reads.

## What a strategy can use

| Metric path | In `Glassnode` | In `REFDATA.APP_METRIC` | In the alt-data page | Seen 2026-10-03 |
|---|---|---|---|---|
| `market/price_usd_close` | yes, when `metric_nm` is `price` | yes, `metric_nm = price` | price client already existed | 200, 14 points, anchors retained |
| `indicators/sopr` | no | yes, `metric_nm = sopr`, release `1.28.0` | sketch only | 200, `{t, v}`, anchors retained |
| `market/mvrv` | no | yes, `metric_nm = mvrv`, release `1.28.0` | sketch only | 200, `{t, v}`, values not retained |
| `addresses/active_count` | no | yes, `metric_nm = active_address_count`, release `1.29.0` | sketch only | 200, `{t, v}`, values not retained |
| `transactions/transfers_volume_to_exchanges_sum` | no | yes, `metric_nm = exchange_inflow_volume`, release `1.29.0` | sketch only | 200, `{t, v}`, values not retained |
| `mining/hash_rate_mean` | no | yes, `metric_nm = hash_rate_mean`, release `1.28.0` | sketch only | 200, `{t, v}`, values not retained |

`METRIC_NM` is snake_case of `DISPLAY_NAME`. A parenthetical qualifier is a suffix, so "(point-in-time)" is `_pit`. It is not the vendor path. `METRIC_PATH` is that path. `DATA_CATEGORY` is the subject — `PRICE`, `VALUATION`, `NETWORK`, `FLOW` — and a later provider of the same series uses the same subject. Close price stays `metric_nm = price` on every app that has a close.

`get_onchain_metric` exists only as a sketch in [Alternative data sources](alt-data-sources.md). It is not a method on the class. The class requests the `METRIC_PATH` it is given. A backtest still resolves metric name `price`, so another catalog row is not what that run fetches.

`fetch_df` always asks for the metric name `price`. `REFDATA.DATA_COLUMN` offers `price` (column `price`) and `Volume` (column `Volume`). A Glassnode frame has `price` and `factor`. A factor whose `data_column` is `Volume` looks that column up on the frame in `Performance._factor_series_for_sub` and will not find it.

The factor model is another symbol, or another column on that symbol's frame. It is not a second metric of the same symbol. `_build_data_dict` keys frames by cusip. Two metrics of `btcusdt.crypto` do not fit.

## Sleeve factors

A check already run on 3 Oct 2026, outside this repo, dated three series the research sleeves might use. They do not share a window. This change did not call Glassnode again. No response body for these paths is in the repo. The [harness note](#harness) records the rule that was chosen before any run.

The sleeve those facts were checked against is the 2021 to mid-2024 window. On the research page that window is the blend from 8 Oct 2021 through 30 Jun 2024, and BTC at its own Bollinger z-score window 60 above 2.25 is the BTC sleeve ([Chin Shum review](../research/chinshum-review.md)).

| Series | What was checked | 2021 to mid-2024 |
|---|---|---|
| `transactions/transfers_volume_exchanges_net_pit` | Point-in-time exchange netflow volume. BTC starts 11 Dec 2019. ETH starts 15 Feb 2022. BNB is not a valid asset. | BTC covers the window. ETH does not cover the whole window. BNB cannot be requested. |
| `indicators/sopr_pit`, `market/mvrv_z_score_pit` | Both start 27 Jun 2025. | A from-July-2025 check only. |
| `distribution/exchange_net_position_change` | Exchange balance change, the BNB stand-in, because netflow volume rejects BNB. The restated series starts 29 Aug 2020. The point-in-time twin `distribution/exchange_net_position_change_pit` starts 23 Jun 2025. | The point-in-time twin does not cover 2021–2024. The restated series is not a backtest for that window. |

A full-window Sharpe on the restated `indicators/sopr` or `market/mvrv_z_score` series would be look-ahead. The January 2020 `indicators/sopr` fixture is a 14-day shape sample of that restated path, with synthetic middles. It is not that Sharpe. `market/mvrv` in the same sample is not `market/mvrv_z_score`.

The research room named the child before any result. The application will store that column and read it as factor one. The sentences below are that behavior. They are not a number for a person to apply by hand.

The raw point-in-time BTC exchange netflow series (`transactions/transfers_volume_exchanges_net_pit`) has no exact zeros in the saved copy from 11 Dec 2019 through 1 Oct 2026 (2487 days, 0 nulls, smallest absolute value about 2.56). The 2021-07-01 to 2024-06-30 window is 1096 days and also has no exact zero. A non-zero gate on the raw series never turns the sleeve off, so it is not the child.

The named series, chosen before a result, is 1 when that point-in-time value is below zero, and 0 otherwise. No other cut. The application stores the 0. Dropping zero days is not allowed. In the saved copy that column is 0 on 702 days and 1 on 1785 days. That is a count of the named rule, not a backtest result.

That 0/1 column is factor one. BTC 60/2.25 stays factor two. `combine_positions` already implements a two-factor FILTER as gate then direction (`quant/strategy/signals.py`, decision #6). The 0/1 column has to be first. Put second, the sleeve's direction is thrown away. The gate indicator is `get_sma` with window 1, so a stored 0 stays off and a stored 1 stays on. A wider window or a Bollinger is not this series. `momentum_band_signal` is long only when the indicator is above its signal threshold. The signal threshold on the SMA (window 1) of the 0/1 outflow column has to sit strictly between 0 and 1. Any value in that open range leaves a stored 0 off and a stored 1 on, so the threshold is not a search and do not pick or recommend a specific number inside the range. The sleeve's 2.25 is not the gate's threshold. A threshold of 2.25 would leave the gate off every day, because a 1 is never above 2.25.

SOPR and MVRV z-score stay a from-July-2025 check only.

The harness locks this rule without restating it; the wording under [Sleeve factors](#sleeve-factors) is the source.

None of these paths is a method on `Glassnode`. Release `refdata/1.28.0` seeds them on `REFDATA.APP_METRIC`. `fetch_df` requests the `METRIC_PATH` of the `metric_nm` it is given. A backtest passes `price`, so these rows are not what that run fetches. The later store is not built here.

### One request for the window, then local bars

Price already works this way when the cache hits. One refresh is one HTTP call for the whole window (the client does not paginate, and the captured bodies are one JSON list). `refresh_payload` stores that frame. The next run with refresh off slices it. The indicator walks the column in memory. There is no HTTP call per bar on this path.

An on-chain series is the same shape. `fetch_df` already takes `metric_nm` and passes that row's `METRIC_PATH` to `get_historical_price`, and the cache key is that row's `APP_METRIC_ID`. A backtest passes `price`. The points still go through `refresh_payload` as one JSON document. A place to put `{t, v}` that is not that document is not built here.

The [alt-data page](alt-data-sources.md) deferred the five on-chain paths because Professional was $799/mo. That reason is stale. The plan has been active since 28 Sep 2026 18:00 HKT, and those five paths plus close price answered on 3 Oct 2026. A backtest still requests close price. `REFDATA.APP_METRIC` seeds the series in release `refdata/1.28.0` (context `refdata,prod-deploy`). `fetch_df(..., metric_nm=...)` is the call that requests another row's path. Cost is no longer what blocks a strategy from reading SOPR. The fetch and the store are.

## API_REQUEST, as it is

`BT.API_REQUEST` is the subscription header: app, metric, interval, cusip, range, and a version window. `BT.API_REQUEST_PAYLOAD` is supposed to hold the whole series as one JSONB document per version. `SP_INS_API_REQUEST` closes the current header (`TRANSACT_TO_TS = now`) and inserts the next version plus a payload row.

Three facts in the source make this a poor place to put more Glassnode series.

**The write copies the whole series on every refresh.** `refresh_payload` serialises the fetched frame and sends it as `IN_PAYLOAD`. The previous version stays. The reader only joins the current version, so the closed JSONB is not what a replay sees. [Backtest data hygiene](2026-09-25-backtest-data-hygiene-proposal.md) already says a refreshed provider cache is a different series and Sharpe can move. Closed rows are the only record of the previous series, and nothing in the app reads them.

**The payload table and the insert do not describe the same row.** The table columns are `API_REQ_ID`, `API_REQ_VID`, `PAYLOAD`, `USER_ID`, `CREATED_AT`. The procedure inserts `RANGE_START_TS` and `RANGE_END_TS` into the payload as well. Those two columns exist on the header table, not in the payload `CREATE TABLE`. No later changeset alters the payload table. A live catalog was not queried, so this is source drift, not a measured production failure. New Glassnode writes should not depend on it until that catalog is checked.

**The header comment and the design-doc index are ahead of the DDL.** The payload file still says to join on `IS_CURRENT_IND = 'Y'`. The table has no such column; currency is `TRANSACT_TO_TS`. [Separate underlying](separate-underlying.md) shows a partial unique index `UX_API_REQUEST_CURRENT_SUBSCRIPTION`. That index is not in `API_REQUEST.sql`. `SP_GET_API_REQUEST` can return more than one current row, and `BacktestCache` uses the first.

The limit guard does not protect the cap. `SP_GET_API_LIMIT_CHK` counts `API_REQUEST` rows with `TRANSACT_TO_TS = 9999-12-31` and `CREATED_AT` inside the window. A refresh closes the previous row, so it leaves the count. Repeated refreshes of one subscription do not add up. The archived seed in `API_LIMIT.sql` is the free tier. Release `config/1.2.0` replaces the Glassnode rows with `requests_per_month` = 160000 over 2592000 seconds (30 days) for `APP_ID = 2`, the one API key. The procedure reads `CONFIG.API_LIMIT`. `Glassnode.get_historical_price` never calls the procedure. The 3 Oct short window (600, reset around 20 seconds) is still only a response header. The monthly cap was not a response header.

Logging already tripped over the blob. `quant/shared/db.py` truncates a logged parameter at 200 characters because one `API_REQUEST` write was a JSON string of every bar and pushed the neighbouring lines out of `docker logs`.

Size, as arithmetic on the write shape, not as a measurement: a daily series of a few thousand points, stored as datetime plus `price` plus `factor`, is on the order of a few hundred kilobytes per version. Six metrics and a hundred refreshes are hundreds of megabytes, not a full disk. That is not why a purge is dangerous. The danger is what a purge does to the current row and to WAL, below.

## Options

Costs are the ones that matter for this key: database growth, the shared 160,000 calls/month, a block of the single IP that calls Glassnode, and whether a backtest can be run again on the same series.

### Option 1 — keep the current write

Keep calling `SP_INS_API_REQUEST` with the full JSON body for every refresh, and point new Glassnode metrics at the same path.

| Cost | What happens |
|---|---|
| Database growth | Every refresh inserts another full document and leaves the previous one. Closed documents are unread by the cache and sit in the yearly `CREATED_AT` partition with the current one. |
| 160,000 / month | One refresh is one HTTP call today, because there is no page loop. The cap is shared and nothing in the Glassnode path counts it. Turning on five more metrics multiplies calls by five, still one call per series per refresh, still uncounted. |
| Single IP | The call is `requests.get` from whichever host runs the API or the worker. There is no backoff. A bug that refreshes in a loop spends the short window (600, reset around 20 seconds) and then the monthly cap from that one address. A 429 body was not captured, so the failure shape is unknown. |
| Reproducibility | A cache hit replays the current document. A refresh replaces it, including any rewrite Glassnode made, and the next backtest silently uses the new series. Old versions are stored and not read. |

This keeps working for one close-price series if the insert matches the live table. It is a weak place to put five more series, and the source DDL may already reject the insert.

### Option 2 — keep the tables, stop writing the JSONB

Keep `API_REQUEST` as the subscription header. Stop inserting the document.

| Cost | What happens |
|---|---|
| Database growth | Header rows stay small. Payload growth stops only if nothing else still needs the document. |
| 160,000 / month | Unchanged until a replacement cache serves the second request. With no document and no other store, every backtest misses and calls Glassnode again. |
| Single IP | A cache that cannot answer is a fetch. Misses from one host are the blocking risk. |
| Reproducibility | `SP_GET_API_REQUEST` inner-joins the payload. No payload means no series to replay. |

On its own this option does not serve a backtest. It is a step toward option 3 or option 4, not a store.

### Option 3 — cache outside the database

Keep the saved-copy layout the harness already reads: request identity, status, headers, raw body. Put those files on a disk or an object store both the API and the worker can see.

| Cost | What happens |
|---|---|
| Database growth | New Glassnode bytes stay out of Postgres. Existing `API_REQUEST` rows stay. |
| 160,000 / month | One fetch fills one copy. A second host that cannot see the file fetches again. The cap is still uncounted in the app. |
| Single IP | Same client, same host, unless the cache actually hits. A shared laptop disk does not exist in the deployed API and worker. |
| Reproducibility | A backtest can pin the body hash. Two copies with the same points and different bytes are a formatting difference, which the harness reports and does not treat as a rewrite. The pin has to be written down with the result, or the next read is whatever file is there now. |

This matches the revision check. It is a new shared filesystem the platform does not have. Redis today holds REFDATA snapshots, not versioned multi-year series.

### Option 4 — narrower metric store (recommended)

One row per `(metric, asset, interval, timestamp)` with `v`, written and read through stored procedures. `API_REQUEST` can stay the header that says which range was fetched, without a new full document. `PRICE_BAR` stays the immutable exchange print.

| Cost | What happens |
|---|---|
| Database growth | A point is a timestamp and a number. A refresh of an unchanged day does not store a second copy of the whole history. When a value changes, the later store keeps that history. Alfred's archive path is a purge of closed copies, not a delete of the live rows and not a vague archive. That purge is not built here. |
| 160,000 / month | Still one HTTP call per series per refresh. The series is then reused from the table, which is the same "one request, then local bars" path price already has on a cache hit. The cap still needs a counter that counts calls, which `SP_GET_API_LIMIT_CHK` does not. |
| Single IP | The fetch stays on one host. The store does not add calls. A loop that ignores the table would. Shipping the store without a call counter leaves that loop possible. |
| Reproducibility | A backtest that reads the live table sees the current points. The later store keeps history. Alfred's archive path is a purge of closed copies, not a delete of the live rows and not a vague archive. That store is a later pull request and is not built here. Keeping that history is not the point-in-time series. Point-in-time is a different Glassnode series. The copies outside the repo stay the log of a rewrite. Exchange bars stay on `PRICE_BAR` under their own `SOURCE_APP_ID`, so a Glassnode close and a Bybit close do not share a key. |

The later store is a later pull request. This page does not add a table, a changeset, or purge SQL.

## A purge is an option, not this change

[Separate underlying](separate-underlying.md#future-work-scheduled-purge-of-closed-versions) describes a future purge of closed `API_REQUEST` versions. The payload file comments that the purge path is dropping a partition. Neither is implemented, and this change does not implement them. There is no `DELETE`, no `DROP`, and no `SP_PURGE_*` in this change. The later Glassnode store's path is the same kind of step: a purge of closed copies, not a delete of the live rows and not a vague archive. This page does not add that purge.

Blast radius, if someone does it later:

- `API_REQUEST_PAYLOAD` is partitioned by `CREATED_AT`, yearly, via `pg_partman`. A current payload and the closed payloads written in the same year share a partition.
- Dropping that partition removes the document `SP_GET_API_REQUEST` inner-joins. The next backtest misses. The following refresh refetches every series from one IP and writes a new full document, against the shared monthly cap.
- The header rows are not in that partition. After the payload is gone they point at nothing.
- Deleting the JSONB row by row rewrites those documents into WAL. That is a rewrite proportional to the stored history, on the database the app is reading. The 2026-08-16 migration is the reminder that a wide `BT` rewrite dies in the middle. A purge of this table is that shape.
- Closed versions are the only copy of a previous series. Removing them removes the ability to see what an earlier backtest would have read. The app does not read them today, which is a reason to stop creating them, not a reason to delete them first.
- A safe drop needs a partition scheme that does not put the current row in the dropped set, and a count of rows and bytes from the live catalog. Neither exists here.

Do that work as its own change, after those two facts are known. Do not attach it to a Glassnode feature.

## Revisions

Glassnode is rumored to revise history after the fact. This repo has not seen that happen. The harness must not contain a second copy that pretends it did. `tests/fixtures/glassnode/later/` is a suite failure on purpose.

A saved copy is a directory with three files:

| File | What it holds |
|---|---|
| `request.json` | `metric_path`, `asset`, `interval`, `since`, `until`. `captured_at` is stored and not compared. |
| `response.meta.json` | HTTP status and headers. |
| `response.body` | Raw bytes. |

Comparison (`compare_copies` in `quant/data/glassnode_response.py`):

- The request identity has to match. A different asset or window is a different request, not a revision.
- JSON number literals are kept as text. `1` and `1.0` differ. Float round-trip is not the comparison.
- Points are joined on `t`. A different `v` at the same `t` is a value revision. A timestamp only on one side is a value revision. A duplicate `t` inside one body is a value revision.
- Status, content type (parameters such as `charset` stripped), and any header that is not in the two lists below are reported and fail `--compare`.
- A plain-text body, including the 400, is compared as text. A change in that text is visible.
- The body hash is reported when the bytes differ and the points do not. That is formatting, and `--compare` does not fail it.

Allowed to change without failing `--compare`:

| Header | Why |
|---|---|
| `x-rate-limit-remaining` | Moves by 1 on each call. The absolute value from 3 Oct was not retained. |
| `x-rate-limit-reset` | Described as about 20 seconds. It is a clock, not a point. |

`x-rate-limit-limit` is reported as a quota change. It does not fail `--compare`, and it is not a rewrite of `v`. The committed fixtures store `600` because that value was observed. They do not store a made-up remaining.

`captured_at` may change. It is when the copy was taken.

What a revision looks like, once two real directories exist: `--compare earlier later` prints `t=<unix> <old literal> -> <new literal>` and exits 1. Until those directories exist, the suite step `revision` passes with the line that no second copy is in the fixture root.

A unit test plants a one-point delta in memory to prove the comparator prints it. That delta is not a Glassnode response and it is not a fixture.

## Harness

```bash
python scripts/glassnode_local_harness.py --suite
python scripts/glassnode_local_harness.py --suite --json
python scripts/glassnode_local_harness.py --compare earlier_dir later_dir
```

`--suite` reads `tests/fixtures/glassnode/manifest.json`. A missing manifest, a missing case file, or an empty root fails the process. CI runs the suite through `tests/unit/test_glassnode_harness.py`. Nothing in that path calls Glassnode.

| Case | What it locks |
|---|---|
| `price_usd_close_btc_24h` | 200, JSON list, 14 daily points, observed first and last `v`, synthetic middles |
| `sopr_btc_24h` | Same, with the observed SOPR anchors. Not a method on `Glassnode` |
| `mvrv_btc_24h` | 200 and the `{t, v}` shape. Values are fillers. Not wired |
| `active_count_btc_24h` | Same |
| `transfers_volume_to_exchanges_sum_btc_24h` | Same |
| `hash_rate_mean_btc_24h` | Same |
| `notacoin_price_usd_close` | 400, `text/plain`, body prefix only. The allowed-values list was not retained |
| `empty_json_list` | 200 and `[]`. The client and `refresh_payload` accept an empty frame and insert nothing. This body was not observed |
| `pagination` | The client issues one GET. The sample body is one list and has no cursor. No paginated body was captured |
| `rate_limit` | Short window `600` on the successful fixtures. Remaining and reset are described. Monthly cap 160,000 is an operator figure, not a header. No 429 body |
| `interval` | Every series case is `24h`. No sub-daily body is in the corpus |
| `sleeve_factors` | The three series above. Only BTC point-in-time netflow covers 2021 to mid-2024. The child is the stored 0/1 column, not a non-zero gate on the raw series. The rule text is fixed. A missing contract file fails the suite |
| `revision` | No second copy. Fails if `later/` appears under the fixture root |

The parser is `quant/data/glassnode_response.py`. `Glassnode.get_historical_price` does not call it, so this change does not alter a backtest or a live order.

## Later store

Alfred has rejected latest-only storage. The later Glassnode store keeps history. Alfred's archive path is a purge of closed copies, not a delete of the live rows and not a vague archive. That store is a later pull request and is not built here.

Keeping that history is not the point-in-time series. Point-in-time is a different Glassnode series. The sleeve factor note is already chosen and is not this store: the 0/1 column is factor one, BTC 60/2.25 stays factor two, the gate indicator is an SMA with window 1, and SOPR and MVRV z-score stay a from-July-2025 check only.

The external copies are the log of a rewrite. The `*_pit` paths are separate Glassnode series, already named in the sleeve note.

The monthly row is release `config/1.2.0` (decision #93). The counter columns are release `config/1.3.0`, and `BT.SP_RESERVE_API_CALL` is release `bt/1.27.0` (decision #94). Contexts are `config,prod-deploy` and `bt,prod-deploy`. `SP_GET_API_LIMIT_CHK` still counts current subscription rows.

## Call count

`CONFIG.API_LIMIT` holds the threshold and the count on the same row. `CALL_COUNT` is how many calls have been reserved since `WINDOW_FROM_TS`. `BT.API_REQUEST` stays the stored series. There is no row per call.

`BT.SP_RESERVE_API_CALL` takes the app id and updates that app's limit rows. An open window adds one to `CALL_COUNT`. An elapsed window, or a null `WINDOW_FROM_TS`, sets the count to 1 and `WINDOW_FROM_TS` to the transaction time. The procedure does not take a user id and does not refuse the call. The whole window resets together.

`fetch_df` calls `BacktestCache.reserve_api_call` on the provider path, after the catalog path is known and immediately before `get_historical_price`. A missing path does not reserve. `read_payload` does not reserve. `Glassnode` stays a client: it has no database handle, and a direct call that skips `fetch_df` is outside this count. The short window of 600 is still only a response header. The 160,000 calls per 30 days stay the `MAX_VALUE` on the Glassnode row. This procedure does not read that maximum.

## What this change does not do

- No new HTTP calls, no new `API_REQUEST` writes, no migration, no purge SQL.
- No metric table, no changeset, and no purge SQL. The later store is a later pull request.
- `get_historical_price` takes the catalog path. A backtest still requests close price. The narrower store and the purge are not built.
- No API key. Tracked files have a placeholder in `.env.example` (`your_key_here`). No live key was found in tracked files.
