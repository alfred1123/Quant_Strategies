-- Vendor-specific symbol cross-references for each product.
-- One row per (product, provider) pair. Replaces REFDATA.TICKER_MAPPING.
CREATE TABLE INST.PRODUCT_XREF (
    PRODUCT_XREF_ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    PRODUCT_ID      INTEGER NOT NULL,
    APP_ID          INTEGER NOT NULL,
    VENDOR_SYMBOL   TEXT NOT NULL,
    USER_ID         TEXT,
    UPDATED_AT      TIMESTAMPTZ,
    UNIQUE (PRODUCT_ID, APP_ID)
);
