-- Align crypto spot products with the pair they actually trade.
--
-- EXCHANGE names the listing/clearing venue, which only exists for equities
-- (decision #21). A crypto spot pair is quoted on every venue that lists it, so
-- 'crypto' in that column is a category label standing in for a venue that has
-- no meaning here — the venue lives in INST.PRODUCT_XREF, one row per APP_ID.
--
-- CCY matters more than it looks: LiveApplyOrchestrator._settlement_ccy reads it
-- straight into TRADE.TRANSACTION.TRANS_CCY_CD, so 'USD' on a pair that settles
-- in USDT mis-stamps the currency on every recorded fill. Note the column being
-- empty would have been safer than being wrong — the code falls back to 'USDT'.
-- Taken from the cusip, which already names the quote leg.
--
-- The description on product 43 likewise still read "BTC-USD spot crypto pair"
-- from before the rename to btcusdt.crypto, naming a market that is not executed.
--
-- INST.PRODUCT is soft-versioned: SP_INS_PRODUCT flips the current row to 'N' and
-- inserts a new VID. Idempotent — a row already corrected matches no WHERE clause
-- and so is never re-versioned.
DO $$
DECLARE
    R           RECORD;
    V_SQLSTATE  TEXT;
    V_SQLMSG    TEXT;
    V_SQLERRMC  TEXT;
BEGIN
    FOR R IN
        SELECT PRODUCT_ID,
               INTERNAL_CUSIP,
               DISPLAY_NM,
               ASSET_TYPE_ID,
               CASE WHEN INTERNAL_CUSIP LIKE '%usdt.crypto' THEN 'USDT' ELSE CCY END AS CCY,
               REPLACE(DESCRIPTION, 'BTC-USD', 'BTC/USDT') AS DESCRIPTION
          FROM INST.PRODUCT
         WHERE IS_CURRENT_IND = 'Y'
           AND INTERNAL_CUSIP LIKE '%.crypto'
           AND (EXCHANGE IS NOT NULL
                OR DESCRIPTION LIKE '%BTC-USD%'
                OR (INTERNAL_CUSIP LIKE '%usdt.crypto' AND CCY IS DISTINCT FROM 'USDT'))
    LOOP
        CALL INST.SP_INS_PRODUCT(
            R.PRODUCT_ID,
            R.INTERNAL_CUSIP,
            R.DISPLAY_NM,
            R.ASSET_TYPE_ID,
            NULL,             -- EXCHANGE
            R.CCY,
            R.DESCRIPTION,
            'system',
            V_SQLSTATE, V_SQLMSG, V_SQLERRMC
        );

        IF V_SQLSTATE <> '00000' THEN
            RAISE EXCEPTION 'SP_INS_PRODUCT failed for %: % (%)',
                R.INTERNAL_CUSIP, V_SQLERRMC, V_SQLSTATE;
        END IF;

        RAISE NOTICE 'corrected % — EXCHANGE=NULL, CCY=%', R.INTERNAL_CUSIP, R.CCY;
    END LOOP;
END $$;
