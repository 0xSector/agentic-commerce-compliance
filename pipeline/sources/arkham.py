# @purpose: Arkham entity attribution client. Pulls known entity label
# (if any) for a wallet. Slice 1 is a stub returning None.

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ArkhamEntity:
    address: str
    label: str | None = None
    entity_type: str | None = None   # e.g. "cex", "defi", "individual"
    confidence: str | None = None


def lookup(address: str, chain: str = "base") -> ArkhamEntity:
    key = os.environ.get("ARKHAM_API_KEY")
    if not key:
        return ArkhamEntity(address=address)
    # slice 2: real call to Arkham's /wallet/{chain}/{address} endpoint
    return ArkhamEntity(address=address)
