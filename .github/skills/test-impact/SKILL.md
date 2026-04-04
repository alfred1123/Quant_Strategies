---
name: test-impact
description: 'Check which tests are impacted by recent code changes and run only those tests. Use after batch edits (sed, find-replace, refactoring) to verify nothing is broken without waiting for the full suite.'
argument-hint: 'Changed files or module name, e.g. ta.py, strat.py, perf.py'
---

# Test Impact — Run Affected Tests After Batch Changes

## When to Use
- After batch code changes using `sed`, `find`, or a bulk search-and-replace
- After refactoring a function signature shared across modules
- After renaming a class, method, or constant
- Before committing, to quickly confirm only the tests that cover the changed code

## Source → Test File Mapping

| Changed source file | Corresponding test file(s) |
|---------------------|---------------------------|
| `src/ta.py` | `tests/unit/test_ta.py` |
| `src/strat.py` | `tests/unit/test_strat.py` |
| `src/perf.py` | `tests/unit/test_perf.py` |
| `src/param_opt.py` | `tests/unit/test_param_opt.py` |
| `src/walk_forward.py` | `tests/unit/test_walk_forward.py` |
| `src/data.py` | `tests/unit/test_data.py` |
| `src/trade.py` | `tests/unit/test_trade.py` |
| `src/main.py` | `tests/unit/test_main.py` |
| `src/app.py` | `tests/unit/test_app.py` |
| `src/log_config.py` | `tests/unit/test_log_config.py` |
| Any `src/` file | `tests/integration/test_backtest_pipeline.py` (always run) |

## Procedure

### 1. Identify changed files

```bash
# Files changed since the last commit
git diff --name-only HEAD

# Files changed in the working tree (unstaged + staged)
git diff --name-only && git diff --cached --name-only

# Files changed in a specific commit
git diff --name-only <commit-sha>~1 <commit-sha>
```

### 2. Map to test files

Run only the tests that cover the changed modules:

```bash
# Single module changed
python -m pytest tests/unit/test_ta.py -v

# Multiple modules changed
python -m pytest tests/unit/test_ta.py tests/unit/test_strat.py -v

# Always include integration tests when any src/ file changes
python -m pytest tests/unit/test_ta.py tests/integration/test_backtest_pipeline.py -v
```

### 3. Filter tests by keyword

If only a specific function or class changed, filter by keyword to run only relevant tests:

```bash
# Run all tests mentioning "bollinger"
python -m pytest tests/ -v -k "bollinger"

# Run all tests mentioning "momentum" or "reversion"
python -m pytest tests/ -v -k "momentum or reversion"

# Run all tests in a class
python -m pytest tests/unit/test_ta.py::TestBollingerBand -v
```

### 4. Batch change verification workflow

Use this workflow whenever applying a batch change (e.g., `sed` rename):

```bash
# Step 1: Confirm the change looks correct
git diff --stat

# Step 2: Identify affected test files
git diff --name-only HEAD | sed 's|src/\(.*\)\.py|tests/unit/test_\1.py|'

# Step 3: Run targeted tests
python -m pytest <affected-test-files> tests/integration/test_backtest_pipeline.py -v

# Step 4: If all pass, run the full suite for final verification
python -m pytest tests/ -v
```

**Example — renaming a method with `sed`:**

```bash
# Rename get_bollinger_band → get_zscore_band across all source files
find src/ -name "*.py" -exec sed -i 's/get_bollinger_band/get_zscore_band/g' {} +

# Verify only ta.py and its tests are affected
git diff --name-only
# → src/ta.py, src/app.py, src/main.py, ...

# Run impacted tests immediately
python -m pytest tests/unit/test_ta.py tests/unit/test_main.py \
    tests/integration/test_backtest_pipeline.py -v
```

### 5. Common batch-change scenarios

#### Rename a Strategy method

```bash
find src/ -name "*.py" -exec sed -i 's/momentum_const_signal/<new_name>/g' {} +
python -m pytest tests/unit/test_strat.py tests/unit/test_perf.py \
    tests/unit/test_param_opt.py tests/unit/test_walk_forward.py \
    tests/integration/test_backtest_pipeline.py -v
```

#### Update constructor signature (e.g., new parameter)

```bash
# After changing Performance.__init__ signature
python -m pytest tests/unit/test_perf.py \
    tests/integration/test_backtest_pipeline.py -v
```

#### Change a constant or default value

```bash
# After changing default fee_bps or trading_period
python -m pytest tests/unit/test_perf.py tests/unit/test_param_opt.py \
    tests/unit/test_walk_forward.py \
    tests/integration/test_backtest_pipeline.py -v
```

#### Update import paths or module structure

```bash
# After restructuring src/ imports
python -m pytest tests/ -v
```

### 6. Quick one-liner: auto-detect and run impacted tests

```bash
# Collect all changed src/ files and derive test paths, then run
CHANGED=$(git diff --name-only HEAD | grep '^src/' | sed 's|src/\(.*\)\.py|tests/unit/test_\1.py|' | xargs)
[ -n "$CHANGED" ] && python -m pytest $CHANGED tests/integration/test_backtest_pipeline.py -v \
    || echo "No src/ files changed"
```

### 7. Full suite (final gate before pushing)

After all targeted tests pass, run the full suite to catch any cross-module regressions:

```bash
python -m pytest tests/ -v
```

## Tips

- **NaN propagation failures** after a batch rename usually mean a test fixture or mock uses
  the old function name — update the test mock target.
- **Import errors** after a rename mean not all call sites were updated — run
  `grep -r "old_name" src/ tests/` to find remaining references.
- **Integration test failures only** (unit tests pass) usually mean a data-flow contract
  changed — review how modules are chained in `perf.py` or `main.py`.

## Checklist
- [ ] Changed files identified with `git diff --name-only HEAD`
- [ ] Targeted tests run and pass
- [ ] Integration tests run and pass
- [ ] Full suite (`python -m pytest tests/ -v`) run as final gate
- [ ] No regressions introduced
