# @purpose: MPP (Tempo) data adapter. Slice 1 is a stub — slice 2 will implement
# Allium-based Tempo MPP tx pulls (primary) with mppscan RSC scrape fallback.

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MppBuyerSpend:
    address: str
    server_hash: str
    tx_count: int
    total_usd: float


def buyer_spend_for_servers(server_hashes: list[str], days: int = 7) -> list[MppBuyerSpend]:
    """Stub — returns [] until Allium integration lands in slice 2.

    Planned primary path (slice 2):
      SELECT sender, server_hash, COUNT(*) as tx, SUM(amount_usd) as spend
      FROM tempo.mpp_transactions
      WHERE server_hash IN (...) AND block_time >= NOW() - INTERVAL '7 days'
      GROUP BY sender, server_hash
      ORDER BY spend DESC
    """
    return []
