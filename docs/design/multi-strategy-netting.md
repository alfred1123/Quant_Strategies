# Multi-strategy netting — why the execution tables are keyed wrong

**Status: recorded, not built.** No DDL or Python is committed for this. It
documents a modelling error that today's schema does not yet expose, so that the
eventual fix is a decision rather than a discovery.

---

## 1. The intent

Several strategies trade one asset on one account. Rather than each placing its
own order — paying fees twice and potentially trading against itself — the
platform **sums the quantity each strategy wants per asset, compares that to the
account's actual position, and places one net order for the difference.**

Two things follow: fees are minimised, because offsetting intentions cancel
before reaching the exchange instead of after; and strategies can no longer
fight, because there is only ever one order per asset per tick.

## 2. Why `DEPLOYMENT_ID` breaks

`TRADE.EXECUTION_EVENT` and `TRADE.TRANSACTION` both carry
`DEPLOYMENT_ID UUID NOT NULL`. That column asserts **this execution was caused by
this one deployment**, which is true today only because each deployment applies
independently.

Netting makes it false. One net order is caused by *N* deployments, and neither
way of recording it is honest:

| If you write | Then |
|---|---|
| One row, on one `DEPLOYMENT_ID` | That deployment is blamed for an order it partly caused; the others have no record |
| One row per contributing deployment | One exchange order appears *N* times — its fills and fees double-count |

`DEPLOYMENT_VID` is the second clue. It exists to pin *which config version*
produced a decision. That is a property of the decision, not of the order: an
order sent to Bybit has no version.

## 3. Where `POSITION_QTY` really belongs

`TRADE.EXECUTION_EVENT.POSITION_QTY` (added in `1.7.0`) is the **account-level**
position for the symbol — `fetch_positions([symbol])` on the credential. Bybit in
one-way mode keeps one net position per symbol per account and has no notion of a
strategy's share of it.

So it describes the *(credential, symbol)* pair, not the deployment. It was
attached to the deployment row because no table represents that pair. This is
the same error as §2 seen from the other side, and both resolve together.

!!! note "Not a problem in production today"
    With one enabled deployment per symbol the account position *is* that
    deployment's position, and `DEPLOYMENT_ID` *is* the sole cause of the order.
    Every column is currently accurate. The error is latent, and netting is what
    would activate it.

## 4. The shape that resolves it

Three entities are presently squeezed into two tables:

```text
DEPLOYMENT ─────────── config, per strategy
     │
     ▼
APPLY_INTENT ───────── per (deployment, tick)
     │                 signal, target qty, bar_source, DEPLOYMENT_VID
     │  many-to-one
     ▼
ORDER_ATTEMPT ──────── per (credential, symbol, tick)
     │                 POSITION_QTY before, net delta, side,
     │                 vendor_order_id, success, attempt
     ▼
TRANSACTION ────────── fills, per vendor_order_id
```

The link is a **nullable** `ORDER_ATTEMPT_ID` on the intent. Nullable matters:
an intent that nets to zero produces no order at all, and that non-event is
worth recording — it is today's `HOLD`.

Read against this, the current `EXECUTION_EVENT` is `APPLY_INTENT` and
`ORDER_ATTEMPT` merged, which is exactly why two of its columns feel wrong.

## 5. Why this is deferred

[Decision #38](../decisions.md) rejected a `TRADE.INTENT` table because per-tick
signal state is computed in the worker and survives milliseconds, and it named
its own revisit condition: *"only if limit orders or a live-signal UI need state
between bar closes."* Netting is a third trigger that decision did not
anticipate. It is not wrong — it was never asked this question.

Building the split before the netting engine exists means guessing at that
engine's requirements. These are open, and each one changes the schema:

| Open question | Why it decides the schema |
|---|---|
| Does netting scope to a credential, or to a user across credentials? | Determines the natural key of `ORDER_ATTEMPT` |
| Does an intent carry a **target position** or a **delta**? | Targets are idempotent and survive a missed tick; deltas are not |
| How is a **partially filled** net order attributed back to contributors? | Decides whether attribution is stored or derived, and whether it can be exact at all |
| Do intents on different intervals (1H and daily) net together within a tick? | Decides whether `ORDER_ATTEMPT` is per interval or per sweep |
| Does one strategy's failure block the whole net order? | Decides transactional boundaries across contributors |

Guessing wrong costs more than waiting, because by then there are live rows to
migrate.

## 6. What today's schema does not foreclose

`POSITION_QTY` is nullable and additive. When `ORDER_ATTEMPT` arrives the column
moves there, `DEPLOYMENT_ID` relaxes to nullable on the execution side, and rows
written in the meantime stay readable as history — they describe a period when
one deployment did cause one order.

A cheaper forward step exists if this is wanted before netting: record
`API_CREDENTIAL_ID` and `INTERNAL_CUSIP` on `EXECUTION_EVENT` directly, rather
than leaving them derivable through the deployment. That is what lets a netted
execution exist later without back-filling the pair onto old rows. It was
considered and **not** taken, on the grounds that two columns serving no current
reader is the speculative generality this document is arguing against.

## 7. Related

- [Two deployments, same asset §7](scheduler-trade-open-questions.md#7-two-deployments-same-asset-how-to-detect-position) — the same conflict, and why the one-slot guard recommended there is **superseded** by netting
- [Recording the position an apply saw](../architecture/database.md#recording-the-position-an-apply-saw) — what `POSITION_QTY` is and why `0` differs from `NULL`
- [Live order execution](live-order-execution.md) — the single-deployment order path as it stands
