# @purpose: Generates plain-English narrative from enrichment facts.
# Template-driven (deterministic, no LLM cost). Three sections mirror the
# sample output the user provided: Summary, Funding & Behavior, What They're
# Buying. Intent speculation is explicit and tagged as hypothesis.

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pipeline.attribution import Attribution
from pipeline.enrich import EnrichedBuyer


@dataclass
class ComplianceAnalysis:
    overall: str                  # e.g. "LOW–MEDIUM"
    why_not_high: str | None      # omitted if overall is HIGH
    why_not_low: str | None       # omitted if overall is LOW
    investigation_path: str


@dataclass
class Narrative:
    summary: str
    funding_and_behavior: str
    compliance: ComplianceAnalysis | None = None


KYC_EXCHANGES = {"coinbase", "kraken", "binance", "binance.us", "gemini", "bitstamp", "okx", "robinhood"}


def _is_kyc_exchange(label: str | None) -> bool:
    if not label:
        return False
    s = label.lower()
    return any(ex in s for ex in KYC_EXCHANGES)


def _fmt_usd(x: float) -> str:
    return f"${x:,.2f}"


def _summary(e: EnrichedBuyer, rank: int) -> str:
    b = e.buyer
    origins_txt = ", ".join(b.origins) or "MPP-only"
    return (
        f"Wallet {b.address} ranked #{rank} among top buyers this week, with "
        f"{_fmt_usd(b.total_usd)} across {b.total_tx} transactions on {origins_txt}. "
        f"Activity spans {', '.join(sorted(b.chains)) or 'unknown'}."
    )


def _funding_and_behavior(e: EnrichedBuyer) -> str:
    n = e.nansen
    parts: list[str] = []
    if n.funding_source:
        kyc = " (KYC'd exchange)" if _is_kyc_exchange(n.funding_source) else ""
        parts.append(
            f"Primary inbound funding: {n.funding_source}{kyc}"
            + (f" via {n.funding_address}" if n.funding_address else "")
            + (f", {_fmt_usd(n.funding_amount_usd)}" if n.funding_amount_usd else "")
            + "."
        )
    elif n.counterparty_count == 0:
        parts.append("No Nansen counterparty data returned.")
    else:
        parts.append(f"No labeled funding source; {n.counterparty_count} total counterparties.")

    if n.current_balance_usd:
        parts.append(f"Current balance: {_fmt_usd(n.current_balance_usd)}.")

    if e.trm.sanctions_hit:
        parts.append("TRM: **sanctions hit**.")
    if e.trm.mixer_direct:
        parts.append("TRM: direct mixer exposure.")
    if e.trm.mixer_indirect and not e.trm.mixer_direct:
        parts.append("TRM: indirect mixer exposure.")
    if e.trm.categories:
        parts.append("TRM categories: " + ", ".join(e.trm.categories[:4]) + ".")

    return " ".join(parts) or "No enrichment signal available."


def _short_addr(addr: str | None) -> str:
    if not addr or len(addr) < 10:
        return addr or ""
    return f"{addr[:8]}…{addr[-4:]}"


def _behavioral_signals(e: EnrichedBuyer, attrs_by_origin: dict[str, list[Attribution]]) -> dict:
    """Derive behavioral-pattern flags from the aggregated tx data."""
    b = e.buyer
    all_amounts: list[float] = []
    for amounts in b.amounts_by_origin.values():
        all_amounts.extend(amounts)

    distinct_prices = len({round(a, 4) for a in all_amounts})
    origins_count = len(b.origins) + len(b.mpp_servers)

    return {
        "tight_automation": b.total_tx >= 100 and distinct_prices <= 3,
        "single_origin": origins_count <= 1 and b.total_tx >= 50,
        "high_volume": b.total_tx >= 200,
        "unknown_funding": e.nansen.funding_source is None,
        "kyc_funding": _is_kyc_exchange(e.nansen.funding_source),
        "no_mixer": not (e.trm.mixer_direct or e.trm.mixer_indirect),
        "no_sanctions": not e.trm.sanctions_hit,
    }


