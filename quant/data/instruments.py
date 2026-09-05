"""In-process cache for INST product and cross-reference data, and its writer.

Loads all current products and xrefs at startup via stored procedures,
then serves lookups from memory. Refresh via ``load_all()`` or
``POST /api/v1/inst/refresh``.

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

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class InstrumentCache(DbGateway):
    """In-process cache for INST product and cross-reference data.

    Holds a long-lived Postgres connection (managed by ``DbGateway``) for
    INST SP calls so there is no per-query connect overhead.
    """

    def __init__(self, conninfo: str, user_id: str = "system") -> None:
        super().__init__(conninfo, user_id=user_id, persistent=True)
        self._products: list[dict] = []
        self._xrefs: list[dict] = []
        self._by_cusip: dict[str, dict] = {}
        self._by_product_id: dict[int, dict] = {}
        self._xref_index: dict[tuple[int, int], str] = {}

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

    # ── product lookups ──────────────────────────────────────────────────

    def get_products(self) -> list[dict]:
        """Return all current products."""
        return self._products

    def get_product_by_id(self, product_id: int) -> dict | None:
        """Lookup a single product by PRODUCT_ID."""
        return self._by_product_id.get(product_id)

    def get_product_by_cusip(self, internal_cusip: str) -> dict | None:
        """Lookup a single product by INTERNAL_CUSIP."""
        return self._by_cusip.get(internal_cusip)

    # ── xref lookups ─────────────────────────────────────────────────────

    def get_xrefs(self, product_id: int | None = None, app_id: int | None = None) -> list[dict]:
        """Return xrefs filtered by product and/or app."""
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
        self.load_all()

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

        Reloads the cache before returning: the products and xrefs served to
        every dropdown come from memory, so without this the instrument would
        not appear until the next ``POST /api/v1/inst/refresh`` or restart —
        and the caller's next action is to use it.

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
