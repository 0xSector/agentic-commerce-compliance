# @purpose: Arkham entity attribution. Best-effort — Arkham's public Intel
# Exchange API uses signed-timestamp auth (HMAC) that varies by account tier.
# Slice 2 tries a simple API-Key header GET; slice 3 can wire real signed auth
# if the key we have is for that path. Missing data falls through to "—".

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

ARKHAM_BASE = "https://api.arkhamintelligence.com"


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

    for path in (
        f"/intelligence/address/{address}",
        f"/address/{address}",
    ):
        try:
            r = requests.get(
                f"{ARKHAM_BASE}{path}",
                headers={"API-Key": key, "Accept": "application/json"},
                timeout=20,
            )
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except ValueError:
            continue
        # Arkham responses include nested entity info; grab what looks like a label.
        entity = data.get("arkhamEntity") or data.get("entity") or {}
        label = entity.get("name") or data.get("name")
        etype = entity.get("type") or data.get("type")
        return ArkhamEntity(
            address=address,
            label=label,
            entity_type=etype,
            confidence=entity.get("certainty") or data.get("certainty"),
        )
    return ArkhamEntity(address=address)
