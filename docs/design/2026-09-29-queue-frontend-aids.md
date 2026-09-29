# Queue screen aids — result, labels, search, compare

**Status:** proposed (not yet implemented)
**Date:** 2026-09-29
**Related:** [Jobs table detail UX](jobs-table-detail-ux.md), [Best-VID promotion](best-vid-promotion.md), [Backtest queue](backtest-queue.md)

Four frontend changes that make a finished backtest easier to judge. None of them add a table, a column, or a stored procedure. Each one displays data the API already returns.

The read-only **Config** dialog on the Queue tab (pull request #83) is the place for the result section and the side-by-side compare. Search and the plain-language labels sit on the Queue table and the Promotion tab.

## Change impact

| Layer | Change required? | Reason |
|-------|------------------|--------|
| Database | No | `config_json` and the result payload are already stored. Promotion outcome and gate results are already stored. |
| Backend API | No | `GET /api/v1/backtest/jobs/{id}` already returns `config_json` and `result`. The jobs list already includes `strategy_nm`. Promotion rows already include `outcome` and `gate_results`. |
| Frontend | Yes | New sections, a search box, and short explanations on labels that already exist. |

## Before and after

| | Before | After |
|---|--------|--------|
| See how a run did | Open **View** for charts, or open Promotion and hunt for the version | **Config** shows Sharpe, Calmar, return, and max drawdown next to the settings |
| Sharpe, Calmar, Kept, Promoted | The words appear with no explanation | Each label has a one-line tooltip |
| Find a run | Scroll the Queue and use status chips | Type part of the strategy name and the table filters |
| See what changed between two runs | Open Clone twice, or read two JSON blobs separately | Pick two finished jobs and see settings and scores side by side |

## 1. Result next to the config

**Config** today shows general settings, factors, and raw JSON. The same job response already carries `result`. Add a **Result** block in that dialog for a completed job:

| Field | Where it already lives |
|-------|------------------------|
| Sharpe Ratio | `result` performance metrics |
| Calmar Ratio | same |
| Total return | same |
| Max drawdown | same |

Failed and cancelled jobs keep the config block. The result block stays empty when `result` is missing, with the error text the table already shows.

This is the useful slice of the older [jobs-table detail drawer](jobs-table-detail-ux.md). It does not replace that proposal. Hover preview, a full drawer, and putting `config_json` on every list row are still separate work.

## 2. Plain-language labels

Sharpe, Calmar, Kept, and Promoted are the words a user has to learn before the Promotion tab is usable. Add a tooltip (or a one-line caption) on each, using the meanings already written in [Best-VID promotion](best-vid-promotion.md):

| Label | Caption |
|-------|---------|
| Sharpe | Profit relative to how much the result jumped around. Higher is smoother. A new version must clear Sharpe above 1, and beat buy-and-hold. |
| Calmar | Yearly profit divided by the worst drop. Used when Sharpe does not decide the comparison. |
| Promoted | Passed the gates and beat the current Best. This version becomes Best. |
| Kept | The current Best stays. This version lost, tied, or already is Best and still passes. |

Rejected and Demoted get the same treatment so the four outcomes stay consistent: Rejected failed a gate; Demoted was Best and no longer passes.

The gate list and the “decisive” chip stay as they are. This change only explains the words.

## 3. Search the Queue by strategy name

The jobs list is already in memory and already shows **Strategy**. Add a text field above the status chips. Typing filters rows whose `strategy_nm` contains that text. Status chips still apply on top of the search. Clearing the box shows the full filtered list again.

No new request. The table keeps auto-refresh.

## 4. Compare two finished jobs

A control on the Queue, available for **COMPLETED** jobs, lets the user pick two rows. The dialog fetches each job with the existing single-job call and shows:

- symbol, date range, and factors for each side
- Sharpe, Calmar, total return, and max drawdown for each side
- raw JSON for each side, collapsed

The dialog is read-only. It does not enqueue, clone, or promote.

## Suggested order

| Step | What ships | Why this order |
|------|------------|----------------|
| 1 | Result block inside Config | Same dialog as the viewer. One job, one click. |
| 2 | Label tooltips | Smallest change. Unblocks the Promotion tab. |
| 3 | Strategy-name search | Uses the list that is already on screen. |
| 4 | Two-job compare | Needs the result fields from step 1 so both sides show scores, not only JSON. |

## Acceptance

- [ ] Config on a completed job shows Sharpe, Calmar, total return, and max drawdown
- [ ] Config on a failed job still shows settings, and does not invent a result
- [ ] Sharpe, Calmar, Kept, Promoted, Rejected, and Demoted each show a one-line explanation
- [ ] Typing in the Queue search box hides jobs whose strategy name does not match
- [ ] Status chips still filter the rows that search leaves visible
- [ ] Two completed jobs can be compared without writing to the queue
- [ ] No database migration and no new API route
