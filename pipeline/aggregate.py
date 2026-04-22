# @purpose: Combines per-origin buyer spend from all sources into a single
# top-N ranking. Aggregates the same wallet across origins, sums USD spend
# and tx counts, and surfaces which origins each wallet touched.

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pipeline.sources.mppscan import MppBuyerSpend
from pipeline.sources.x402scan import BuyerSpend


@dataclass
class AggregatedBuyer:
    address: str
    total_usd: float = 0.0
    total_tx: int = 0
    origins: list[str] = field(default_factory=list)     # x402 origins
    mpp_servers: list[str] = field(default_factory=list) # mpp server_hashes
    chains: set[str] = field(default_factory=set)
    # per-origin tx amount list — for endpoint attribution
    amounts_by_origin: dict[str, list[float]] = field(default_factory=dict)


def aggregate(
    x402_spend: list[BuyerSpend],
    mpp_spend: list[MppBuyerSpend],
    top_n: int = 20,
) -> list[AggregatedBuyer]:
    by_addr: dict[str, AggregatedBuyer] = {}
    for b in x402_spend:
        a = by_addr.setdefault(b.address.lower(), AggregatedBuyer(address=b.address.lower()))
        a.total_usd += b.total_usd
        a.total_tx += b.tx_count
        if b.origin not in a.origins:
            a.origins.append(b.origin)
        a.chains.add("base")
        a.amounts_by_origin.setdefault(b.origin, []).extend(b.tx_amounts)

    for m in mpp_spend:
        a = by_addr.setdefault(m.address.lower(), AggregatedBuyer(address=m.address.lower()))
        a.total_usd += m.total_usd
        a.total_tx += m.tx_count
        if m.server_hash not in a.mpp_servers:
            a.mpp_servers.append(m.server_hash)
        a.chains.add("tempo")

    ranked = sorted(by_addr.values(), key=lambda x: x.total_usd, reverse=True)
    return ranked[:top_n]
