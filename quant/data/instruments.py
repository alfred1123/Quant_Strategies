"""In-process cache for INST product and cross-reference data, and its writer.

Loads all current products and xrefs at startup via stored procedures,
then serves lookups from memory. Refresh via ``load_all()`` or
``POST /api/v1/inst/refresh``.

The snapshot is per process. Prod runs ``uvicorn --workers 2``, so a write
that only reloads the worker that handled it leaves the other one serving
the pre-write list — which is how a just-created instrument can appear in
the product dropdown and then fail subscribe with "no xref". A Redis
version stamp (``inst:version``) is checked on every read, the same way
``RedisRefData`` checks ``refdata:version``: the writer bumps it, and any
other process reloads from Postgres before answering.

Creating an instrument lives here too, rather than in a repo of its own. This
class already owns every INST stored-procedure call, and a second class calling
into the same schema would split that ownership for nothing — the write path
needs the cache anyway, to reload itself so the dropdowns see the new row.

Instruments are **not owned**. ``USER_ID`` on the row is audit, the same way it
is on a bar subscription: a product is a shared platform fact, so there is no
owner to scope a read or a write to, and ``user_id`` is a property of this
gateway rather than something threaded through from the caller.
"""

import logging

import redis

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)

#: Bumped after every INST write so every uvicorn worker and the queue
#: worker drop their snapshot on the next read. Same shape as
#: ``refdata:version`` — a stamp, not pub/sub, so a process that was
#: mid-request still finishes on what it loaded and the next one is fresh.
INST_VERSION_KEY = "inst:version"


