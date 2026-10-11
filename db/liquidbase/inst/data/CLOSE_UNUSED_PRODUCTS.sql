-- Close current products that are not the pairs this platform trades.
--
-- Kept: btcusdt.crypto, ethusdt.crypto, bnbusdt.crypto.
-- A current row is also kept when a deployment, a captured bar, a bar
-- subscription, an active group membership, or a current strategy names it.
-- History stays. SP_UPD_PRODUCT_IS_CURRENT sets IS_CURRENT_IND to N and
-- closes the open xrefs. Idempotent: a second run finds nothing current to close.
DO $$
DECLARE
    R          RECORD;
    V_SQLSTATE TEXT;
    V_SQLMSG   TEXT;
    V_SQLERRMC TEXT;
BEGIN
    FOR R IN
        SELECT p.INTERNAL_CUSIP
          FROM INST.PRODUCT p
         WHERE p.IS_CURRENT_IND = 'Y'
           AND p.INTERNAL_CUSIP NOT IN (
                'btcusdt.crypto',
                'ethusdt.crypto',
                'bnbusdt.crypto'
           )
           AND NOT EXISTS (
                SELECT 1
                  FROM TRADE.DEPLOYMENT d
                 WHERE d.INTERNAL_CUSIP = p.INTERNAL_CUSIP
                   AND d.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
           )
           AND NOT EXISTS (
                SELECT 1
                  FROM MARKET_DATA.PRICE_BAR b
                 WHERE b.INTERNAL_CUSIP = p.INTERNAL_CUSIP
           )
           AND NOT EXISTS (
                SELECT 1
                  FROM MARKET_DATA.BAR_SUBSCRIPTION s
                 WHERE s.INTERNAL_CUSIP = p.INTERNAL_CUSIP
                   AND s.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
           )
           AND NOT EXISTS (
                SELECT 1
                  FROM INST.PRODUCT_GRP_MEMBER m
                 WHERE m.PRODUCT_ID = p.PRODUCT_ID
                   AND m.IS_ACTIVE_IND IS DISTINCT FROM 'N'
           )
           AND NOT EXISTS (
                SELECT 1
                  FROM BT.STRATEGY st
                 WHERE st.TRANSACT_TO_TS = TIMESTAMPTZ '9999-12-31 00:00:00+00'
                   AND st.CONFIG_JSON::text LIKE '%' || p.INTERNAL_CUSIP || '%'
           )
    LOOP
        CALL INST.SP_UPD_PRODUCT_IS_CURRENT(
            R.INTERNAL_CUSIP,
            'liquibase',
            V_SQLSTATE,
            V_SQLMSG,
            V_SQLERRMC
        );
        IF V_SQLSTATE <> '00000' THEN
            RAISE EXCEPTION 'SP_UPD_PRODUCT_IS_CURRENT failed for %: % (%)',
                R.INTERNAL_CUSIP, V_SQLERRMC, V_SQLSTATE;
        END IF;
        RAISE NOTICE 'closed %', R.INTERNAL_CUSIP;
    END LOOP;
END $$;