def _build_compliance(e: EnrichedBuyer, tier: str, attrs_by_origin: dict[str, list[Attribution]]) -> ComplianceAnalysis:
    s = _behavioral_signals(e, attrs_by_origin)
    n = e.nansen
    t = e.trm

    # Overall label — rubric tier, optionally compound when signals don't all align.
    concern_count = sum([s["tight_automation"], s["single_origin"], s["unknown_funding"], s["high_volume"]])
    if tier == "HIGH":
        overall = "HIGH"
    elif tier == "MEDIUM":
        overall = "MEDIUM–HIGH" if concern_count >= 3 else "MEDIUM"
    else:  # LOW
        overall = "LOW–MEDIUM" if concern_count >= 1 else "LOW"

    # Why not HIGH — clean factors.
    why_not_high: str | None = None
    if overall != "HIGH":
        parts: list[str] = []
        if s["kyc_funding"]:
            parts.append(f"funding came from {n.funding_source.split('[')[0].strip()}, a KYC'd exchange — a verified identity exists behind this wallet")
        if s["no_mixer"]:
            parts.append("no mixer or privacy-tool interaction detected")
        if s["no_sanctions"]:
            parts.append("no contact with sanctioned addresses")
        if parts:
            why_not_high = "Fully transparent and traceable: " + "; ".join(parts) + "."
        else:
            why_not_high = "TRM returned no risk indicators, but no strongly-positive signals either; treat as unscored rather than cleared."

    # Why not LOW — behavioral concerns that keep it off the bottom tier.
    why_not_low: str | None = None
    if overall != "LOW":
        c_parts: list[str] = []
        if s["tight_automation"]:
            c_parts.append(f"tight automated loop — {e.buyer.total_tx} transactions at a narrow set of uniform prices is consistent with scripted bulk data buying")
        if s["single_origin"]:
            c_parts.append("single-origin activity — the wallet does effectively nothing except buy from this API")
        if s["high_volume"] and not s["tight_automation"]:
            c_parts.append(f"high transaction volume ({e.buyer.total_tx} txs in 7 days) indicates pipeline-scale usage")
        if s["unknown_funding"]:
            c_parts.append("no labeled funding source, which limits traceback without additional on-chain work")
        if t.mixer_indirect and not t.mixer_direct:
            c_parts.append("indirect mixer exposure per TRM")
        if c_parts:
            why_not_low = (
                "Behavioral pattern is the concern: " + "; ".join(c_parts) + ". "
                "This pattern fits both legitimate sales prospecting / lead generation and "
                "adversarial target-list building — on-chain data alone cannot distinguish intent."
            )

    # Investigation path.
    if t.sanctions_hit:
        investigation_path = (
            "Sanctions hit is the primary concern. Escalate to compliance immediately and halt "
            "any Visa-adjacent interaction with this address pending formal OFAC review."
        )
    elif s["kyc_funding"] and n.funding_address:
        exchange_name = n.funding_source.split('[')[0].strip()
        investigation_path = (
            f"KYC trail is the direct follow-up. A subpoena or law-enforcement request to "
            f"{exchange_name} for the account holder behind deposit address "
            f"{_short_addr(n.funding_address)} would resolve attribution."
        )
    elif n.funding_source and n.funding_address:
        investigation_path = (
            f"Primary inbound funder is {n.funding_source.split('[')[0].strip()} "
            f"({_short_addr(n.funding_address)}). Tracing through that counterparty is the "
            f"next step; no direct KYC handle without a centralized intermediary."
        )
    else:
        investigation_path = (
            "No labeled funding source identified in Nansen. Next step is deeper tx-graph "
            "analysis to reach a KYC'd counterparty before attribution is possible."
        )

    return ComplianceAnalysis(
        overall=overall,
        why_not_high=why_not_high,
        why_not_low=why_not_low,
        investigation_path=investigation_path,
    )


def build(e: EnrichedBuyer, rank: int, attrs_by_origin: dict[str, list[Attribution]], tier: str = "LOW") -> Narrative:
    return Narrative(
        summary=_summary(e, rank),
        funding_and_behavior=_funding_and_behavior(e),
        compliance=_build_compliance(e, tier, attrs_by_origin),
    )
