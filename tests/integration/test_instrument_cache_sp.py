"""Integration test for INST.SP_GET_PRODUCT_XREF and InstrumentCache.

Exercises the real stored procedure against the configured PostgreSQL
instance and asserts the resolver chain returns the seeded vendor symbol.

Skipped automatically when QUANTDB_URL is not set or the DB is unreachable
(e.g. CI without a database).

This test guards against the TZ-naive ``TIMESTAMPTZ '9999-12-31'`` regression
where the SP filtered out all current xrefs because the literal was
interpreted in the server's session timezone (HKT) but the seeded data was
stored at UTC midnight.
"""


import os

import pytest

psycopg = pytest.importorskip("psycopg")

from quant.data.instruments import InstrumentCache  # noqa: E402


def _resolve_db_url() -> str | None:
    url = os.environ.get("QUANTDB_URL")
    if not url:
        return None
    # Quick reachability probe — skip cleanly if DB is down.
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception:
        return None
    return url


DB_URL = _resolve_db_url()


@pytest.mark.skipif(DB_URL is None, reason="QUANTDB_URL not set or DB unreachable")
def test_sp_get_product_xref_returns_current_rows():
    """SP_GET_PRODUCT_XREF must return the current xrefs for a seeded product.

    Seeds a unique product + xref through the public SPs, then asserts the
    cache (which calls SP_GET_PRODUCT_XREF) sees them.
    """
    import uuid

    cusip = f"itest_{uuid.uuid4().hex[:8]}.x"
    vendor_symbol = f"ITEST_{uuid.uuid4().hex[:6].upper()}"
    app_id = 1  # yahoo — must already exist in REFDATA.APP

    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        # SP_INS_PRODUCT requires an explicit PRODUCT_ID (no sequence).
        cur.execute("SELECT COALESCE(MAX(PRODUCT_ID), 0) + 1 FROM INST.PRODUCT")
        product_id = cur.fetchone()[0]

        # Seed product
        cur.execute(
            "CALL INST.SP_INS_PRODUCT(%s, %s, %s, 1, 'crypto', 'USD', 'integration test', 'pytest', NULL, NULL, NULL)",
            (product_id, cusip, "Integration Test Product"),
        )
        # SP_INS_PRODUCT_XREF requires an explicit PRODUCT_XREF_ID.
        cur.execute("SELECT COALESCE(MAX(PRODUCT_XREF_ID), 0) + 1 FROM INST.PRODUCT_XREF")
        xref_id = cur.fetchone()[0]
        cur.execute(
            "CALL INST.SP_INS_PRODUCT_XREF(%s, %s, %s, %s, 'pytest', NULL, NULL, NULL)",
            (xref_id, product_id, app_id, vendor_symbol),
        )
        conn.commit()

    try:
        cache = InstrumentCache(DB_URL)
        try:
            cache.load_all()
            xrefs = cache.get_xrefs(product_id=product_id)
            assert len(xrefs) == 1, f"expected 1 xref for seeded product, got {xrefs}"
            assert xrefs[0]["vendor_symbol"] == vendor_symbol
            assert cache.resolve_vendor_symbol(product_id, app_id) == vendor_symbol
        finally:
            cache.close()
    finally:
        # Cleanup: hard-delete the seeded rows via raw DML (test data only).
        with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM INST.PRODUCT_XREF WHERE PRODUCT_ID=%s", (product_id,))
            cur.execute("DELETE FROM INST.PRODUCT WHERE PRODUCT_ID=%s", (product_id,))
            conn.commit()
