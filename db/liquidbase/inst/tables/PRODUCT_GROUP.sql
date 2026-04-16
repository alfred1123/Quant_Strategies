-- Named product universe / basket with self-referential hierarchy.
-- PARENT_GROUP_ID forms a tree (NULL = root). GROUP_LEVEL is computed by the SP.
-- Products attach to leaf groups only; parents aggregate via recursive CTE.
CREATE TABLE INST.PRODUCT_GROUP (
    PRODUCT_GROUP_ID  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    PARENT_GROUP_ID   INTEGER,
    GROUP_LEVEL       INTEGER NOT NULL,
    GROUP_NM          TEXT NOT NULL UNIQUE,
    DISPLAY_NAME      TEXT NOT NULL,
    DESCRIPTION       TEXT,
    USER_ID           TEXT,
    UPDATED_AT        TIMESTAMPTZ
);
