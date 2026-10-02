# Queue screen aids — search and compare

**Status:** proposed (not yet implemented)
**Date:** 2026-09-29
**Related:** [Jobs table detail UX](jobs-table-detail-ux.md), [Best-VID promotion](best-vid-promotion.md), [Backtest queue](backtest-queue.md)

Two frontend changes that make a finished backtest easier to find and compare. Neither adds a table, a column, or a stored procedure. Each one uses data the API already returns.

## Change impact

| Layer | Change required? | Reason |
|-------|------------------|--------|
| Database | No | `config_json` and the result payload are already stored. |
| Backend API | No | `GET /api/v1/backtest/jobs/{id}` already returns `config_json` and `result`. The jobs list already includes `strategy_nm`. |
| Frontend | Yes | A search box and a compare dialog. |

## Before and after

| | Before | After |
|---|--------|--------|
| Find a run | Scroll the Queue and use status chips | Type part of the strategy name and the table filters |
| See what changed between two runs | Open Clone twice, or read two JSON blobs separately | Pick two finished jobs and see settings and scores side by side |

## 1. Search the Queue by strategy name

The jobs list is already in memory and already shows **Strategy**. Add a text field above the status chips. Typing filters rows whose `strategy_nm` contains that text. Status chips still apply on top of the search. Clearing the box shows the full filtered list again.

No new request. The table keeps auto-refresh.

## 2. Compare two finished jobs

A control on the Queue, available for **COMPLETED** jobs, lets the user pick two rows. The dialog fetches each job with the existing single-job call and shows:

- symbol, date range, and factors for each side
- Sharpe, Calmar, total return, and max drawdown for each side
- raw JSON for each side, collapsed

The dialog is read-only. It does not enqueue, clone, or promote.

## Suggested order

| Step | What ships | Why this order |
|------|------------|----------------|
| 1 | Strategy-name search | Uses the list that is already on screen. Simplest change. |
| 2 | Two-job compare | Builds on the search to find the jobs you want to compare. |

## Acceptance

- [ ] Typing in the Queue search box hides jobs whose strategy name does not match
- [ ] Status chips still filter the rows that search leaves visible
- [ ] Two completed jobs can be compared without writing to the queue
- [ ] No database migration and no new API route
