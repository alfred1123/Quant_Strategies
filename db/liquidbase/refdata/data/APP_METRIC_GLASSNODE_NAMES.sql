-- METRIC_NM is snake_case of DISPLAY_NAME, not the vendor path.
-- A parenthetical qualifier is a suffix: "(point-in-time)" is `_pit`.
-- METRIC_PATH stays the vendor locator. DATA_CATEGORY is the subject
-- (PRICE, VALUATION, NETWORK, FLOW), so another provider can reuse it.
-- Release 1.28.0 inserted the vendor-path tails. This renames those three
-- and sets the subject on every Glassnode series except close price.
UPDATE REFDATA.APP_METRIC
   SET METRIC_NM = 'active_address_count', DATA_CATEGORY = 'NETWORK', UPDATED_AT = now()
 WHERE APP_ID = 2 AND METRIC_NM = 'active_count';

UPDATE REFDATA.APP_METRIC
   SET METRIC_NM = 'exchange_inflow_volume', DATA_CATEGORY = 'FLOW', UPDATED_AT = now()
 WHERE APP_ID = 2 AND METRIC_NM = 'transfers_volume_to_exchanges_sum';

UPDATE REFDATA.APP_METRIC
   SET METRIC_NM = 'exchange_netflow_pit', DATA_CATEGORY = 'FLOW', UPDATED_AT = now()
 WHERE APP_ID = 2 AND METRIC_NM = 'transfers_volume_exchanges_net_pit';

UPDATE REFDATA.APP_METRIC
   SET DATA_CATEGORY = 'VALUATION', UPDATED_AT = now()
 WHERE APP_ID = 2 AND METRIC_NM IN ('sopr', 'mvrv', 'sopr_pit', 'mvrv_z_score_pit');

UPDATE REFDATA.APP_METRIC
   SET DATA_CATEGORY = 'NETWORK', UPDATED_AT = now()
 WHERE APP_ID = 2 AND METRIC_NM = 'hash_rate_mean';

UPDATE REFDATA.APP_METRIC
   SET DATA_CATEGORY = 'FLOW', UPDATED_AT = now()
 WHERE APP_ID = 2 AND METRIC_NM IN ('exchange_net_position_change', 'exchange_net_position_change_pit');