class InstrumentCache(DbGateway):
    """In-process cache for INST product and cross-reference data.

    Holds a long-lived Postgres connection (managed by ``DbGateway``) for
    INST SP calls so there is no per-query connect overhead.
    """

    def __init__(
        self,
        conninfo: str,
        user_id: str = "system",
        *,
        redis_url: str | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        super().__init__(conninfo, user_id=user_id, persistent=True)
        self._products: list[dict] = []
        self._xrefs: list[dict] = []
        self._by_cusip: dict[str, dict] = {}
        self._by_product_id: dict[int, dict] = {}
        self._xref_index: dict[tuple[int, int], str] = {}
        self._version: str | None = None
        # Tests construct this without Redis and still exercise the lookups.
        # A missing client is "this process is the only one", not an error.
        self._redis = redis_client
        if self._redis is None and redis_url:
            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )

    # ── load ─────────────────────────────────────────────────────────────

    def load_all(self) -> None:
        """Fetch all current products and xrefs into memory."""
        self._products = self._call_get(
            "CALL INST.SP_GET_PRODUCT(%s, %s, NULL, NULL, NULL, NULL)",
            (None, None),
        )
        self._xrefs = self._call_get(
            "CALL INST.SP_GET_PRODUCT_XREF(%s, %s, %s, NULL, NULL, NULL, NULL)",
            (None, None, None),
        )
        self._by_cusip = {p["internal_cusip"]: p for p in self._products}
        self._by_product_id = {p["product_id"]: p for p in self._products}
        self._xref_index = {
            (x["product_id"], x["app_id"]): x["vendor_symbol"]
            for x in self._xrefs
        }
        logger.info(
            "InstrumentCache loaded %d products, %d xrefs",
            len(self._products), len(self._xrefs),
        )
        self._adopt_version()

    # ── cross-process freshness ──────────────────────────────────────────

    def _read_version(self) -> str | None:
        if getattr(self, "_redis", None) is None:
            return None
        try:
            return self._redis.get(INST_VERSION_KEY)
        except redis.RedisError:
            logger.warning(
                "could not read %s — serving the local INST snapshot",
                INST_VERSION_KEY,
                exc_info=True,
            )
            return self._version

    def _adopt_version(self) -> None:
        """Remember the stamp we just loaded, so the next read is a no-op."""
        current = self._read_version()
        if current is None and getattr(self, "_redis", None) is not None:
            try:
                # First process to boot seeds the stamp. SET NX so a create
                # that raced ahead is not overwritten back to zero.
                self._redis.set(INST_VERSION_KEY, "0", nx=True)
                current = self._redis.get(INST_VERSION_KEY)
            except redis.RedisError:
                logger.warning(
                    "could not seed %s — other workers will not see later writes",
                    INST_VERSION_KEY,
                    exc_info=True,
                )
        self._version = current

    def _bump_version(self) -> None:
        """Tell every other process its snapshot is behind.

        INCR rather than a timestamp: two writes in the same second still
        move the stamp, and a worker that loaded in between them reloads
        twice instead of staying on the first write.
        """
        if getattr(self, "_redis", None) is None:
            return
        try:
            self._redis.incr(INST_VERSION_KEY)
        except redis.RedisError:
            logger.warning(
                "could not bump %s — other workers will keep the old INST snapshot",
                INST_VERSION_KEY,
                exc_info=True,
            )

    def _sync(self) -> None:
        """Reload from Postgres if another process has written since we last did."""
        current = self._read_version()
        if current != getattr(self, "_version", None):
            self.load_all()

    # ── product lookups ──────────────────────────────────────────────────

    def get_products(self) -> list[dict]:
        """Return all current products."""
        self._sync()
        return self._products

    def get_product_by_id(self, product_id: int) -> dict | None:
        """Lookup a single product by PRODUCT_ID."""
        self._sync()
        return self._by_product_id.get(product_id)

    def get_product_by_cusip(self, internal_cusip: str) -> dict | None:
        """Lookup a single product by INTERNAL_CUSIP."""
        self._sync()
        return self._by_cusip.get(internal_cusip)

    # ── xref lookups ─────────────────────────────────────────────────────

    def get_xrefs(self, product_id: int | None = None, app_id: int | None = None) -> list[dict]:
        """Return xrefs filtered by product and/or app."""
        self._sync()
        result = self._xrefs
        if product_id is not None:
            result = [x for x in result if x["product_id"] == product_id]
        if app_id is not None:
            result = [x for x in result if x["app_id"] == app_id]
        return result

    def resolve_vendor_symbol(self, product_id: int, app_id: int) -> str | None:
        """Resolve a (product, app) pair to the current vendor symbol.

        Returns ``None`` if no mapping exists.
        """
        self._sync()
        return self._xref_index.get((product_id, app_id))

    def resolve_internal_cusip(self, internal_cusip: str, app_id: int) -> str | None:
        """Resolve ``(internal_cusip, app_id)`` to a vendor symbol.

        Returns ``None`` if the product is unknown or no xref exists.
        """
        product = self.get_product_by_cusip(internal_cusip)
        if product is None:
            return None
        return self.resolve_vendor_symbol(product["product_id"], app_id)

    def refresh(self) -> None:
        """Reload this process, and make every other process do the same.

        The local reload is what the writer needs before it returns the row.
        The version bump is what the *next* request needs — subscribe is a
        different uvicorn worker more often than not.
        """
        self.load_all()
        self._bump_version()
        self._adopt_version()

    # ── writes ───────────────────────────────────────────────────────────

    def sp_ins_product(
        self,
        *,
        internal_cusip: str,
        display_nm: str,
        asset_type_id: int | None = None,
        exchange: str | None = None,
        ccy: str | None = None,
        description: str | None = None,
        product_id: int | None = None,
    ) -> tuple[int, int]:
        """Append a product version and return the ``(id, vid)`` written.

        ``product_id=None`` means a new instrument: the procedure takes
        ``MAX(PRODUCT_ID)+1``. The caller cannot choose the id, because
        ``INST.PRODUCT`` has no sequence and application code is barred from
        raw ``SELECT`` on application tables — "what is the next id" is a
        question only the procedure can answer, which is why it reports the
        answer back instead of the caller guessing it.
        """
        out = self._call_write(
            "CALL INST.SP_INS_PRODUCT("
            "%s::integer, %s::text, %s::text, %s::integer,"
            " %s::text, %s::text, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text,"
            " NULL::integer, NULL::integer)",
            (
                product_id,
                internal_cusip,
                display_nm,
                asset_type_id,
                exchange,
                ccy,
                description,
                self.user_id,
            ),
        )
        return int(out[0]), int(out[1])

    def sp_ins_product_xref(
        self,
        *,
        product_id: int,
        app_id: int,
        vendor_symbol: str,
        product_xref_id: int | None = None,
    ) -> tuple[int, int]:
        """Map a product to one venue's symbol; return the ``(id, vid)`` written.

        ``product_xref_id=None`` means a new mapping and takes
        ``MAX(PRODUCT_XREF_ID)+1``. Naming an existing id versions that mapping
        instead — which is how a mistyped symbol is corrected, since
        ``UQ_PRODUCT_XREF_CURRENT`` allows one open row per
        ``(PRODUCT_ID, APP_ID)`` and a second insert for the pair is refused
        rather than forking it.
        """
        out = self._call_write(
            "CALL INST.SP_INS_PRODUCT_XREF("
            "%s::integer, %s::integer, %s::integer, %s::text, %s::text,"
            " NULL::text, NULL::text, NULL::text,"
            " NULL::integer, NULL::integer)",
            (
                product_xref_id,
                product_id,
                app_id,
                vendor_symbol,
                self.user_id,
            ),
        )
        return int(out[0]), int(out[1])

    def create_instrument(
        self,
        *,
        internal_cusip: str,
        display_nm: str,
        app_id: int,
        vendor_symbol: str,
        asset_type_id: int | None = None,
        exchange: str | None = None,
        ccy: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a product and the first venue symbol for it, as one action.

        Two writes but one instrument. A product with no xref is invisible to
        every venue-scoped read — ``/inst/apps/{app_id}/products`` is built from
        the xrefs, so an unmapped product cannot be subscribed to, backtested
        or deployed. Creating the two separately would therefore expose a state
        that looks like a bug, so the first mapping is part of creating the
        instrument rather than a follow-up step.

        Reloads this process and bumps ``inst:version`` before returning.
        The products and xrefs served to every dropdown come from memory, so
        without the local reload the writer would return a row its own
        lookups cannot see. Without the bump, the other uvicorn worker —
        the one subscribe is likely to hit — would keep the pre-write
        snapshot and refuse a mapping that was just inserted.

        Neither procedure validates its input. ``NOT NULL`` on the columns and
        the two partial unique indexes — ``UQ_PRODUCT_CUSIP_CURRENT`` on the
        cusip, ``UQ_PRODUCT_XREF_CURRENT`` on ``(PRODUCT_ID, APP_ID)`` — are the
        enforcement, and required fields are refused earlier still by
        ``CreateInstrumentRequest``. What arrives here is therefore Postgres
        reporting a constraint, surfaced as ``ProcedureError`` carrying its
        ``sqlstate``, which ``quant.api.exception_handlers`` maps: ``23*`` to
        409. There is nothing a bespoke exception type here would add.

        The two calls are **not one transaction** — ``_call_write`` commits per
        call — so a rejected xref leaves a product no venue lists. That is
        logged rather than swallowed, and the original error is re-raised so
        the status code still describes what the caller got wrong.
        """
        product_id, product_vid = self.sp_ins_product(
            internal_cusip=internal_cusip,
            display_nm=display_nm,
            asset_type_id=asset_type_id,
            exchange=exchange,
            ccy=ccy,
            description=description,
        )
        try:
            xref_id, xref_vid = self.sp_ins_product_xref(
                product_id=product_id,
                app_id=app_id,
                vendor_symbol=vendor_symbol,
            )
        except Exception:
            logger.error(
                "PRODUCT_ID %d (%s) was created but its first xref to app %d as "
                "%r was rejected — the product exists and no venue lists it",
                product_id, internal_cusip, app_id, vendor_symbol,
            )
            raise

        self.refresh()
        product = self.get_product_by_id(product_id)
        if product is None:
            raise RuntimeError(
                "SP_INS_PRODUCT reported PRODUCT_ID "
                f"{product_id} v{product_vid} but SP_GET_PRODUCT does not "
                "return it"
            )

        logger.info(
            "created instrument %s (PRODUCT_ID %d v%d) listed on app %d as %s "
            "(PRODUCT_XREF_ID %d v%d)",
            internal_cusip, product_id, product_vid, app_id, vendor_symbol,
            xref_id, xref_vid,
        )
        return product | {
            "app_id": app_id,
            "vendor_symbol": vendor_symbol,
            "product_xref_id": xref_id,
            "product_xref_vid": xref_vid,
        }
