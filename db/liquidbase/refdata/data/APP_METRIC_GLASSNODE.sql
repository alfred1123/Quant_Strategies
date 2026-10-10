-- Further Glassnode series (APP_ID = 2). Close price stays in APP_METRIC.sql.
-- METRIC_PATH is the Glassnode path under /v1/metrics/. The class still
-- ignores it: Glassnode.get_historical_price always requests price_usd_close.
-- See docs/design/glassnode-market-data.md
INSERT INTO REFDATA.APP_METRIC (APP_ID, METRIC_NM, DISPLAY_NAME, METRIC_PATH, DATA_CATEGORY, METHOD_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    (2, 'sopr',                              'SOPR',                                    'indicators/sopr',                                 'ONCHAIN', 'get_historical_price', 'Spent output profit ratio',                              'alfcheun', now()),
    (2, 'mvrv',                              'MVRV',                                    'market/mvrv',                                     'ONCHAIN', 'get_historical_price', 'Market value to realized value',                         'alfcheun', now()),
    (2, 'active_count',                      'Active Address Count',                    'addresses/active_count',                          'ONCHAIN', 'get_historical_price', 'Active address count',                                   'alfcheun', now()),
    (2, 'transfers_volume_to_exchanges_sum', 'Exchange Inflow Volume',                  'transactions/transfers_volume_to_exchanges_sum',  'ONCHAIN', 'get_historical_price', 'Transfer volume to exchanges',                           'alfcheun', now()),
    (2, 'hash_rate_mean',                    'Hash Rate Mean',                          'mining/hash_rate_mean',                           'ONCHAIN', 'get_historical_price', 'Mean hash rate',                                         'alfcheun', now()),
    (2, 'transfers_volume_exchanges_net_pit','Exchange Netflow (point-in-time)',        'transactions/transfers_volume_exchanges_net_pit', 'ONCHAIN', 'get_historical_price', 'Point-in-time exchange netflow volume',                  'alfcheun', now()),
    (2, 'sopr_pit',                          'SOPR (point-in-time)',                    'indicators/sopr_pit',                             'ONCHAIN', 'get_historical_price', 'Point-in-time spent output profit ratio',                'alfcheun', now()),
    (2, 'mvrv_z_score_pit',                  'MVRV Z-Score (point-in-time)',            'market/mvrv_z_score_pit',                         'ONCHAIN', 'get_historical_price', 'Point-in-time MVRV z-score',                             'alfcheun', now()),
    (2, 'exchange_net_position_change',      'Exchange Net Position Change',            'distribution/exchange_net_position_change',       'ONCHAIN', 'get_historical_price', 'Restated exchange balance change',                       'alfcheun', now()),
    (2, 'exchange_net_position_change_pit',  'Exchange Net Position Change (point-in-time)', 'distribution/exchange_net_position_change_pit', 'ONCHAIN', 'get_historical_price', 'Point-in-time exchange balance change',             'alfcheun', now());
