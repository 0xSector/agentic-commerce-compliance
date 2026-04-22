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
class Narrative:
    summary: str
    funding_and_behavior: str


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


def build(e: EnrichedBuyer, rank: int, attrs_by_origin: dict[str, list[Attribution]]) -> Narrative:
    return Narrative(
        summary=_summary(e, rank),
        funding_and_behavior=_funding_and_behavior(e),
    )
