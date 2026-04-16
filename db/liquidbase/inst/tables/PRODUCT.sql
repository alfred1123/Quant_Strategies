-- Canonical product master: tradeable instruments and trackable data series.
-- One row per logical product. Vendor-specific symbols live in PRODUCT_XREF.
CREATE TABLE INST.PRODUCT (
    PRODUCT_ID     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    INTERNAL_CUSIP TEXT NOT NULL UNIQUE,
    SYMBOL   TEXT NOT NULL,
    ASSET_TYPE_ID  INTEGER,
    EXCHANGE       TEXT,
    CCY            TEXT,
    DESCRIPTION    TEXT,
    USER_ID        TEXT,
    UPDATED_AT     TIMESTAMPTZ
);
