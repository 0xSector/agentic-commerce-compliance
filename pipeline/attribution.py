# @purpose: Endpoint attribution — given a wallet's per-transfer amounts and
# an origin's published price list, determine which endpoint(s) the wallet was
# likely calling. Invariant: EIP-3009 transfers on Base carry amount only, not
# the resource path, so attribution is by amount matching. Shared prices are
# reported as "ambiguous" — never invent a split.

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass


@dataclass
class EndpointInfo:
    path: str
    method: str
    price_usd: float
    summary: str | None = None


@dataclass
class Attribution:
    amount_usd: float                      # rounded amount (4 decimals)
    tx_count: int                          # how many transfers at this amount
    matched_endpoints: list[EndpointInfo]  # endpoints at this exact price
    confidence: str                        # "unambiguous" | "ambiguous" | "unmatched"


def discover_endpoints(origin: str, timeout: int = 45) -> list[EndpointInfo]:
    """Use agentcash discover to pull endpoint list + prices for an origin."""
    if not shutil.which("npx"):
        return []
    try:
        r = subprocess.run(
            ["npx", "-y", "agentcash@latest", "discover", origin, "--format", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return []
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    endpoints = (data.get("data") or {}).get("endpoints") or []
    out: list[EndpointInfo] = []
    for e in endpoints:
        price = e.get("price")
        usd = _parse_price_usd(price)
        if usd is None:
            continue
        out.append(EndpointInfo(
            path=e.get("path") or "",
            method=e.get("method") or "GET",
            price_usd=usd,
            summary=e.get("summary"),
        ))
    return out


def _parse_price_usd(price: str | float | int | None) -> float | None:
    if price is None:
        return None
    if isinstance(price, (int, float)):
        return float(price)
    s = str(price).strip().lstrip("$").replace("USD", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def attribute(amounts: list[float], endpoints: list[EndpointInfo]) -> list[Attribution]:
    """Group `amounts` by rounded USD value, match against endpoint prices."""
    if not amounts:
        return []
    buckets = Counter(round(a, 4) for a in amounts)

    # Index endpoints by rounded price for fast lookup.
    price_index: dict[float, list[EndpointInfo]] = {}
    for e in endpoints:
        price_index.setdefault(round(e.price_usd, 4), []).append(e)

    out: list[Attribution] = []
    for amt, count in sorted(buckets.items(), key=lambda kv: -kv[0] * kv[1]):
        matches = price_index.get(amt, [])
        if not matches:
            conf = "unmatched"
        elif len(matches) == 1:
            conf = "unambiguous"
        else:
            conf = "ambiguous"
        out.append(Attribution(amount_usd=amt, tx_count=count, matched_endpoints=matches, confidence=conf))
    return out
