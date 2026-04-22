# @purpose: Nansen Profiler client via agentcash CLI. Fetches current balance,
# counterparties (for funding-source narrative), and labels per wallet.
# Costs ~$0.07/wallet/week in USDC micropayments.

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

NANSEN_ORIGIN = "https://api.nansen.ai"
# Wide historical window — funding source is usually the first-ever inbound.
NANSEN_HISTORY_FROM = "2024-01-01"


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
        print(f"[nansen] {path} timeout", file=sys.stderr)
        return None
    if r.returncode != 0:
        print(f"[nansen] {path} rc={r.returncode}: {(r.stderr or '')[:200]}", file=sys.stderr)
        return None
    try:
        parsed = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"[nansen] {path} bad JSON: {(r.stdout or '')[:200]}", file=sys.stderr)
        return None
    # agentcash wraps real response in .data.body (or .data depending on path)
    d = parsed.get("data") if isinstance(parsed, dict) else None
    if isinstance(d, dict):
        return d.get("body") or d
    return parsed


def _nansen_chain(chain: str) -> str:
    return {"base": "base", "ethereum": "ethereum", "tempo": "tempo", "solana": "solana"}.get(chain, chain)


def _first_label(arr) -> str | None:
    if isinstance(arr, list) and arr:
        return str(arr[0])
    if isinstance(arr, str):
        return arr
    return None


def fetch_profile(address: str, chain: str = "base") -> NansenProfile:
    if not _agentcash_available():
        return NansenProfile(address=address, chain=chain, notes=["agentcash unavailable — set AGENTCASH_WALLET_PRIVATE_KEY"])

    nchain = _nansen_chain(chain)
    prof = NansenProfile(address=address, chain=chain)
    today = _dt.date.today().isoformat()

    # Current balance — simple body.
    bal = _agentcash_fetch("/api/v1/profiler/address/current-balance",
                           {"address": address, "chain": nchain})
    if isinstance(bal, dict):
        rows = bal.get("data") if isinstance(bal.get("data"), list) else []
        prof.current_balance_usd = sum(float(r.get("value_usd") or r.get("usdValue") or 0) for r in rows)
        prof.chains_active = sorted({str(r.get("chain") or "") for r in rows if r.get("chain")})

    # Counterparties — requires `date` range. Use wide history to catch funding source.
    cps = _agentcash_fetch(
        "/api/v1/profiler/address/counterparties",
        {
            "address": address,
            "chain": nchain,
            "date": {"from": NANSEN_HISTORY_FROM, "to": today},
        },
    )
    if isinstance(cps, dict):
        rows = cps.get("data") if isinstance(cps.get("data"), list) else []
        prof.counterparty_count = len(rows)
        # Short display list of top-5 counterparties by total volume.
        rows_sorted = sorted(rows, key=lambda r: float(r.get("total_volume_usd") or 0), reverse=True)
        prof.counterparties = [
            (_first_label(r.get("counterparty_address_label"))
             or r.get("counterparty_address") or "")[:80]
            for r in rows_sorted[:5]
        ]
        # Funding-source hypothesis: top counterparty by volume_in_usd (pure inbound).
        inbound_sorted = sorted(
            [r for r in rows if float(r.get("volume_in_usd") or 0) > 0],
            key=lambda r: float(r.get("volume_in_usd") or 0),
            reverse=True,
        )
        if inbound_sorted:
            top = inbound_sorted[0]
            label = _first_label(top.get("counterparty_address_label"))
            prof.funding_source = label
            prof.funding_address = top.get("counterparty_address")
            prof.funding_amount_usd = float(top.get("volume_in_usd") or 0)

    return prof
