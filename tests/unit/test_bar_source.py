"""Unit tests for the deployment → price bar service binding."""

from unittest.mock import MagicMock, patch

import pytest

from quant.trade.bar_source import PriceBarServiceFactory
from quant.trade.errors import TradeValidationError


@pytest.fixture
def factory():
    caches = MagicMock()
    caches.refdata.resolve_app_id.side_effect = lambda name: {
        "bybit": 34,
        "binance": 35,
    }[name]
    with patch("quant.trade.bar_source.PriceBarRepo") as repo_cls:
        yield PriceBarServiceFactory("postgresql://test", caches), repo_cls


class TestPriceBarServiceFactory:
    def test_builds_service_on_the_deployments_venue(self, factory):
        fac, _repo_cls = factory

        service = fac.for_app(34)

        assert service._fetcher._exchange_id == "bybit"

    def test_same_app_reuses_one_service(self, factory):
        """A scheduled apply runs every boundary — don't rebuild the ccxt client."""
        fac, _repo_cls = factory

        assert fac.for_app(34) is fac.for_app(34)

    def test_distinct_apps_get_distinct_venues(self, factory):
        fac, _repo_cls = factory

        assert fac.for_app(34) is not fac.for_app(35)
        assert fac.for_app(35)._fetcher._exchange_id == "binanceusdm"

    def test_one_repo_shared_across_venues(self, factory):
        """Bars for every venue land in the same table, on one connection."""
        fac, repo_cls = factory

        fac.for_app(34)
        fac.for_app(35)

        assert repo_cls.call_count == 1

    def test_app_without_a_venue_is_refused(self, factory):
        fac, _repo_cls = factory

        with pytest.raises(TradeValidationError, match="no market data venue"):
            fac.for_app(999)
