-- One-off BT reset before strategy VID-by-name (release 1.10.0).
-- Pre-live only — clears duplicate (USER_ID, STRATEGY_NM, VID=1) rows.
-- Does NOT touch TRADE.* (separate rollout track).
-- See docs/design/strategy-vid-versioning.md.

TRUNCATE TABLE
    BT.PROMOTION,
    BT.RESULT,
    BT.QUEUE,
    BT.STRATEGY;
