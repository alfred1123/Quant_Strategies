"""Broker session health types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BrokerSessionState:
    connected: bool
    message: str
