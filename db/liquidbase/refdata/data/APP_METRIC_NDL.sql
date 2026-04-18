-- Nasdaq Data Link industrial & alternative metrics (APP_ID = 4)
-- See docs/design/alt-data-sources.md § "Targeted Nasdaq Data Link Datasets"
INSERT INTO REFDATA.APP_METRIC (APP_ID, METRIC_NM, DISPLAY_NAME, METRIC_PATH, DATA_CATEGORY, METHOD_NAME, DESCRIPTION, USER_ID, UPDATED_AT)
VALUES
    -- Machinery Activity (NDAQ/GIALST)
    (4, 'machine_movement',     'Machine Movement',      'NDAQ/GIALST',  'MACHINERY',     'get_table_data',  '7-day rolling sum of physical machine moves',               'alfcheun', now()),
    (4, 'equipment_runtime',    'Equipment Runtime',     'NDAQ/GIALST',  'MACHINERY',     'get_table_data',  'Cumulative hours of machine movement (7-day roll)',          'alfcheun', now()),
    (4, 'active_machine_count', 'Active Machine Count',  'NDAQ/GIALST',  'MACHINERY',     'get_table_data',  'Unique count of active machines recorded daily',             'alfcheun', now()),
    (4, 'equipment_type',       'Equipment Type',        'NDAQ/GIALST',  'MACHINERY',     'get_table_data',  'Category of machinery (e.g. Construction, Mining)',           'alfcheun', now()),

    -- Supply Chain (NDAQ/CSP)
    (4, 'accounts_receivable',  'Accounts Receivable',   'NDAQ/CSP',     'SUPPLY_CHAIN',  'get_table_data',  'Daily B2B payment behavior and credit patterns',             'alfcheun', now()),
    (4, 'revenue_dependency',   'Revenue Dependency',    'NDAQ/CSP',     'SUPPLY_CHAIN',  'get_table_data',  '% of revenue tied to specific industrial partners',          'alfcheun', now()),

    -- ESG & Risk
    (4, 'risk_incident_alerts', 'Risk Incident Alerts',  'REPRISK/TR',   'ESG_RISK',      'get_table_data',  'Daily environmental or labor strike notifications',          'alfcheun', now()),
    (4, 'carbon_estimates',     'Carbon Estimates',      'NDAQ/ESG',     'ESG_RISK',      'get_table_data',  'Daily/periodic modeled GHG emission outputs',                'alfcheun', now()),

    -- Thematic (NDAQ/GFT)
    (4, 'industrial_exposure',  'Industrial Exposure',   'NDAQ/GFT',     'THEMATIC',      'get_table_data',  'Daily score (0-1) of exposure to Metal Supply',              'alfcheun', now()),

    -- Corporate (NDAQ/NDL)
    (4, 'daily_list',           'Daily List',            'NDAQ/NDL',     'CORPORATE',     'get_table_data',  'Daily tracking of listings, delistings, and name changes',   'alfcheun', now());
