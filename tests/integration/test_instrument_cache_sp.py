"""Integration tests for the INST product procedures and ``InstrumentCache``.

Exercises the real stored procedures against the configured PostgreSQL
instance: creating an instrument allocates its own ids, naming an id appends a
version instead, and the resolver chain returns the seeded vendor symbol.

The refusal cases here assert a SQLSTATE and a constraint name rather than a
sentence, because that is all there is: the procedures carry no validation, so
``NOT NULL`` and the two partial unique indexes are the enforcement and what
reaches the caller is Postgres reporting one of them.

Skipped automatically when QUANTDB_URL is not set or the DB is unreachable
(e.g. CI without a database).

The xref read is also the guard against the TZ-naive
``TIMESTAMPTZ '9999-12-31'`` regression, where the SP filtered out all current
xrefs because the literal was interpreted in the server's session timezone
(HKT) while the seeded data was stored at UTC midnight.
"""


import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from quant.data.instruments import InstrumentCache  # noqa: E402

#: yahoo — must already exist in REFDATA.APP.
YAHOO = 1
#: glassnode — a second venue, for the "one product, many listings" case.
GLASSNODE = 2


#: The OUT column INST release 1.4.0 adds. Its presence is how these tests
#: tell "the database is there" from "the database is there and has the
#: procedures this file calls" — a distinction that matters because a staged
#: Liquibase release is a normal state, not a broken one. Adding an OUT
#: parameter changes a procedure's signature, so against an un-migrated
#: database every CALL below resolves to nothing and fails identically,
#: reporting a missing migration as if the code were wrong.
_RELEASE_MARKER = "out_product_id"

_SIGNATURE_PROBE = """
    SELECT 1
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'inst'
       AND p.proname = 'sp_ins_product'
       AND %s = ANY(p.proargnames)
"""


def _resolve_db_url() -> tuple[str | None, str]:
    """The URL to test against, or ``None`` plus the reason to skip."""
    url = os.environ.get("QUANTDB_URL")
    if not url:
        return None, "QUANTDB_URL not set"
    try:
        with psycopg.connect(url, connect_timeout=2) as conn, conn.cursor() as cur:
            cur.execute(_SIGNATURE_PROBE, (_RELEASE_MARKER,))
            applied = cur.fetchone() is not None
    except Exception:
        return None, "database unreachable"
    if not applied:
        return None, (
            "INST release 1.4.0-product-insert-allocates-id is not applied — "
            "INST.SP_INS_PRODUCT has no OUT_PRODUCT_ID"
        )
    return url, ""


DB_URL, _SKIP_REASON = _resolve_db_url()

pytestmark = pytest.mark.skipif(DB_URL is None, reason=_SKIP_REASON)


def _unique_cusip() -> str:
    return f"itest_{uuid.uuid4().hex[:8]}.x"


def _unique_symbol() -> str:
    return f"ITEST_{uuid.uuid4().hex[:6].upper()}"


def _purge(product_id: int) -> None:
    """Hard-delete the seeded rows via raw DML — test data only.

    Every version, not just the current one: the procedures append rows, so a
    test that versions a mapping leaves more than it created.
    """
    with psycopg.connect(DB_URL) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM INST.PRODUCT_XREF WHERE PRODUCT_ID=%s", (product_id,))
        cur.execute("DELETE FROM INST.PRODUCT WHERE PRODUCT_ID=%s", (product_id,))
        conn.commit()


@pytest.fixture
def cache():
    instance = InstrumentCache(DB_URL, user_id="pytest")
    try:
        yield instance
    finally:
        instance.close()


def test_creating_an_instrument_allocates_its_own_ids(cache):
    """The caller supplies no id, because it has no way to know one.

    ``INST.PRODUCT`` has no sequence and application code is barred from raw
    ``SELECT`` on application tables, so the next ``PRODUCT_ID`` is a question
    only the procedure can answer. Before this it was answered by hand, which
    is why creating an instrument was a direct INSERT against the database.
    """
    cusip = _unique_cusip()
    vendor_symbol = _unique_symbol()

    created = cache.create_instrument(
        internal_cusip=cusip,
        display_nm="Integration Test Product",
        asset_type_id=1,
        # NULL exchange: the venue lives in the xref, never in product identity.
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=vendor_symbol,
    )
    try:
        assert created["product_id"] > 0
        assert created["product_vid"] == 1
        assert created["product_xref_id"] > 0
        assert created["product_xref_vid"] == 1
        assert created["internal_cusip"] == cusip
        assert created["vendor_symbol"] == vendor_symbol
    finally:
        _purge(created["product_id"])


def test_sp_get_product_xref_returns_current_rows(cache):
    """SP_GET_PRODUCT_XREF must return the current xrefs for a seeded product."""
    cusip = _unique_cusip()
    vendor_symbol = _unique_symbol()

    created = cache.create_instrument(
        internal_cusip=cusip,
        display_nm="Integration Test Product",
        asset_type_id=1,
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=vendor_symbol,
    )
    product_id = created["product_id"]
    try:
        # create_instrument already reloaded the cache — the whole point is
        # that a new instrument is visible without a separate refresh.
        xrefs = cache.get_xrefs(product_id=product_id)
        assert len(xrefs) == 1, f"expected 1 xref for seeded product, got {xrefs}"
        assert xrefs[0]["vendor_symbol"] == vendor_symbol
        assert cache.resolve_vendor_symbol(product_id, YAHOO) == vendor_symbol
        assert cache.resolve_internal_cusip(cusip, YAHOO) == vendor_symbol
    finally:
        _purge(product_id)


