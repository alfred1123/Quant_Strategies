"""What a venue reports about one API key, and the egress route it answered on."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

from quant.trade.models.order import OrderRejectReason


@dataclass(frozen=True)
class ApiKeyInfo:
    """The venue's own description of a key (Bybit: "Get API Key Information")."""

    ips: tuple[str, ...] = ()
    kyc_region: str | None = None
    read_only: bool | None = None
    expires_at: str | None = None

    def to_json(self) -> dict:
        return {**asdict(self), "ips": list(self.ips)}

    @classmethod
    def from_json(cls, payload: dict) -> ApiKeyInfo:
        return cls(
            ips=tuple(payload.get("ips") or ()),
            kyc_region=payload.get("kyc_region"),
            read_only=payload.get("read_only"),
            expires_at=payload.get("expires_at"),
        )


@dataclass(frozen=True)
class KeyProfile:
    """One API key as the venue sees it — cached, never stored.

    The user can change any of this at the venue without telling us, so it is
    re-read rather than persisted: ``route`` is whichever egress the venue last
    accepted the key from, and ``info`` is what it said about the key then
    (``None`` for a venue with no key-information call).
    ``restricted_market_types`` is learned from refusals (Bybit ``10024``),
    because no venue publishes per-product eligibility up front.
    """

    route: str
    info: ApiKeyInfo | None = None
    restricted_market_types: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def accepted(
        cls, route: str, info: ApiKeyInfo | None, *, carrying: KeyProfile | None
    ) -> KeyProfile:
        """The profile after the venue accepted the key on *route*.

        Learned restrictions are carried over from the previous profile: a
        reconnect proves the route, not that a refused product is now allowed.
        """
        return cls(
            route=route,
            info=info,
            restricted_market_types=(
                carrying.restricted_market_types if carrying else frozenset()
            ),
        )

    def refusal(self, market_type: str) -> tuple[OrderRejectReason, str] | None:
        """Why an order of *market_type* cannot succeed on this key, or ``None``."""
        if self.info is not None and self.info.read_only:
            return (
                OrderRejectReason.KEY_READ_ONLY,
                "API key is read-only — enable trading on it at the venue",
            )
        if market_type in self.restricted_market_types:
            region = (self.info.kyc_region if self.info else None) or "unknown"
            return (
                OrderRejectReason.REGION_RESTRICTED,
                f"venue refuses {market_type} for this account (KYC region {region})",
            )
        return None

    def restricting(self, market_type: str) -> KeyProfile:
        return replace(
            self,
            restricted_market_types=self.restricted_market_types | {market_type},
        )

    def to_json(self) -> dict:
        return {
            "route": self.route,
            "info": self.info.to_json() if self.info else None,
            "restricted_market_types": sorted(self.restricted_market_types),
        }

    @classmethod
    def from_json(cls, payload: dict) -> KeyProfile:
        info = payload.get("info")
        return cls(
            route=payload["route"],
            info=ApiKeyInfo.from_json(info) if info else None,
            restricted_market_types=frozenset(
                payload.get("restricted_market_types") or ()
            ),
        )
