# Adding Indicators

To add a new technical indicator to the backtest pipeline, follow this pattern.

## Steps

1. **Add the method** to `TechnicalAnalysis` in `src/strat.py`:

    ```python
    def get_my_indicator(self, period: int) -> pd.Series:
        """Compute my indicator on self.data['factor']."""
        factor = self.data["factor"]
        # ... compute indicator ...
        self.data["indicator"] = result
        return result
    ```

2. **Add signal mapping** — if the indicator is bounded (0–100 like RSI), set `IS_BOUNDED_IND = 'Y'` in REFDATA. The backend auto-selects bounded vs band signal functions.

3. **Seed REFDATA** — create a Liquibase changeset to insert into `REFDATA.INDICATOR`:

    ```sql
    INSERT INTO REFDATA.INDICATOR (
        METHOD_NAME, DISPLAY_NAME, IS_BOUNDED_IND,
        WIN_MIN, WIN_MAX, WIN_STEP, SIG_MIN, SIG_MAX, SIG_STEP,
        USER_ID, UPDATED_AT
    ) VALUES (
        'get_my_indicator', 'My Indicator', 'N',
        5, 100, 5, 0.25, 2.50, 0.25,
        'alfcheun', now()
    );
    ```

4. **Write tests** in `tests/unit/test_strat.py` — verify output shape, edge cases, NaN handling.

5. **Run all tests**: `python -m pytest tests/ -v`

!!! note
    See the `add-indicator` skill at `.github/skills/add-indicator/SKILL.md` for the full checklist.
