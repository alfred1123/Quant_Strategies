# Adding Strategies

To add a new trading strategy (signal direction) to the backtest pipeline.

## Steps

1. **Add the method** to `SignalDirection` in `src/strat.py`:

    ```python
    @staticmethod
    def my_custom_signal(indicator: np.ndarray, signal: float) -> np.ndarray:
        """Custom signal logic. Returns array of {-1, 0, 1}."""
        position = np.zeros_like(indicator)
        position[indicator > signal] = 1
        position[indicator < -signal] = -1
        return position
    ```

2. **Seed REFDATA** — create a Liquibase changeset to insert into `REFDATA.SIGNAL_TYPE`:

    ```sql
    INSERT INTO REFDATA.SIGNAL_TYPE (
        NAME, DISPLAY_NAME, FUNC_NAME_BAND, FUNC_NAME_BOUNDED,
        USER_ID, UPDATED_AT
    ) VALUES (
        'my_custom', 'My Custom Strategy',
        'my_custom_signal', 'my_custom_bounded_signal',
        'alfcheun', now()
    );
    ```

3. **Write tests** in `tests/unit/test_strat.py` — verify long/short/flat positions for known inputs.

4. **Run all tests**: `python -m pytest tests/ -v`

!!! note
    See the `add-strategy` skill at `.github/skills/add-strategy/SKILL.md` for the full checklist.
