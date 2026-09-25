# Backtest data hygiene — proposal

**Doc type:** proposal. Nothing here is adopted.
**Status:** open. This page does not change the engine, the schema, or any stored row.
**Reviewed against:** `main` at `85fa94409` (2026-09-25), including the [backtest review](2026-09-25-backtest-review.md).

The engine now compounds simple returns and reads drawdown off that equity curve. Rows written before the worker that does this came up still store the old annual return, total return, max drawdown, and Calmar. Sharpe, on a long enough sample, is the same number either way. Strategy identity is still the full display name, so a change of bar interval starts a new lineage. The catalog still shows every Best version, including ones a user would not want to trade.

This proposal covers three decisions the owner has to make: how to clean the old rows, whether one recipe should be one `STRATEGY_ID` across intervals, and which versions the catalog shows. Adopting any of them is a new decision-log entry. A procedure or schema change still needs its own changeset, with `context` set to the schema only, until the owner asks for `prod-deploy`.

## What was confirmed

Confirmed means it was read from git history, the GitHub Actions log, or the code and DDL in this tree. Inferred means it follows from those facts and was not checked against production. This page did not connect to a database, did not enqueue a job, and did not trade.

| Claim | Status |
|---|---|
| Compounding and geometric annualisation landed in one commit, `d1ddb557b` (2026-09-22 17:55 +0800) | Confirmed |
| The prod worker running that commit was up at **2026-09-22 10:00:43 UTC** | Confirmed from the deploy log |
| No column stores an engine version or git SHA | Confirmed from the DDL |
| Sharpe is computed from the per-bar series and does not read the equity curve | Confirmed in `quant/strategy/performance.py` |
| A drawdown above 1 cannot be produced by the new formula | Confirmed by the equity floor in `_compound()` and `tests/unit/test_perf.py` |
| The 31-job replay on 2026-09-22 ran, and a second deploy restarted the worker during it | Confirmed from the capacity review and the second deploy log. Which rows it replaced is **not** confirmed |
| Job `8252fe48-a90b-4cc3-a72c-f7a4af7915bc` still stores 35.4% and 20.8% | **Reported by the owner.** The same before/after pair is the archive's local replay of the deployed BTC parameters. This page did not read the row |
| Date range is already a version attribute when the name string matches | Confirmed in `buildStrategyNm` and `BT.SP_INS_STRATEGY` |
| Bar interval is part of the identity string, on purpose | Confirmed. Decision #58 and release `1.19.0` |
| Why BNB job `adb36235-e492-4f3e-aec4-59fb2bb81e9d` minted `5489c9bd` | **Not confirmed.** The SQL below shows the name that job stored |

## Stale stored results

### The switch

The geometric switch is one commit, not two.

