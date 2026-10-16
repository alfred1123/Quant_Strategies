# Risk control

**Doc type:** strategy research  
**Status:** the application owns the rule. This page describes what a run reads and records. It does not give anyone a limit to apply by hand.

The three sleeves are one book. The application stores the risk rule for that book in `quant/strategy/risk_rule.py`. That module is the only copy. A run reads it, and the result records what was read. How the research bots divide the work is in the [research workflow](workflow.md#risk-control-risk-guardian).

## What a run reads

`run_optimize` reads the rule before the search. The same function serves the queue worker and `POST /api/v1/backtest/optimize`, so both paths read the same rule.

The rule names each sleeve and the blend weight stored for it. The sleeve text is the identity of the golden sleeves already chosen. The application does not retune those sleeves. Alfred chose the weighting the module holds. A drawdown ladder and a kill switch are not in the rule. They are unsigned, so the module does not carry them as a default and this page does not publish them as limits.

## What the result records

A finished run stores the rule on `OptimizeResponse.risk_rule`. The queue worker writes that payload to `BT.RESULT`. The record has:

| Field | What it means |
|---|---|
| `rule_id`, `blend_name` | Which rule the run read |
| `sleeves` | Each sleeve's key, name, definition, and the weight the application holds |
| `applied` | Whether this run sized or combined the sleeves with that rule |
| `engine_can_apply` | Whether the engine can size or combine sleeves at all |
| `metrics_are` | What the performance block is |
| `limits` | Drawdown ladder and kill switch, when a signed rule contains them |

Today `applied` is false, `engine_can_apply` is false, `metrics_are` is `unit_position`, and `limits` is empty. Positions are still −1, 0, or 1. The performance block is the unit-position search. It is the sleeve that was run, with the rule attached as a record of what was read.

The schema refuses a record that says the rule was applied, or that the metrics are a sized blend. That claim can appear only in a later change that actually sizes the book.

## When the engine can apply the rule

Sizing and combining sleeves is the [fractional sizing and stateful exits](../design/2026-09-26-fractional-sizing-stateful-exits.md) proposal ([PR #63](https://github.com/alfred1123/Quant_Strategies/pull/63)). It is not in the engine. Until it is, a run still reads the rule and still records it, and the result stays a unit-position search with `applied` false.

When that engine path exists, the same read happens. A result that used the rule records `applied` true, and its performance block is the sized book. A result that did not use the rule keeps `applied` false and stays `unit_position`. An empty `limits` field stays empty until a signed rule puts a ladder or a kill switch there. A placeholder number is not that rule.

## A missing rule

If the rule cannot be read, `run_optimize` raises and returns no response. The worker marks the queue row failed and does not call `BT.SP_INS_RESULT`. There is no stored payload whose Sharpe could be taken for a sized or blended book that simply omitted its rule.
