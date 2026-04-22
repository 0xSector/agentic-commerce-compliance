# @purpose: Fans out per-wallet enrichment (Nansen profile, TRM screen, Arkham
# entity). Returns EnrichedBuyer records ready for rubric + narrative.

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from pipeline.aggregate import AggregatedBuyer
from pipeline.sources import arkham, nansen, trm


@dataclass
class EnrichedBuyer:
    buyer: AggregatedBuyer
    nansen: nansen.NansenProfile
    trm: trm.TrmScreen
    arkham: arkham.ArkhamEntity
    facts: list[str] = field(default_factory=list)


def enrich_all(buyers: list[AggregatedBuyer]) -> list[EnrichedBuyer]:
    out: list[EnrichedBuyer] = []
    for i, b in enumerate(buyers):
        chain = "base" if "base" in b.chains else next(iter(b.chains), "base")
        try:
            n = nansen.fetch_profile(b.address, chain=chain)
        except Exception as ex:
            print(f"[enrich] nansen failed for {b.address}: {ex}", file=sys.stderr)
            n = nansen.NansenProfile(address=b.address, chain=chain, notes=[f"error: {ex}"])
        try:
            t = trm.screen(b.address, chain=chain)
            if i == 0:
                import json as _j
                print(f"[trm-debug] first wallet {b.address} raw:", file=sys.stderr)
                print(_j.dumps(t.raw, indent=2)[:2000], file=sys.stderr)
        except Exception as ex:
            print(f"[enrich] trm failed for {b.address}: {ex}", file=sys.stderr)
            t = trm.TrmScreen(address=b.address, chain=chain, raw={"error": str(ex)})
        try:
            a = arkham.lookup(b.address, chain=chain)
        except Exception as ex:
            print(f"[enrich] arkham failed for {b.address}: {ex}", file=sys.stderr)
            a = arkham.ArkhamEntity(address=b.address)
        out.append(EnrichedBuyer(buyer=b, nansen=n, trm=t, arkham=a))
    return out
