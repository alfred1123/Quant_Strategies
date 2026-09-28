<!--
Standards: docs/design/coding-standards.md
https://alfred1123.github.io/Quant_Strategies/design/coding-standards/
Fill in every section. Write "n/a" with a reason rather than deleting one.
A code PR without the testing evidence below is blocked.
-->

## What

<!-- What changed, in one or two sentences. -->

## Why

<!-- The problem or bug this solves. Link the issue, bug id, or design doc. -->

## Hard rules

Confirm each rule and add a one-line note (for example, which class owns the change).

- [ ] **1. OOP ownership.** The change is in the class or module that owns the behaviour. No caller patches, no new cross-module coupling or import cycles, no duplicated logic, no lower layer importing an upper one.
  Note:
- [ ] **2. No backward compatibility.** Changed interfaces are replaced and every caller is updated in this PR. No shims, aliases, deprecated parameters, fallbacks, or legacy branches.
  Note:
- [ ] **3. No hard-coded values.** Business values, status ids, limits, fees, and thresholds come from REFDATA/CONFIG tables (or env only for deployment settings, secrets, or process tuning). No new magic numbers or strings.
  Note:
- [ ] **4. Thorough testing.** The evidence below is filled in.
  Note:
- [ ] **5. How did this happen?** The section below names where the wrong behaviour starts. If this PR removes or hides bad output, it explains why that output cannot be stopped at the source.
  Note:
- [ ] **5. Long-term fix.** The change fixes the root cause in the owning class. The long-term check below is filled in.
  Note:

## How did this happen? (root cause)

- Where the wrong behaviour starts: <!-- The point that produces it, not where it shows up. -->
- If this PR removes or hides bad output (dropping duplicate rows after the fact, filtering bad values, or catching and ignoring an error), why that output cannot be stopped at its source: <!-- If it cannot, this is a design item under docs/design/, not a quick fix. -->

## Long-term check

- Root cause or symptom? <!-- Say which, and name the root cause. If this only treats a symptom, it should be a design item under docs/design/ instead. -->
- What would break this within a month? Answer each:
  - A new strategy type:
  - A new coin or instrument:
  - Hourly (or other non-daily) bars:
  - A database schema change:
  - A new broker:

## Testing evidence

### Fails on main, passes here

- [ ] Added or updated a test that fails on `main` and passes on this branch.

Test name(s):

```text
Paste the failure from main here (assertion or traceback).
```

### Edge cases covered

- [ ] Empty and `None` inputs
- [ ] Boundaries (zero, one, the limit, one past it)
- [ ] Interacting or racing paths (retries, concurrent workers, cancel during run)

Notes:

### Full suite

- [ ] `python -m pytest tests/ -v` passes locally.
- [ ] CI is green.

```text
Paste the pytest summary line here.
```

### ruff and mypy (CI does not run these)

- [ ] `python -m ruff check quant tests scripts`: no new findings.
- [ ] `python -m mypy quant --ignore-missing-imports`: no new errors.

```text
Paste the counts before and after, or the output for the files you touched.
```

### Backtest comparison

- [ ] This change cannot alter backtest results (say why), **or**
- [ ] Before-and-after comparison on a real backtest is below (same instrument, interval, date range, and parameters).

| Metric | main | this branch |
|---|---|---|
| | | |

## Risk and rollback

<!-- What could go wrong, and who or what it affects. Does this touch quant/trade/ (live trading)? If so, which failure paths are tested? How to roll back (revert, changeset rollback, refdata refresh). -->

## Docs

- [ ] Docs updated in this PR (`docs/`, `README.md`, `docs/decisions.md`), or no behaviour change needs them.
- [ ] New docs pages are in `mkdocs.yml` `nav:` and `mkdocs build --strict` passes.

---

I have read [docs/design/coding-standards.md](https://github.com/alfred1123/Quant_Strategies/blob/main/docs/design/coding-standards.md). Alfred merges all code PRs.
