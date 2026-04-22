# @purpose: TRM Labs screening API client. Pulls sanctions + risk category
# exposure for an address. Minimal, ready to go — just needs TRM_API_KEY.

from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests

TRM_URL = "https://api.trmlabs.com/public/v1/screening/addresses"


@dataclass
class TrmScreen:
    address: str
    chain: str
    risk_score: int | None = None
    sanctions_hit: bool = False
    categories: list[str] = field(default_factory=list)
    mixer_direct: bool = False
    mixer_indirect: bool = False
    raw: dict = field(default_factory=dict)


def _chain_to_trm(chain: str) -> str:
    return {"base": "base", "ethereum": "ethereum", "tempo": "tempo", "solana": "solana"}.get(chain, chain)


def screen(address: str, chain: str = "base") -> TrmScreen:
    key = os.environ.get("TRM_API_KEY")
    if not key:
        # stub path — keep slice 1 running without key
        return TrmScreen(address=address, chain=chain, raw={"stub": "TRM_API_KEY not set"})

    body = [{"address": address, "chain": _chain_to_trm(chain)}]
    r = requests.post(
        TRM_URL,
        json=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    item = data[0] if isinstance(data, list) and data else {}

    categories = [c.get("category") for c in (item.get("addressRiskIndicators") or []) if c.get("category")]
    # heuristic classification — refine in slice 2 with actual TRM category taxonomy
    sanctions = any("sanction" in (c or "").lower() for c in categories)
    mixer_direct = any("mixer" in (c or "").lower() and "indirect" not in (c or "").lower() for c in categories)
    mixer_indirect = any("mixer" in (c or "").lower() and "indirect" in (c or "").lower() for c in categories)

    return TrmScreen(
        address=address,
        chain=chain,
        risk_score=item.get("riskScore"),
        sanctions_hit=sanctions,
        categories=categories,
        mixer_direct=mixer_direct,
        mixer_indirect=mixer_indirect,
        raw=item,
    )
