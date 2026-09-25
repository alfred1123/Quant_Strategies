-- Stamp ISSUE_TYPE on the current instrument rows.
--
-- INST.PRODUCT is soft-versioned: SP_INS_PRODUCT flips the current row to 'N'
-- and inserts a new VID. A row that already has ISSUE_TYPE is left alone.
--
-- spot  — the exchange pair itself (btcusdt.crypto and the same shape).
-- etf   — a share of a listed fund, including funds whose basket is bitcoin
--         futures (BITO, 03066.hkex, 03135.hkex) and the leveraged and inverse
--         funds. The futures contract is not the instrument.
-- stock — a listed company.
DO $$
DECLARE
    R            RECORD;
    V_ISSUE_TYPE TEXT;
    V_SQLSTATE   TEXT;
    V_SQLMSG     TEXT;
    V_SQLERRMC   TEXT;
    V_PRODUCT_ID INTEGER;
    V_PRODUCT_VID INTEGER;
BEGIN
    FOR R IN
        SELECT PRODUCT_ID,
               INTERNAL_CUSIP,
               DISPLAY_NM,
               ASSET_TYPE_ID,
               EXCHANGE,
               CCY,
               DESCRIPTION
          FROM INST.PRODUCT
         WHERE IS_CURRENT_IND = 'Y'
           AND ISSUE_TYPE IS NULL
    LOOP
        V_ISSUE_TYPE := CASE
            WHEN R.INTERNAL_CUSIP IN (
                'btcusdt.crypto',
                'ethusdt.crypto',
                'bnbusdt.crypto'
            ) THEN 'spot'
            WHEN R.INTERNAL_CUSIP IN (
                'ibit.nasdaq',
                'fbtc.cboebzx',
                'gbtc.nysearca',
                'btc.nysearca',
                'bitb.nysearca',
                'arkb.cboebzx',
                'hodl.cboebzx',
                'brrr.nasdaq',
                'ezbc.cboebzx',
                'btco.cboebzx',
                'btcw.cboebzx',
                'msbt.nysearca',
                'bito.nysearca',
                'bitx.cboebzx',
                'biti.nysearca',
                '03042.hkex',
                '09042.hkex',
                '83042.hkex',
                '03008.hkex',
                '03439.hkex',
                '03066.hkex',
                '03135.hkex',
                '07376.hkex'
            ) THEN 'etf'
            WHEN R.INTERNAL_CUSIP IN (
                'mara.nasdaq',
                'riot.nasdaq',
                'clsk.nasdaq',
                'corz.nasdaq',
                'cifr.nasdaq',
                'hut.nasdaq',
                'btdr.nasdaq',
                'wulf.nasdaq',
                'iren.nasdaq',
                'btbt.nasdaq',
                'mstr.nasdaq',
                'coin.nasdaq',
                'hood.nasdaq',
                'bmnr.nyse',
                '00863.hkex',
                '01611.hkex',
                '00434.hkex',
                '01499.hkex',
                '01647.hkex'
            ) THEN 'stock'
            ELSE NULL
        END;

        IF V_ISSUE_TYPE IS NULL THEN
            RAISE NOTICE 'left % unset — not in the issue-type list', R.INTERNAL_CUSIP;
            CONTINUE;
        END IF;

        CALL INST.SP_INS_PRODUCT(
            R.PRODUCT_ID,
            R.INTERNAL_CUSIP,
            R.DISPLAY_NM,
            R.ASSET_TYPE_ID,
            R.EXCHANGE,
            R.CCY,
            R.DESCRIPTION,
            V_ISSUE_TYPE,
            'liquibase',
            V_SQLSTATE, V_SQLMSG, V_SQLERRMC,
            V_PRODUCT_ID, V_PRODUCT_VID
        );

        IF V_SQLSTATE <> '00000' THEN
            RAISE EXCEPTION 'SP_INS_PRODUCT failed for %: % (%)',
                R.INTERNAL_CUSIP, V_SQLERRMC, V_SQLSTATE;
        END IF;

        RAISE NOTICE 'set % to %', R.INTERNAL_CUSIP, V_ISSUE_TYPE;
    END LOOP;
END $$;
