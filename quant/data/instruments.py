"""In-process cache for INST product and cross-reference data.

Loads all current products and xrefs at startup via stored procedures,
then serves lookups from memory. Refresh via ``load_all()`` or
``POST /api/v1/inst/refresh``.
"""

import logging

from quant.shared.db import DbGateway

logger = logging.getLogger(__name__)


class InstrumentCache(DbGateway):
    """In-process cache for INST product and cross-reference data.

    Holds a long-lived Postgres connection (managed by ``DbGateway``) for
    INST SP calls so there is no per-query connect overhead.
    """

    def __init__(self, conninfo: str) -> None:
        super().__init__(conninfo, persistent=True)
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