| | |
|---|---|
| Commit | `d1ddb557b3d5409033dda175bba859a8c0f4f9b1` |
| Author date | 2026-09-22 17:55:19 +0800 |
| Subject | Compound backtest returns and drawdowns; re-run stored results after deploy |
| What changed in code | `quant/strategy/performance.py`: `_compound()` and `_cagr()`. Same helper for the strategy series and the buy-and-hold series |
| Prod deploy | [Actions run 35713312990](https://github.com/alfred1123/Quant_Strategies/actions/runs/35713312990), push of that SHA. The `deploy to EC2` job logged `quant-worker` on image `quant-app:d1ddb557b…` as **Up** at **2026-09-22 10:00:43 UTC** |
| Schema change | None. The deploy skipped `migrate database` |

`_compound()` sets `equity = (1 + pnl).clip(lower=0).cumprod()` and drawdown to `1 - equity / peak`, with the peak floored at 1. `_cagr()` is `equity ** (trading_period / n) - 1`. Before that commit, `cumu` was `pnl.cumsum()` and drawdown was `cummax - cumu`, which is unbounded. Annualised return was `pnl.mean() * trading_period`. The write-up of the defect, including the BTC before/after table, is [Return compounding](../archive/return-compounding.md). Decision #73 records the choice to re-run stored rows rather than rewrite them in SQL.

An earlier, separate edit is easy to mix in and should not be. Commit `b25f410f7` (2026-05-31) changed Calmar's numerator from the mean per-bar pnl to `get_annualized_return()`. At that date the annualised figure was still the arithmetic mean. Every September result already includes that Calmar formula. It is not the boundary between 35.4% and 38.6%.

Two later deploys matter for a replay, and neither reverts compounding:

| When (UTC) | Commit | Why it matters |
|---|---|---|
| 2026-09-05 17:13 | `d0a28af0d`, [run 33980107881](https://github.com/alfred1123/Quant_Strategies/actions/runs/33980107881) | Sharpe and annualised return become null below 60 finite pnl bars (decision #63). A short sample re-run today will not reproduce its old Sharpe |
| 2026-09-06 12:11 | `b711871b9`, [run 34032211325](https://github.com/alfred1123/Quant_Strategies/actions/runs/34032211325) | Exhaustive search replaced `GridSampler` (decision #64). A job the old search did not finish can pick a different cell on replay |
| 2026-09-06 12:51 | `437026a3e`, [run 34034169865](https://github.com/alfred1123/Quant_Strategies/actions/runs/34034169865) | Default fee became 10 bps (decision #65). Replay uses `CONFIG_JSON.fee_bps` when the key is present |
| 2026-09-22 10:05–10:42 | — | [Capacity review](../archive/infra-capacity-review.md) records `scripts/rerun_results.py` draining 31 jobs. That window starts after the new worker was up |
| 2026-09-22 10:27:32 | `e215dbc6c`, [run 35715762005](https://github.com/alfred1123/Quant_Strategies/actions/runs/35715762005) | Cap-fix image, still a descendant of `d1ddb557b`. The log shows `quant-worker` **Up** at 10:27:32 UTC. `WorkerLoop.recover_stale` marks every `RUNNING` row `FAILED` on boot and does not write a result |

No file under `quant/strategy/` changed between `d1ddb557b` and `85fa94409`. The one later edit to `quant/market_data/service.py` (`12cd16ca5`, decision #81) adds the still-forming candle on the live path. `read_bars`, which a backtest uses, still returns stored bars.

The cutover used everywhere below is the first moment a prod worker could write the new numbers:

```text
2026-09-22 10:00:43+00
```

A result with `CREATED_AT` before that was computed by the previous image. A result after that was computed by `d1ddb557b` or a descendant, which still compounds. A job that was `RUNNING` at 10:27:32 UTC was failed empty, so the previous result, if it is still `IS_CURRENT_IND = 'Y'`, is the one the catalog reads.

### Fields whose meaning changed

Sharpe did not change, on a sample of at least 60 finite pnl bars. Everything that reads the equity curve did. The same function feeds the strategy and the buy-and-hold series, the in-sample slice, and the out-of-sample slice (`WalkForward._evaluate` calls `get_strategy_performance()`).

| Surface | Field | Meaning after `d1ddb557b` |
|---|---|---|
| `BT.RESULT` | `TOTAL_RETURN`, `BUY_HOLD_TOTAL_RETURN` | Last point of `equity - 1`, not the sum of simple returns |
| `BT.RESULT` | `ANNUALIZED_RETURN`, `BUY_HOLD_ANNUALIZED_RETURN` | CAGR, not `mean * trading_period`. The seed text already said "Compound annual growth rate" while the code was still arithmetic |
| `BT.RESULT` | `MAX_DRAWDOWN`, `BUY_HOLD_MAX_DRAWDOWN` | Peak-to-trough on equity, in `[0, 1]`. The old value is unbounded, which is how a long-only buy-and-hold stored 1.2243 |
| `BT.RESULT` | `CALMAR_RATIO`, `BUY_HOLD_CALMAR_RATIO` | CAGR divided by the new drawdown. Both inputs moved |
| `BT.RESULT` | `SHARPE_RATIO`, `BUY_HOLD_SHARPE_RATIO` | Unchanged by this commit. Null, after 2026-09-05, when finite pnl bars are under 60 |
| `PAYLOAD_JSON` | `performance.strategy_metrics` and `performance.buy_hold_metrics` | The same five keys: `Total Return`, `Annualized Return`, `Sharpe Ratio`, `Max Drawdown`, `Calmar Ratio`. `n_obs` was added on 2026-09-05 and is absent on older payloads |
| `PAYLOAD_JSON` | `performance.equity_curve[]` | `cumu`, `dd`, `buy_hold_cumu`, `buy_hold_dd` |
| `PAYLOAD_JSON` | `performance.perf_csv` | The same columns, serialised |
| `PAYLOAD_JSON` | `walk_forward.is_metrics`, `walk_forward.oos_metrics` | Strategy metrics only, same five keys, same new meaning. There is no buy-and-hold twin inside these two dicts |
| `PAYLOAD_JSON` | `walk_forward.equity_curve[]` | Same four curve fields. This curve is the full-sample run, not the out-of-sample slice |
| `PAYLOAD_JSON` | `best.sharpe` and the grid rows | The objective. Unchanged by compounding |
| `BT.PROMOTION.GATE_RESULTS` | `value` on `max_dd_gate` | Snapshot of the drawdown the gate saw. A later result does not rewrite it |

Promotion reads `performance.strategy_metrics` only (`quant/promotion/evaluate.py`). It does not read walk-forward, and it does not read the buy-and-hold columns. Those columns still change meaning, and the Promotion tab renders them.

The worker shreds the payload into the columns in one insert (`quant/queue/result_metrics.py` into `BT.SP_INS_RESULT`). A current row should have the column and the JSON agree. The census query flags rows where they do not.

There is no engine-version column. `BT.RESULT`, `BT.QUEUE`, and `BT.STRATEGY` were read for one. Identity of the code that wrote a row is the timestamp against the cutover above.

### How to find every affected row

`BT.RESULT` is inserted once per completed queue id. A replay is a new `QUEUE_ID` and a new `RESULT_VID` on the same `(STRATEGY_ID, STRATEGY_VID)`. `IS_CURRENT_IND = 'Y'` is the row the catalog and live apply read. The original job page reads the result for that `QUEUE_ID`, which is never updated. Job `8252fe48-…` can show 35.4% and 20.8% forever, including after a successful replay has written a newer current row for the same version.

The owner's reported pair matches the archive's BTC replay: strategy annualised 35.4% to 38.6%, drawdown 0.2080 to 0.194, Sharpe 1.481, buy-and-hold max drawdown 1.2243 to 0.767. That is evidence the stored job is on the old convention. It is not a count of how many current rows are.

Drawdown above 1 is proof of the old formula. The new code cannot emit it. The converse is false: the BTC strategy's old drawdown was 0.208, which is a legal new-formula number as well. The timestamp is the net. The `> 1` check is the knot that does not depend on the clock.

All statements below are read-only. They are for the owner to run. They were not executed for this proposal.

```sql
-- Cutover: prod worker on d1ddb557b reported Up.
-- 2026-09-22 10:00:43 UTC. Deploy run 35713312990.

-- 1. The reported BTC job, and whether a later current row exists
--    for the same version.
SELECT r.queue_id,
       r.result_id,
       r.strategy_id,
       r.strategy_vid,
       r.result_vid,
       r.is_current_ind,
       r.created_at,
       r.sharpe_ratio,
       r.annualized_return,
       r.total_return,
       r.max_drawdown,
       r.calmar_ratio,
       r.buy_hold_sharpe_ratio,
       r.buy_hold_annualized_return,
       r.buy_hold_total_return,
       r.buy_hold_max_drawdown,
       r.buy_hold_calmar_ratio
  FROM bt.result r
 WHERE r.queue_id = '8252fe48-a90b-4cc3-a72c-f7a4af7915bc'
    OR (r.strategy_id, r.strategy_vid) IN (
           SELECT strategy_id, strategy_vid
             FROM bt.result
            WHERE queue_id = '8252fe48-a90b-4cc3-a72c-f7a4af7915bc'
       )
 ORDER BY r.strategy_id, r.strategy_vid, r.result_vid;
```

```sql
-- 2. Every current row still on the old convention.
--    This is the set promotion and the Trade picker trust today.
SELECT r.strategy_id,
       r.strategy_vid,
       s.strategy_nm,
       s.is_best_ind,
       s.logical_delete_ind,
       r.queue_id,
       r.result_vid,
       r.created_at,
       r.sharpe_ratio,
       r.annualized_return,
       r.total_return,
       r.max_drawdown,
       r.calmar_ratio,
       r.buy_hold_max_drawdown,
       r.buy_hold_annualized_return,
       r.buy_hold_total_return
  FROM bt.result r
  JOIN bt.strategy s
    ON s.strategy_id = r.strategy_id
   AND s.strategy_vid = r.strategy_vid
 WHERE r.is_current_ind = 'Y'
   AND r.created_at < TIMESTAMPTZ '2026-09-22 10:00:43+00'
 ORDER BY r.created_at;
```

```sql
-- 3. Proof, independent of the clock: a drawdown above 1.
--    Includes historical RESULT_VIDs, not only the current one.
SELECT r.queue_id,
       r.strategy_id,
       r.strategy_vid,
       r.result_vid,
       r.is_current_ind,
       r.created_at,
       r.max_drawdown,
       r.buy_hold_max_drawdown
  FROM bt.result r
 WHERE r.max_drawdown > 1
    OR r.buy_hold_max_drawdown > 1
 ORDER BY r.created_at;
```

```sql
-- 4. Column vs JSON. One insert writes both; a mismatch is a shredded row
--    that does not match the payload the UI draws.
SELECT r.queue_id, r.result_vid, r.created_at
  FROM bt.result r
 WHERE r.max_drawdown IS DISTINCT FROM
       (r.payload_json #>> '{performance,strategy_metrics,Max Drawdown}')::numeric
    OR r.annualized_return IS DISTINCT FROM
       (r.payload_json #>> '{performance,strategy_metrics,Annualized Return}')::numeric
    OR r.total_return IS DISTINCT FROM
       (r.payload_json #>> '{performance,strategy_metrics,Total Return}')::numeric
    OR r.sharpe_ratio IS DISTINCT FROM
       (r.payload_json #>> '{performance,strategy_metrics,Sharpe Ratio}')::numeric
    OR r.buy_hold_max_drawdown IS DISTINCT FROM
       (r.payload_json #>> '{performance,buy_hold_metrics,Max Drawdown}')::numeric;
```

```sql
-- 5. Walk-forward blocks on the old convention. The columns above do not
--    store these. Null walk_forward (the flag was off) drops out of the
--    numeric comparison.
SELECT r.queue_id,
       r.created_at,
       r.is_current_ind,
       (r.payload_json #>> '{walk_forward,is_metrics,Annualized Return}')::numeric AS is_ann,
       (r.payload_json #>> '{walk_forward,is_metrics,Max Drawdown}')::numeric      AS is_dd,
       (r.payload_json #>> '{walk_forward,oos_metrics,Annualized Return}')::numeric AS oos_ann,
       (r.payload_json #>> '{walk_forward,oos_metrics,Max Drawdown}')::numeric      AS oos_dd,
       (r.payload_json #>> '{walk_forward,is_metrics,Sharpe Ratio}')::numeric       AS is_sharpe,
       (r.payload_json #>> '{walk_forward,oos_metrics,Sharpe Ratio}')::numeric      AS oos_sharpe
  FROM bt.result r
 WHERE r.created_at < TIMESTAMPTZ '2026-09-22 10:00:43+00'
   AND r.payload_json ? 'walk_forward'
   AND r.payload_json->'walk_forward' <> 'null'::jsonb;
```

```sql
-- 6. Replay jobs that died at the 10:27:32 UTC worker restart, or any
--    other FAILED row whose version still has an old current result.
--    QUEUE_STATUS.NAME is the lookup. The active queue row is the open
--    transact window.
SELECT q.queue_id,
       q.strategy_id,
       q.strategy_vid,
       q.created_at AS failed_at,
       q.error_text,
       r.created_at AS current_result_at,
       r.max_drawdown,
       r.annualized_return,
       r.sharpe_ratio
  FROM bt.queue q
  JOIN refdata.queue_status qs
    ON qs.queue_status_id = q.queue_status_id
  JOIN bt.result r
    ON r.strategy_id = q.strategy_id
   AND r.strategy_vid = q.strategy_vid
   AND r.is_current_ind = 'Y'
 WHERE q.transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
   AND qs.name = 'FAILED'
   AND r.created_at < TIMESTAMPTZ '2026-09-22 10:00:43+00'
 ORDER BY q.created_at;
```

`scripts/rerun_results.py` skips logically deleted strategies, because `SP_GET_STRATEGY_LIST` omits them. Query 2 includes them (`logical_delete_ind`). Their current figures stay old unless someone re-runs them on purpose.

### Cleanup

Four ways to treat a current row whose `CREATED_AT` is before the cutover:

| Option | What happens to the old numbers | What promotion reads afterwards | Audit |
|---|---|---|---|
| Recompute in place | `UPDATE` the current `BT.RESULT` columns and `PAYLOAD_JSON` | The new numbers, with no `RESULT_VID` trail | The number promotion used is gone |
| Recompute into a new result version | A new queue id, a new `RESULT_VID`, `IS_CURRENT_IND` flips | The new numbers. The old row stays `IS_CURRENT_IND = 'N'` | The old payload, the old gate snapshot, and the new decision row all remain |
| Flag as stale | Rows stay | The old numbers, with a chip | Intact, and still wrong when a new run is ranked against them |
| Archive | `LOGICAL_DELETE_IND = 'Y'` | Hidden from the picker. History keeps the old figures | Intact. The recipe is hidden because the metric convention was wrong |

**Recommend flag, then recompute into a new result version, then check that Sharpe matched.**

Flagging is how the catalog stops trusting the old number the day the SQL comes back. Recomputing is how the number becomes the one the engine now prints. Archiving uses decision #66's "do not trade this" flag for a different problem. Rewriting in place destroys the only record of what the gate saw, and it cannot be done in SQL anyway: the payload has the metric dicts and the equity curve, not the per-bar position series those were built from. That limit is why decision #73 already chose a queue replay. This proposal keeps that choice and adds the two steps the 2026-09-22 replay did not record: a census, and a Sharpe check before anyone trusts the new current row.

`scripts/rerun_results.py` is the replay. It enqueues the same `(STRATEGY_ID, STRATEGY_VID)` as the stale current result, so it does not mint a strategy version. The worker writes the new result and then calls promotion, which inserts a new `BT.PROMOTION` row and may move `IS_BEST_IND`. Run it only against a worker image that is `d1ddb557b` or a descendant. A replay on the old image writes a fresh timestamp on the old numbers, and the script then treats the row as done. The image that is up as of `85fa94409` qualifies. Pass the cutover explicitly:

```bash
python -m scripts.rerun_results --user-id <uuid> --dry-run \
    --cutover 2026-09-22T10:00:43+00:00
```

The script's own notes still apply. The per-user queue cap is 30, so one pass can defer the rest and a second pass picks them up. Logically deleted lineages are skipped. This proposal does not run the script.

Acceptance, after the batch, is another read:

```sql
-- 7. Versions that now have a post-cutover current result and still
--    keep a pre-cutover result. Sharpe should match at 4 decimal places
--    on a sample that had at least 60 finite pnl bars. A larger gap means
--    the series or the chosen cell moved, and the row is a different
--    backtest, not only a convention fix.
WITH current_result AS (
    SELECT *
      FROM bt.result
     WHERE is_current_ind = 'Y'
       AND created_at >= TIMESTAMPTZ '2026-09-22 10:00:43+00'
),
old_result AS (
    SELECT DISTINCT ON (strategy_id, strategy_vid)
           *
      FROM bt.result
     WHERE created_at < TIMESTAMPTZ '2026-09-22 10:00:43+00'
     ORDER BY strategy_id, strategy_vid, result_vid DESC
)
SELECT n.strategy_id,
       n.strategy_vid,
       o.queue_id AS old_queue_id,
       n.queue_id AS new_queue_id,
       o.sharpe_ratio AS old_sharpe,
       n.sharpe_ratio AS new_sharpe,
       o.annualized_return AS old_ann,
       n.annualized_return AS new_ann,
       o.max_drawdown AS old_dd,
       n.max_drawdown AS new_dd,
       o.buy_hold_max_drawdown AS old_bh_dd,
       n.buy_hold_max_drawdown AS new_bh_dd,
       o.payload_json #>> '{best,window}' AS old_window,
       n.payload_json #>> '{best,window}' AS new_window,
       o.payload_json #>> '{best,signal}' AS old_signal,
       n.payload_json #>> '{best,signal}' AS new_signal
  FROM current_result n
  JOIN old_result o
    ON o.strategy_id = n.strategy_id
   AND o.strategy_vid = n.strategy_vid
 ORDER BY n.strategy_id, n.strategy_vid;
```

Hold a version out of the "convention fixed" set when any of these is true:

- `new_sharpe` and `old_sharpe` differ past the fourth decimal, and the old payload's `n_obs` is null or at least 60. The fourth decimal is the precision the owner quoted (1.4815), not a statistical bound.
- `new_dd` or `new_bh_dd` is above 1. The new formula cannot do that. Something else wrote the row.
- `new_window` or `new_signal` differs. Live apply reads the fitted window and signal out of the current payload (`compute_latest_position` in `quant/strategy/live_service.py`). A different cell is a different strategy, and the next apply will trade it. `CONFIG_JSON` on the version does not change; the payload does.
- The version has fewer than 60 finite bars. Sharpe becoming null is the sample-size floor working, not a failed compounding check. Those rows belong to [Short samples](#short-samples).

Determinism of the Sharpe check rests on the per-bar pnl being the same series. Confirmed conditions:

- `CONFIG_JSON` is the whole `OptimizeRequest`, including `data_source` (decision #53), `tm_interval_id` (decision #57), and `fee_bps` when the client sent it. The worker validates that JSON and does not refill defaults over a present key.
- Closed exchange bars are immutable (decision #48). A replay that asks for a range the store no longer covers fails the job. It does not shorten the series.
- Fee default 10 bps applies only when `fee_bps` is absent. Query the gaps before trusting a Sharpe match:

```sql
-- 8. Configs a replay would fill with today's 10 bps default.
SELECT strategy_id, strategy_vid, strategy_nm, created_at
  FROM bt.strategy
 WHERE transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
   AND NOT (config_json ? 'fee_bps');
```

Provider history is the weak spot. An exchange replay reads `MARKET_DATA.PRICE_BAR`. A Yahoo or Glassnode replay reads the `BT.API_REQUEST` cache unless `refresh_dataset` is set. A cache row refreshed since the original run is a different series, and Sharpe will move. The acceptance query is the detector. This page cannot see whether any cache row was refreshed.

The audit trail is the pair of result rows plus the new promotion row. Do not delete the old `RESULT_VID`. Do not update `GATE_RESULTS` on the old promotion. The old snapshot is what the gate decided at the time.

Enabled deployments pin `STRATEGY_ID` and `STRATEGY_VID`, not "whatever is Best". Flipping `IS_BEST_IND` does not retarget them. Replacing the current payload of the pinned version does change the next signal, as above. List them before the replay and decide, per row, whether that version may receive a new payload:

```sql
-- 9. Open deployments whose pinned version still has an old current result.
SELECT d.deployment_id,
       d.deployment_vid,
       d.app_user_id,
       d.strategy_id,
       d.strategy_vid,
       d.internal_cusip,
       d.is_enabled_ind,
       d.is_paper_ind,
       d.deployment_status,
       s.strategy_nm,
       r.queue_id,
       r.created_at AS result_at,
       r.sharpe_ratio,
       r.max_drawdown
  FROM trade.deployment d
  JOIN bt.strategy s
    ON s.strategy_id = d.strategy_id
   AND s.strategy_vid = d.strategy_vid
  LEFT JOIN bt.result r
    ON r.strategy_id = d.strategy_id
   AND r.strategy_vid = d.strategy_vid
   AND r.is_current_ind = 'Y'
 WHERE d.transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
 ORDER BY d.is_enabled_ind DESC, r.created_at;
```

This proposal does not pause a deployment and does not place an order.

### Promotion and Best

The hard gates in `REFDATA.PROMOTION_METRIC` are Sharpe greater than 0, and max drawdown at most 0.40 (`max_dd_gate`, `lower_is_better`). The soft order is Sharpe, then Calmar, total return, annualised return, max drawdown. Decision #73 kept the 0.40 threshold: the old additive drawdown overstated, so the gate used to bind near a true 33% on the BTC example, and a real 40% is the limit that was intended. That "about seven points" figure is that one series. It is not a conversion to apply to every row. The new drawdown cannot be computed from the stored scalar.

What can flip, once a version is recomputed:

- **`max_dd_gate`.** The old number is larger than the compounded one on the path the archive describes (`cummax - cumsum` tracks `-ln(1 - true drawdown)`). A rejection for drawdown can become a pass. A pass becoming a fail would mean the new drawdown rose, which that relationship does not predict. List the rejections. Do not assume they all pass.
- **Sharpe gate, and the first soft metric.** Unchanged when both samples have at least 60 finite bars. If the two Sharpes differ, Calmar and the return fields never get a vote. Those decisions stand.
- **A Sharpe tie.** The next soft metric is Calmar, then the returns, then drawdown. All four changed meaning. A tie can flip `PROMOTED` to `KEPT` or the reverse.
- **VID 1.** Stays `IS_BEST_IND = 'Y'` even when the gates fail (decision #63). A recompute that worsens VID 1 does not clear Best. `LOGICAL_DELETE_IND` is the flag that takes it off the picker (decision #66).
- **A later VID that is current Best and fails a gate on the new number.** The worker demotes it, and demote-only restores VID 1.

`GATE_RESULTS` stores `{name, passed, value, threshold}`. The name written is the REFDATA `name` key. The DDL leaves `NAME` unquoted, so the snapshot key is `max_dd_gate`. Confirm on one row before trusting the filter: `SELECT gate_results FROM bt.promotion WHERE gate_results IS NOT NULL LIMIT 1`.

```sql
-- 10. Best versions whose live metrics are still pre-cutover.
--     IS_BEST_IND is standing on the old drawdown and the old CAGR.
SELECT s.strategy_id,
       s.strategy_vid,
       s.strategy_nm,
       s.logical_delete_ind,
       r.queue_id,
       r.created_at,
       r.sharpe_ratio,
       r.max_drawdown,
       r.calmar_ratio,
       r.annualized_return,
       r.total_return
  FROM bt.strategy s
  JOIN bt.result r
    ON r.strategy_id = s.strategy_id
   AND r.strategy_vid = s.strategy_vid
   AND r.is_current_ind = 'Y'
 WHERE s.is_best_ind = 'Y'
   AND s.transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
   AND r.created_at < TIMESTAMPTZ '2026-09-22 10:00:43+00'
 ORDER BY r.max_drawdown DESC NULLS LAST;
```

```sql
-- 11. Rejections where the drawdown gate failed. These are the decisions
--     most likely to reverse once the version is recomputed. The snapshot
--     value is the old drawdown. The new one is not in the database.
SELECT p.promotion_id,
       p.queue_id,
       p.strategy_id,
       p.strategy_vid,
       p.outcome,
       p.created_at,
       g->>'name' AS gate_name,
       g->>'passed' AS passed,
       g->>'value' AS snapshot_value,
       g->>'threshold' AS threshold,
       s.is_best_ind,
       s.strategy_nm
  FROM bt.promotion p
  JOIN LATERAL jsonb_array_elements(p.gate_results) g ON true
  JOIN bt.strategy s
    ON s.strategy_id = p.strategy_id
   AND s.strategy_vid = p.strategy_vid
 WHERE g->>'name' = 'max_dd_gate'
   AND g->>'passed' = 'false'
 ORDER BY p.created_at;
```

```sql
-- 12. Soft decisions that Sharpe did not decide. Candidate Sharpe equals
--     the compared VID's *current* Sharpe, so Calmar or a return field
--     cast the vote. If that compared VID was itself replayed later, the
--     current Sharpe is not the opponent the original decision saw.
--     compared_vid NULL is a baseline (VID 1, or a re-run of the best)
--     and has no opponent.
SELECT p.promotion_id,
       p.strategy_id,
       p.strategy_vid,
       p.compared_vid,
       p.outcome,
       p.created_at,
       rc.sharpe_ratio AS candidate_sharpe,
       rb.sharpe_ratio AS compared_current_sharpe,
       rc.calmar_ratio AS candidate_calmar,
       rb.calmar_ratio AS compared_current_calmar
  FROM bt.promotion p
  JOIN bt.result rc
    ON rc.queue_id = p.queue_id
  JOIN bt.result rb
    ON rb.strategy_id = p.strategy_id
   AND rb.strategy_vid = p.compared_vid
   AND rb.is_current_ind = 'Y'
 WHERE p.compared_vid IS NOT NULL
   AND rc.sharpe_ratio IS NOT NULL
   AND rb.sharpe_ratio IS NOT NULL
   AND round(rc.sharpe_ratio, 4) = round(rb.sharpe_ratio, 4)
 ORDER BY p.created_at;
```

Buy-and-hold drawdown is not a gate. The 122% figure on the BTC job does not, by itself, fail `max_dd_gate`. It does mark the row as pre-cutover, and query 3 already returns it.

### Short samples

The 2026-09-04 volume-filter job is a different defect that shares the cleanup. Decision #63 describes it: a FILTER recipe is a new `STRATEGY_ID` at VID 1, VID 1 is Best with no opponent, and Sharpe printed 5.07 on a sample of about two dozen finite bars. `Performance.MIN_METRIC_OBS = 60` shipped in `d0a28af0d`, deployed 2026-09-05 17:13 UTC. A job completed on 2026-09-04 was scored before that floor. The stored Sharpe is still 5.07 until something rewrites the result. VID 1 remains Best even if a re-run stores a null Sharpe. The Recommended banner then ranks it first, because it takes the highest finite Sharpe among Best rows that are not logically deleted (`PromotionTab.tsx`).

The floor that exists today nulls Sharpe inside a trial and maps a non-finite Sharpe to `-inf` in the objective. The job can still complete. The grid is still allowed to contain a window longer than the series. `live_lookback_bars` (`window * 3 + 60`) is the history a live signal fetches. It is not a backtest validity rule.

**Proposed rule.** Before the search starts, refuse the run when the loaded series cannot score the top of the grid. Let `W` be the maximum `window_range.max` across factors, and let `N` be the number of bars actually loaded (the series the worker is about to optimise, not the calendar span). Require:

```text
N >= W + MIN_METRIC_OBS
```

`W` bars are the rolling warmup (`_metric_window`, and `rolling(window=period)` on SMA, RSI, and Bollinger). Stochastic smooths a second rolling window of the same length, so its warmup is `2W`. The first cut can use `W + 60` for every indicator and tighten stochastic when that indicator is in the request. `MIN_METRIC_OBS` stays the constant in `Performance`. The threshold is not a new magic number, and it is not a REFDATA row: it is the same floor the Sharpe already uses.

Apply it in the worker, before `ParametersOptimization.run`, and fail the queue row with the bar count, `W`, and the interval in the error text. Failing at enqueue is worse: the API does not hold the bars. An exchange run already knows coverage; the check belongs next to the frame that will be scored.

A grid the series can only partly score should fail, not silently drop the long windows. Dropping them searches a different strategy than the one the user configured. The drawer can warn from coverage before the click. The worker is the guarantee.

Retroactive pass: find completed results whose fitted window, or whose configured grid max, does not fit the stored curve. The equity curve drops leading null `cumu` points, so its length is a lower bound on usable bars, not the raw download. `n_obs` is the real count where the payload has it (results after 2026-09-05). Older payloads need the curve length.

```sql
-- 13. Jobs whose grid or fitted window does not fit the stored curve.
--     The 2026-09-04 volume filter should appear here if its payload
--     still has the curve and a window above that length.
WITH win AS (
    SELECT r.queue_id,
           r.strategy_id,
           r.strategy_vid,
           r.created_at,
           r.is_current_ind,
           r.sharpe_ratio,
           s.strategy_nm,
           s.is_best_ind,
           s.logical_delete_ind,
           (r.payload_json #>> '{performance,strategy_metrics,n_obs}')::int AS n_obs,
           jsonb_array_length(r.payload_json #> '{performance,equity_curve}') AS curve_len,
           (r.payload_json #>> '{best,window}') AS best_window,
           (
               SELECT max((f->'window_range'->>'max')::numeric)
                 FROM jsonb_array_elements(s.config_json->'factors') f
           ) AS grid_max
      FROM bt.result r
      JOIN bt.strategy s
        ON s.strategy_id = r.strategy_id
       AND s.strategy_vid = r.strategy_vid
     WHERE r.is_current_ind = 'Y'
)
SELECT *
  FROM win
 WHERE (n_obs IS NOT NULL AND n_obs < 60)
    OR (curve_len IS NOT NULL AND grid_max IS NOT NULL AND curve_len < grid_max + 60)
    OR (best_window ~ '^[0-9]+$' AND curve_len < best_window::numeric + 60)
 ORDER BY sharpe_ratio DESC NULLS LAST;
```

A multi-factor `best.window` is a JSON array, so the numeric test on `best_window` skips it. `grid_max` still covers that row, because it reads every factor's `window_range.max`.

```sql
-- 14. The reported volume-filter job, without assuming its queue id.
--     Dated 2026-09-04 by the owner. The next UTC day is included so a
--     timestamp stored near midnight is not missed. Sharpe 5.07 is the
--     figure decision #63 records.
SELECT r.queue_id,
       r.strategy_id,
       r.strategy_vid,
       s.strategy_nm,
       s.is_best_ind,
       s.logical_delete_ind,
       r.created_at,
       r.sharpe_ratio,
       r.total_return,
       r.annualized_return,
       r.max_drawdown,
       jsonb_array_length(r.payload_json #> '{performance,equity_curve}') AS curve_len,
       r.payload_json #>> '{best,window}' AS best_window,
       s.config_json->'factors' AS factors
  FROM bt.result r
  JOIN bt.strategy s
    ON s.strategy_id = r.strategy_id
   AND s.strategy_vid = r.strategy_vid
 WHERE r.created_at >= TIMESTAMPTZ '2026-09-04 00:00:00+00'
   AND r.created_at <  TIMESTAMPTZ '2026-09-06 00:00:00+00'
   AND (
           s.strategy_nm ILIKE '%FILTER%'
        OR r.sharpe_ratio >= 4
       )
 ORDER BY r.sharpe_ratio DESC NULLS LAST;
```

The retroactive action is not a silent recompute. A re-run of this job under today's floor stores a null Sharpe and leaves VID 1 as Best, which removes it from the Recommended banner (the banner ignores null Sharpe) and leaves the Best chip on the row. That is a half fix. After query 13 and 14, the owner marks the lineages with `LOGICAL_DELETE_IND = 'Y'` through the existing Remove action. The proposal does not generate that call.

## Strategy identity

### How an id is chosen today

`BT.SP_INS_STRATEGY` (the live body is `db/liquidbase/bt/procedures/SP_INS_STRATEGY_VID_BY_NM.sql`, release `1.10.0`) resolves `STRATEGY_ID` by an exact match on `(USER_ID, STRATEGY_NM)`. A match bumps `STRATEGY_VID`. A miss inserts VID 1 and, when the caller passed no id, `gen_random_uuid()`. The unique key is `(USER_ID, STRATEGY_NM, STRATEGY_VID)`.

The name is built only in the browser, in `buildStrategyNm`:

```text
{cusip}@{dataSource}:{cadence} ← {factor}/{indicator}/{signal} on {source}:{column}
```

Multiple factors join with ` AND `, ` OR `, or ` FILTER `. The server's only check (`JobsService._assert_cadence_in_name`) is that the traded leg ends with `:{TM_INTERVAL.NAME}` for `config_json.tm_interval_id`. `EnqueueRequest` carries `strategy_nm` and `config_json`. It does not carry `strategy_id`.

What that puts in the identity string, and what it leaves on the version:

| In `STRATEGY_NM`, so a change is a new `STRATEGY_ID` at VID 1 | On `CONFIG_JSON` only, so a change is the next `STRATEGY_VID` |
|---|---|
| Traded cusip | `start`, `end` |
| Traded venue (`data_source`) | `fee_bps` |
| Bar interval name (`DAILY`, `1H`, …) | `trading_period` |
| Each factor's symbol, indicator, signal function, data column, factor source | `window_range`, `signal_range` |
| Conjunction, including `FILTER` | `walk_forward`, `split_ratio`, `refresh_dataset` |
| | The fitted window and signal, which live on the result payload |

Date range is already a version attribute. Two runs that differ only in `start` and `end`, and that build the same name, share a `STRATEGY_ID`. A re-run that started a new id changed something else in the string. The usual causes, each confirmed in history:

- Interval was added to the name on purpose (decision #58, release `1.19.0`), because hourly Sharpe is annualised with 8,760 and daily with 365, and `_evaluate_soft` compares them bare. `SP_UPD_PROMOTE_STRATEGY` keeps a single Best per `STRATEGY_ID`.
- Venue was added on purpose (decision #53). Re-running a pre-`@venue` name mints a new lineage. `1.19.0` did not rename those older rows.
- A factor list change, including adding a volume FILTER, is a new recipe (decision #63). That part should stay a new id.
- After `1.19.0` renamed stored rows, a client still sending the name without `:DAILY` forked a second lineage. The unique constraint makes renaming that fork onto the original collide at VID 1. Decision #58 records that this fork cannot be repaired by a rename.

BNB job `adb36235-e492-4f3e-aec4-59fb2bb81e9d` and lineage `5489c9bd` were not read. This shows the name and the neighbours:

```sql
-- 15. What that BNB job was stored as, and every lineage whose name
--     shares the traded leg (the text before ' ← ').
WITH job AS (
    SELECT q.queue_id, q.strategy_id, q.strategy_vid, q.user_id, q.created_at,
           s.strategy_nm, s.config_json
      FROM bt.queue q
      JOIN bt.strategy s
        ON s.strategy_id = q.strategy_id
       AND s.strategy_vid = q.strategy_vid
     WHERE q.queue_id = 'adb36235-e492-4f3e-aec4-59fb2bb81e9d'
       AND q.transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
)
SELECT j.queue_id,
       j.strategy_id,
       j.strategy_vid,
       j.strategy_nm,
       j.config_json->>'tm_interval_id' AS tm_interval_id,
       j.config_json->>'start' AS start_dt,
       j.config_json->>'end' AS end_dt,
       j.config_json->>'data_source' AS data_source,
       sib.strategy_id AS sibling_id,
       sib.strategy_vid AS sibling_vid,
       sib.strategy_nm AS sibling_nm
  FROM job j
  LEFT JOIN bt.strategy sib
    ON sib.user_id = j.user_id
   AND sib.transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
   AND split_part(sib.strategy_nm, ' ← ', 1) LIKE split_part(j.strategy_nm, '@', 1) || '@%'
 ORDER BY sib.strategy_nm, sib.strategy_vid;
```

```sql
-- 16. Lineages that differ only by the :CADENCE token.
--     Same user, same traded leg, same factor text, more than one STRATEGY_ID.
--     These are the merge candidates. FILTER vs the unfiltered parent does
--     not group, because the factor text differs. Pre-@venue names do not
--     group with @venue names, because the venue stays in the key.
WITH open_row AS (
    SELECT strategy_id,
           user_id,
           strategy_nm,
           regexp_replace(
               strategy_nm,
               '^([^@[:space:]]+@[^:[:space:]]+):[^[:space:]]+ ← ',
               '\1 ← '
           ) AS recipe
      FROM bt.strategy
     WHERE transact_to_ts = TIMESTAMPTZ '9999-12-31 00:00:00+00'
)
SELECT user_id,
       recipe,
       count(DISTINCT strategy_id) AS lineage_count,
       array_agg(DISTINCT strategy_id::text ORDER BY strategy_id::text) AS strategy_ids,
       array_agg(DISTINCT strategy_nm ORDER BY strategy_nm) AS names
  FROM open_row
 GROUP BY user_id, recipe
HAVING count(DISTINCT strategy_id) > 1
 ORDER BY lineage_count DESC, recipe;
```

```sql
-- 17. Date range already varying inside one STRATEGY_ID.
--     A row here is the current design working: same name, new VID.
--     An empty result means every stored re-run that changed dates also
--     changed the name.
SELECT strategy_id,
       user_id,
       min(strategy_nm) AS any_name,
       count(DISTINCT strategy_vid) AS vids,
       count(DISTINCT (config_json->>'start') || '→' || (config_json->>'end')) AS distinct_ranges
  FROM bt.strategy
 GROUP BY strategy_id, user_id
HAVING count(DISTINCT (config_json->>'start') || '→' || (config_json->>'end')) > 1
 ORDER BY distinct_ranges DESC;
```

### Proposed key

Keep one `STRATEGY_ID` per recipe. Take the bar interval and the date range out of the identity. Leave them on the version.

The identity, scoped to the owner, is:

- traded internal cusip
- traded venue (`data_source`)
- conjunction, null when there is one factor
- the ordered factor list: symbol or vendor symbol, indicator, signal function, data column, factor data source

The version (`STRATEGY_VID` and its `CONFIG_JSON`) holds the interval, the date range, the fee, the annualisation scalar, the grid bounds, and the walk-forward settings. The result holds the fitted window and signal.

Venue stays in the identity. Yahoo prints and Bybit prints are different series (decision #53). A factor-list change, including FILTER, stays a new identity (decision #63). Merging those would compare a gated book with an ungated one.

Build the key on the server from `config_json`, and store it on `BT.STRATEGY` as `RECIPE_KEY TEXT NOT NULL`. The lookup in `SP_INS_STRATEGY` becomes `(USER_ID, RECIPE_KEY)`. `STRATEGY_NM` stays the display string, cadence included, so a person can tell the hourly row from the daily row. The 200-character cap on `strategy_nm` then limits the label, not the lineage. The client stops being the authority for which rows are the same strategy. The cadence suffix check in `JobsService` goes away with it, replaced by the server-built key.

Doing this by only stripping `:CADENCE` out of `STRATEGY_NM` is smaller and keeps the bug the suffix check was written to close: identity remains a display string, and any formatting change forks a lineage. `RECIPE_KEY` is the proposal.

### Promotion has to move with the key

Decision #58 put cadence in the name because one Best per `STRATEGY_ID` would promote hourly over daily on the annualisation, and `schedule_policy` would then refuse to deploy the winner. Pulling cadence out of the key without changing Best recreates that. The two changes ship together.

`SP_UPD_PROMOTE_STRATEGY` today clears `IS_BEST_IND` on every VID of the id and sets one. After the change it clears and sets within the id **and** the version's `config_json.tm_interval_id`. A daily run is ranked against the current daily Best. An hourly run is ranked against the current hourly Best. VID 1 of a brand-new interval is the baseline for that interval, the way VID 1 of a new id is today.

The Recommended banner must not take `max(Sharpe)` across intervals. It shows the catalog winner of each interval, with the interval on the chip. The comparison panel offers opponents whose `tm_interval_id` matches the selected row.

`schedule_policy` already reads the pinned version's interval (decision #80). It stays correct as long as a deployment's `(STRATEGY_ID, STRATEGY_VID)` still points at the same `CONFIG_JSON`.

### Migration

This is a `bt` changeset plus a `trade` update of deployment pins, and new bodies for `SP_INS_STRATEGY` and `SP_UPD_PROMOTE_STRATEGY`. Context is `bt` and `trade` without `prod-deploy` until the owner asks. Editing the procedure file alone does not redeploy it.

Order:

1. Add nullable `RECIPE_KEY`, backfill from `CONFIG_JSON` (not from the display name, so a missing `:CADENCE` and a present one land on the same key), then set `NOT NULL`. A unique index on `(USER_ID, RECIPE_KEY, STRATEGY_VID)` waits until after the merge, because the duplicates are the point of query 16.
2. Ship the promote-by-interval procedure in the same release as the lookup change. Lookup by `RECIPE_KEY` while two lineages still share a key is ambiguous. Prefer the oldest `STRATEGY_ID` for that key only as a bridge, and merge immediately after.
3. Merge each query-16 group onto the oldest `STRATEGY_ID` that has an open deployment, otherwise the oldest id. Renumber absorbed VIDs in `CREATED_AT` order so `(STRATEGY_ID, STRATEGY_VID)` stays unique. Keep each row's historical `STRATEGY_NM`. Do not rewrite names onto one string: `UNIQUE (USER_ID, STRATEGY_NM, STRATEGY_VID)` is how the post-`1.19.0` fork became unrenameable.
4. In the same transaction, repoint `BT.QUEUE`, `BT.RESULT`, `BT.PROMOTION`, and `TRADE.DEPLOYMENT` through the vid map. `TRADE.EXECUTION_EVENT` and `TRADE.TRANSACTION` point at `DEPLOYMENT_ID`, not at the strategy, so they follow the deployment row.
5. Run query 9 first. An enabled deployment whose vid is renumbered and whose pin is not updated will apply the wrong version on the next tick. The changeset updates the pin. The owner still decides whether any enabled deployment is in a group before the changeset is marked `prod-deploy`.

Do not merge a group query 16 did not return. In particular, do not merge across venues, and do not merge a FILTER lineage onto its parent.

UI effects, once the rows share an id:

- The Promotion tab groups by `strategyGroupKey`, which is owner plus `strategy_nm`. Hourly and daily would still be two accordions if the name keeps the cadence. Group by `STRATEGY_ID` (or `RECIPE_KEY`) and show the interval as a column on each VID.
- The Trade picker lists versions. It gains the interval column and uses the catalog filter from [Visibility](#visibility). Deploy still posts a specific `strategy_id` and `strategy_vid`.
- The Jobs table already shows `strategy_nm` and the Best chip. The chip means "Best for this interval" after the promote change, and the column should say so.
- Clone stays "enqueue this config". The server assigns the id from `RECIPE_KEY`. A clone that only changes dates or interval is the next VID. A clone that changes a factor is VID 1 of a new id.

## Visibility

The owner wants versions with Sharpe below 1, or that fail the hard gates, off the main catalog, either hidden or on another tab, and a small panel of recent Sharpes that includes the failures.

### The rule

A version is in the catalog when all three hold, on its **current** result:

1. The result is not stale. Stale means `CREATED_AT` before 2026-09-22 10:00:43 UTC, or `MAX_DRAWDOWN > 1`, or `BUY_HOLD_MAX_DRAWDOWN > 1`. After the replay, a new current row leaves the stale set on its own.
2. The current shredded metrics pass the HARD rows in `REFDATA.PROMOTION_METRIC` (Sharpe greater than 0, drawdown at most 0.40), evaluated now, not from `GATE_RESULTS`. The snapshot can be the old drawdown.
3. `SHARPE_RATIO` is at least the catalog floor.

Null Sharpe fails the floor and fails the Sharpe gate. A stale 5.07 fails the stale test, so it cannot sit at the top of Recommended while the census is open.

The floor is not the promotion gate. Decision #41 set the gate at Sharpe greater than 0. Raising that gate to 1 would change who is promoted. Visibility is a separate number. The wiki home page also names a research target of Sharpe above 1.5. The floor proposed here is the owner's 1.0, stored so either number can be edited without a frontend release.

### Where the threshold lives

Add one REFDATA table, discovered automatically by `RefDataPublisher` because it lists `information_schema` for the schema:

| Column | Value |
|---|---|
| `NAME` | `default` |
| `SHARPE_MIN` | `1` |
| `RECENT_COUNT` | `8` |

`UPDATED_AT` is on the row because an operator can change the floor. Seed it in a `refdata` changeset without `prod-deploy` until the owner asks. The client reads `GET /api/v1/refdata/catalog_policy`. The React code does not contain the number 1.

`PROMOTION_METRIC` is the wrong table. A `DISPLAY` row would be ignored by `evaluate_promotion`, which only reads `HARD` and `SOFT`, but a recent-count does not fit a metric definition, and a future edit that flips the row to `HARD` would change promotion by accident.

### Where the filter runs

The Trade picker is `GET /api/v1/strategies`, which calls `SP_GET_STRATEGY_LIST` and already drops `LOGICAL_DELETE_IND = 'Y'`. That list defaults to the catalog rule. A caller with a known id can still deploy it: hiding is a list filter, not a 403. An existing deployment of a strategy that later falls under the floor stays manageable.

`GET /api/v1/backtest/promotions` stays the full log. It gains a boolean `in_catalog` computed in the service from the current result and the REFDATA floor, so the page does not reimplement the comparison. The Promotion tab renders two lists from that boolean:

- **Catalog.** The list a person picks from. Recommended is the highest Sharpe in this list, per interval once [identity](#strategy-identity) lands, and across strategies until then.
- **Below the line.** Stale, gate-failed, and under-floor versions, with the reason on the chip (`stale`, `drawdown`, `sharpe`). Best and Removed stay visible here. This is the separate tab. Hiding them with no tab drops the audit the promotion log exists to be.

`LOGICAL_DELETE_IND` stays the "do not use this recipe" action. The catalog filter does not set it.

### Recent backtests

The Jobs list (`JobRow`, `SP_GET_QUEUE`) has status, name, and the Best chip. It does not have Sharpe. The panel needs Sharpe for that queue id's own result, including when the result is stale or the gates fail.

Add `SHARPE_RATIO` from `BT.RESULT` on `QUEUE_ID` to the jobs list read. That is a new changeset pointing at `SP_GET_QUEUE`, context `bt`, because a procedure body does not redeploy itself.

The panel sits on `BacktestPage`, above the three tabs, so it is on screen during a run and on the Promotion tab. It shows the last `RECENT_COUNT` completed jobs for the signed-in user: time, strategy name, Sharpe, and the same chips as the below-the-line tab. A click uses the existing job view. The panel does not apply the catalog filter. That is the point.

Failed and cancelled jobs appear with no Sharpe, so a run that the short-sample rule refuses is visible.

### How the three pieces meet

Stale is a catalog exclusion, not a third hiding policy. A pre-cutover Best with Sharpe 5.07 or a buy-and-hold drawdown of 122% stays on the below-the-line tab and on the recent panel, and off Recommended and the Trade picker, until its current result is newer than the cutover and clears the floor. The recent panel is what still shows that 5.07, labeled stale, so the number is visible and not offered for deploy.

## Open questions

These are the choices this page does not make.

1. After queries 2, 6, and 10, the owner can see which current rows the 31-job replay left behind. The replay itself is something only the owner should start. It writes queue rows and can change the payload an enabled deployment trades.
2. Adopting `RECIPE_KEY` amends decision #58. The alternative is to leave ids split by interval and only group them in the Promotion accordion. That avoids a vid remap and does not give the owner one id.
3. The catalog floor proposed is 1.0. The home page of the wiki states a research target of 1.5. Which number goes in `SHARPE_MIN` is the owner's.
4. Query 14's volume-filter lineage, if it is still Best: Remove (`LOGICAL_DELETE_IND`) now, or leave it on the below-the-line tab until the sample rule exists.
5. Query 9's enabled deployments: which pinned versions may receive a new result payload. A replay that changes `best.window` or `best.signal` changes the next live signal.

## What shipping this would touch

Not in this change. Listed so the blast radius is visible before anyone writes a changeset.

| Piece | Schemas | Procedure bodies |
|---|---|---|
| Catalog floor | `refdata` — one new table and a seed | None. `SP_GET_ENUM` already reads any REFDATA table |
| Stale chip and `in_catalog` | None, if staleness is the cutover timestamp | `SP_GET_STRATEGY_LIST` if the filter is pushed into the procedure. It can also sit in `StrategiesService` over the columns the procedure already returns |
| Recent panel | None | `SP_GET_QUEUE`, to return `SHARPE_RATIO` |
| Short-sample refusal | None | None. Worker code, plus a test |
| Replay | None | None. `scripts/rerun_results.py` already enqueues |
| Identity | `bt` — `RECIPE_KEY`, the merge, repointing queue, result, promotion. `trade` — deployment pins | `SP_INS_STRATEGY`, `SP_UPD_PROMOTE_STRATEGY` |

The merge and the two procedure bodies are the dangerous release. They are one decision, reviewed as a diff, and they wait for `prod-deploy`. The catalog table and the replay are separable and can go first.
