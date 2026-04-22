# @purpose: Fans out per-wallet enrichment (Nansen profile, TRM screen, Arkham
# entity) for each top-N buyer. Returns a flat dict-like record ready for
# rubric evaluation and rendering.

from __future__ import annotations

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
    for b in buyers:
        chain = "base" if "base" in b.chains else next(iter(b.chains), "base")
        out.append(EnrichedBuyer(
            buyer=b,
            nansen=nansen.fetch_profile(b.address, chain=chain),
            trm=trm.screen(b.address, chain=chain),
            arkham=arkham.lookup(b.address, chain=chain),
        ))
    return out
