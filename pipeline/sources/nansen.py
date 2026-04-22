# @purpose: Nansen Profiler client via agentcash CLI. Fetches current balance,
# counterparties (for funding-source narrative), and labels per wallet.
# Costs ~$0.07/wallet/week in USDC micropayments.

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

NANSEN_ORIGIN = "https://api.nansen.ai"


@dataclass
class NansenProfile:
    address: str
    chain: str
    current_balance_usd: float = 0.0
    funding_source: str | None = None          # e.g. "Coinbase"
    funding_address: str | None = None
    funding_amount_usd: float = 0.0
    counterparty_count: int = 0
    counterparties: list[str] = field(default_factory=list)
    chains_active: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _agentcash_available() -> bool:
    return shutil.which("npx") is not None and bool(os.environ.get("AGENTCASH_WALLET_PRIVATE_KEY"))


def _agentcash_fetch(path: str, body: dict, timeout: int = 90) -> dict | None:
    """Shell out to agentcash CLI. Returns parsed JSON data, or None on error."""
    url = f"{NANSEN_ORIGIN}{path}"
    cmd = [
        "npx", "-y", "agentcash@latest", "fetch", url,
        "-m", "POST",
        "-b", json.dumps(body),
        "--format", "json",
    ]
    env = os.environ.copy()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    try:
        parsed = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    # agentcash wraps real response in .data.body (or .data depending on path)
    d = parsed.get("data") if isinstance(parsed, dict) else None
    if isinstance(d, dict):
        return d.get("body") or d
    return parsed


def _nansen_chain(chain: str) -> str:
    return {"base": "base", "ethereum": "ethereum", "tempo": "tempo", "solana": "solana"}.get(chain, chain)


def fetch_profile(address: str, chain: str = "base") -> NansenProfile:
    if not _agentcash_available():
        return NansenProfile(address=address, chain=chain, notes=["agentcash unavailable — set AGENTCASH_WALLET_PRIVATE_KEY"])

    nchain = _nansen_chain(chain)
    prof = NansenProfile(address=address, chain=chain)

    bal = _agentcash_fetch("/api/v1/profiler/address/current-balance",
                           {"address": address, "chain": nchain})
    if isinstance(bal, dict):
        # Nansen response shape: {"data": [...]} or direct; grab total USD across returned rows
        rows = bal.get("data") if isinstance(bal.get("data"), list) else []
        if not rows and isinstance(bal.get("totalUsd"), (int, float)):
            prof.current_balance_usd = float(bal["totalUsd"])
        else:
            prof.current_balance_usd = sum(float(r.get("usdValue") or r.get("usd_value") or 0) for r in rows)

    cps = _agentcash_fetch("/api/v1/profiler/address/counterparties",
                           {"address": address, "chain": nchain})
    if isinstance(cps, dict):
        rows = cps.get("data") if isinstance(cps.get("data"), list) else []
        # Inbound counterparties sorted by volume — take top as funding source hypothesis
        inbound = [r for r in rows if (r.get("direction") or "").lower() in ("in", "inbound", "received")]
        inbound.sort(key=lambda r: float(r.get("usdValue") or r.get("volumeUsd") or 0), reverse=True)
        prof.counterparty_count = len(rows)
        prof.counterparties = [
            (r.get("label") or r.get("entity") or r.get("address") or "")[:80]
            for r in rows[:5]
        ]
        if inbound:
            top = inbound[0]
            prof.funding_source = top.get("label") or top.get("entity") or None
            prof.funding_address = top.get("address") or None
            prof.funding_amount_usd = float(top.get("usdValue") or top.get("volumeUsd") or 0)

    labels = _agentcash_fetch("/api/v1/profiler/address/labels",
                              {"address": address, "chain": nchain})
    if isinstance(labels, dict):
        data = labels.get("data")
        if isinstance(data, list):
            prof.labels = [str(x) for x in data[:10]]
        elif isinstance(data, dict) and data.get("labels"):
            prof.labels = [str(x) for x in data["labels"][:10]]

    return prof
