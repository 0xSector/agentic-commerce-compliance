# @purpose: Applies the risk rubric (config/rubric.yml) to an EnrichedBuyer.
# Returns a tier (LOW / MEDIUM / HIGH) plus the list of flags that fired.
# Slice 1 implements hard flags + a conservative medium path; slice 2 tunes.

from __future__ import annotations

from dataclasses import dataclass

from pipeline.enrich import EnrichedBuyer

HARD = {"trm_sanctions_match", "trm_mixer_direct_exposure", "trm_category_high_risk"}


@dataclass
class RiskAssessment:
    tier: str                # LOW | MEDIUM | HIGH
    flags: list[str]
    reasons: list[str]


def _collect_flags(e: EnrichedBuyer) -> list[str]:
    flags: list[str] = []
    if e.trm.sanctions_hit:
        flags.append("trm_sanctions_match")
    if e.trm.mixer_direct:
        flags.append("trm_mixer_direct_exposure")
    if e.trm.mixer_indirect:
        flags.append("trm_mixer_indirect_exposure")
    if (e.trm.risk_score or 0) >= 15:
        flags.append("trm_category_high_risk")
    if not e.nansen.funding_source:
        flags.append("funding_source_unknown")
    if e.nansen.counterparty_count and e.nansen.counterparty_count < 3:
        flags.append("counterparty_count_under_3")
    return flags


def assess(e: EnrichedBuyer) -> RiskAssessment:
    flags = _collect_flags(e)
    reasons: list[str] = []
    tier = "LOW"
    if any(f in HARD for f in flags):
        tier = "HIGH"
        reasons.append("Hard flag triggered: " + ", ".join(f for f in flags if f in HARD))
    else:
        medium_points = sum(1 for f in flags if f not in HARD)
        if medium_points >= 2:
            tier = "MEDIUM"
            reasons.append(f"{medium_points} medium flag(s) set")
    if not flags:
        reasons.append("No risk flags triggered")
    return RiskAssessment(tier=tier, flags=flags, reasons=reasons)
