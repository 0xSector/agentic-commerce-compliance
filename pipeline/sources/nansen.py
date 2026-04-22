# @purpose: Nansen Profiler client — pulls funding source, balance, counterparties
# for a wallet. Slice 2 wires the real call via agentcash (paid x402 micropayments).

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NansenProfile:
    address: str
    chain: str
    current_balance_usd: float = 0.0
    funding_source: str | None = None          # e.g. "Coinbase"
    funding_address: str | None = None
    funding_amount_usd: float = 0.0
    counterparty_count: int = 0
    counterparties: list[str] = field(default_factory=list)
    chains_active: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def fetch_profile(address: str, chain: str = "base") -> NansenProfile:
    """Stub — returns an empty profile until slice 2."""
    return NansenProfile(address=address, chain=chain, notes=["stub — slice 2 wires agentcash"])
