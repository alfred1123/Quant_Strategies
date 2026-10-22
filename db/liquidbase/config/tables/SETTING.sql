-- Scalar platform policy that used to be a literal in Python.
--
-- One row per knob. SETTING_VALUE is text; the reader casts at the call site
-- (RedisRefData.setting / setting_int / setting_float). A knob that varies by
-- broker or cadence does not belong here — it gets its own typed table
-- (APP_APPLY_TIMING, APP_ISSUE_FEE).
CREATE TABLE CONFIG.SETTING (
    SETTING_NM     TEXT PRIMARY KEY,
    SETTING_VALUE  TEXT NOT NULL,
    DESCRIPTION    TEXT,
    USER_ID        TEXT,
    UPDATED_AT     TIMESTAMPTZ
);