def test_a_second_current_row_for_a_cusip_is_refused(cache):
    """The cusip is the identity every other schema stores.

    Two current rows carrying it would fork one instrument.
    ``UQ_PRODUCT_CUSIP_CURRENT`` is the whole of that enforcement — the
    procedure carries no duplicate check of its own, so what reaches the caller
    is the index's own unique-violation.
    """
    from quant.shared.db import ProcedureError

    cusip = _unique_cusip()
    created = cache.create_instrument(
        internal_cusip=cusip,
        display_nm="Integration Test Product",
        asset_type_id=1,
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=_unique_symbol(),
    )
    try:
        with pytest.raises(ProcedureError) as exc:
            cache.sp_ins_product(
                internal_cusip=cusip, display_nm="Duplicate Attempt"
            )

        assert exc.value.sqlstate == "23505"
        assert "uq_product_cusip_current" in exc.value.message.lower()
    finally:
        _purge(created["product_id"])


def test_a_second_open_mapping_for_one_venue_is_refused(cache):
    """A venue prints one symbol at a time, and the index is what says so.

    With no id supplied the procedure allocates MAX+1, which for a pair that
    already has an open row is a second one — refused by
    ``UQ_PRODUCT_XREF_CURRENT`` rather than quietly forking the mapping.
    Repointing is done by naming the id, in the test below.
    """
    from quant.shared.db import ProcedureError

    created = cache.create_instrument(
        internal_cusip=_unique_cusip(),
        display_nm="Integration Test Product",
        asset_type_id=1,
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=_unique_symbol(),
    )
    product_id = created["product_id"]
    try:
        with pytest.raises(ProcedureError) as exc:
            cache.sp_ins_product_xref(
                product_id=product_id, app_id=YAHOO,
                vendor_symbol=_unique_symbol(),
            )

        assert exc.value.sqlstate == "23505"
        assert "uq_product_xref_current" in exc.value.message.lower()
    finally:
        _purge(product_id)


def test_repointing_a_mapping_by_id_appends_a_version(cache):
    """Correcting a mistyped symbol versions the mapping it names.

    The soft-versioning contract: a non-NULL id closes the open row and
    inserts ``VID+1``, so the correction is a new version of that mapping and
    the old symbol stays readable as history.
    """
    created = cache.create_instrument(
        internal_cusip=_unique_cusip(),
        display_nm="Integration Test Product",
        asset_type_id=1,
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=_unique_symbol(),
    )
    product_id = created["product_id"]
    corrected = _unique_symbol()
    try:
        xref_id, xref_vid = cache.sp_ins_product_xref(
            product_xref_id=created["product_xref_id"],
            product_id=product_id,
            app_id=YAHOO,
            vendor_symbol=corrected,
        )

        assert xref_id == created["product_xref_id"]
        assert xref_vid == created["product_xref_vid"] + 1

        cache.refresh()
        assert cache.resolve_vendor_symbol(product_id, YAHOO) == corrected
    finally:
        _purge(product_id)


def test_amending_a_product_by_id_appends_a_version(cache):
    """The other half of soft-versioning: a named ``PRODUCT_ID`` is amended.

    The current row flips to ``'N'`` and ``VID+1`` becomes current, so the
    cusip keeps exactly one current row and the previous attributes remain.
    """
    cusip = _unique_cusip()
    created = cache.create_instrument(
        internal_cusip=cusip,
        display_nm="Integration Test Product",
        asset_type_id=1,
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=_unique_symbol(),
    )
    product_id = created["product_id"]
    try:
        amended_id, amended_vid = cache.sp_ins_product(
            product_id=product_id,
            internal_cusip=cusip,
            display_nm="Renamed Product",
            asset_type_id=1,
            ccy="USDT",
        )

        assert amended_id == product_id
        assert amended_vid == created["product_vid"] + 1

        cache.refresh()
        current = cache.get_product_by_cusip(cusip)
        assert current["display_nm"] == "Renamed Product"
        assert current["product_vid"] == amended_vid
    finally:
        _purge(product_id)


def test_one_product_can_be_listed_on_a_second_venue(cache):
    """Bybit and Yahoo share a cusip and differ only in their xref.

    A second venue is a second mapping, never a second product — the
    anti-pattern decision #21 exists to rule out.
    """
    created = cache.create_instrument(
        internal_cusip=_unique_cusip(),
        display_nm="Integration Test Product",
        asset_type_id=1,
        exchange=None,
        ccy="USD",
        description="integration test",
        app_id=YAHOO,
        vendor_symbol=_unique_symbol(),
    )
    product_id = created["product_id"]
    elsewhere = _unique_symbol()
    try:
        xref_id, _vid = cache.sp_ins_product_xref(
            product_id=product_id, app_id=GLASSNODE, vendor_symbol=elsewhere
        )
        assert xref_id != created["product_xref_id"]

        cache.refresh()
        assert cache.resolve_vendor_symbol(product_id, GLASSNODE) == elsewhere
        assert (
            cache.resolve_vendor_symbol(product_id, YAHOO)
            == created["vendor_symbol"]
        )
    finally:
        _purge(product_id)
