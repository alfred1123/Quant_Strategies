# Adding Strategies

To add a new trading strategy (signal direction) to the backtest pipeline.

## Steps

1. **Add the method** to `SignalDirection` in `quant/strategy/signals.py`:

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

## Long-only (no short)

For spot accounts or jurisdictions that cannot short, pick **Momentum (long only)** or **Reversion (long only)** in the backtest Strategy dropdown (`REFDATA.SIGNAL_TYPE` names `momentum_long` / `reversion_long`). These map to `*_long_only` functions in `quant/strategy/signals.py`, which clip `-1` legs to flat. The same config flows to live apply — a fitted long-only strategy never signals `OPEN_SHORT`.

Release `1.24.0-signal-type-long-only` seeds the REFDATA rows.

**Production:** a new signal needs **migrate + `quant-app` deploy + Redis refresh**
— not any single step alone. See **[Production Rollout](prod-rollout.md)** for the
full layer checklist, partial-deploy pitfalls, SSO, and verification commands.

!!! note
    See the `add-strategy` skill at `.github/skills/add-strategy/SKILL.md` for the full checklist.
