# @purpose: x402scan + Base RPC adapter. Resolves origin -> recipient wallet(s),
# pulls USDC transfers on Base for a given window, returns per-buyer spend.
# Based on the x402-endpoint-volume skill — key invariants encoded here so the
# pipeline is reproducible without the skill file.

from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Iterable

import requests

X402SCAN_BAZAAR = "https://www.x402scan.com/api/trpc/public.sellers.bazaar.list"
BASE_RPC = "https://mainnet.base.org"
USDC_BASE = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BLOCKS_PER_DAY = 43200  # Base ~2s blocks
GETLOGS_CHUNK = 8000    # public RPC cap is 10k, leave headroom


@dataclass
class SellerBundle:
    origins: list[str]
    recipients: list[str]      # Base addresses, lowercase 0x…
    solana_owners: list[str]
    tx_count: int
    total_amount_usd: float
    unique_buyers: int
    chains: list[str]


@dataclass
class Transfer:
    sender: str        # the buyer (EIP-3009 authorization.from = topics[1])
    recipient: str
    amount_usd: float
    block: int
    tx_hash: str


@dataclass
class BuyerSpend:
    address: str
    origin: str
    tx_count: int = 0
    total_usd: float = 0.0
    tx_amounts: list[float] = field(default_factory=list)  # per-transfer USD (for endpoint attribution)


def _trpc_bazaar(timeframe_days: int) -> list[dict]:
    """Call x402scan's tRPC bazaar list. Returns raw items."""
    payload = {"0": {"json": {"timeframe": timeframe_days, "pagination": {"page_size": 250}}}}
    url = f"{X402SCAN_BAZAAR}?batch=1&input={urllib.parse.quote(json.dumps(payload))}"
    r = requests.get(url, headers={"trpc-accept": "application/jsonl"}, timeout=30)
    r.raise_for_status()
    lines = r.text.splitlines()
    # jsonl: 4th line (index 3) carries the data payload
    data = json.loads(lines[3])["json"][2][0][0]
    return data["items"]


def _origin_urls(raw_origins) -> list[str]:
    """Extract origin URLs from x402scan's mixed dict/string shape."""
    out: list[str] = []
    for o in raw_origins or []:
        if isinstance(o, dict):
            url = o.get("origin") or o.get("url") or ""
        else:
            url = str(o)
        if url:
            out.append(url)
    return out


def _split_recipients(raw_recipients) -> tuple[list[str], list[str]]:
    """x402scan mixes Base (0x…) and Solana (base58) in the same `recipients` list."""
    base, sol = [], []
    for r in raw_recipients or []:
        if isinstance(r, str) and r.startswith("0x") and len(r) == 42:
            base.append(r.lower())
        elif isinstance(r, str):
            sol.append(r)
    return base, sol


def resolve_bundle(origin: str, timeframe_days: int = 7) -> SellerBundle | None:
    """Find the seller bundle (recipient wallet + bundled origins) that owns `origin`."""
    items = _trpc_bazaar(timeframe_days)
    for it in items:
        origin_urls = _origin_urls(it.get("origins"))
        if not any(origin in u for u in origin_urls):
            continue
        base_recipients, sol_owners = _split_recipients(it.get("recipients"))
        return SellerBundle(
            origins=origin_urls,
            recipients=base_recipients,
            solana_owners=sol_owners,
            tx_count=int(it.get("tx_count") or 0),
            total_amount_usd=float(it.get("total_amount") or 0) / 1_000_000,
            unique_buyers=int(it.get("unique_buyers") or 0),
            chains=it.get("chains") or [],
        )
    return None


def _latest_block() -> int:
    r = requests.post(
        BASE_RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
        timeout=15,
    )
    r.raise_for_status()
    return int(r.json()["result"], 16)


def _get_logs(from_block: int, to_block: int, recipient: str) -> list[dict]:
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_getLogs",
        "params": [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": USDC_BASE,
            "topics": [
                TRANSFER_TOPIC,
                None,
                "0x" + recipient[2:].lower().zfill(64),
            ],
        }],
    }
    # retry on transient 429 / 5xx
    for attempt in range(4):
        try:
            r = requests.post(BASE_RPC, json=payload, timeout=30)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(1 + attempt)
                continue
            r.raise_for_status()
            return r.json().get("result", []) or []
        except requests.RequestException:
            time.sleep(1 + attempt)
    raise RuntimeError(f"eth_getLogs failed for recipient {recipient} {from_block}->{to_block}")


def pull_base_transfers(recipient: str, days: int) -> list[Transfer]:
    """USDC transfers into `recipient` on Base over the last `days`."""
    latest = _latest_block()
    start = latest - BLOCKS_PER_DAY * days
    transfers: list[Transfer] = []
    b = start
    while b <= latest:
        to = min(b + GETLOGS_CHUNK - 1, latest)
        logs = _get_logs(b, to, recipient)
        for log in logs:
            topics = log["topics"]
            sender = "0x" + topics[1][-40:]
            amount = int(log["data"], 16) / 1_000_000
            transfers.append(Transfer(
                sender=sender.lower(),
                recipient=recipient.lower(),
                amount_usd=amount,
                block=int(log["blockNumber"], 16),
                tx_hash=log["transactionHash"],
            ))
        b = to + 1
    return transfers


def buyer_spend_for_origin(origin: str, days: int = 7) -> tuple[SellerBundle | None, list[BuyerSpend]]:
    """High-level: given an origin, return (bundle, per-buyer totals for the last `days`).

    Solana side is NOT covered here — slice 1 is Base only. Solana comes in slice 2.
    """
    bundle = resolve_bundle(origin, timeframe_days=max(days, 7))
    if not bundle or not bundle.recipients:
        return bundle, []

    totals: dict[str, BuyerSpend] = {}
    for recipient in bundle.recipients:
        for t in pull_base_transfers(recipient, days=days):
            b = totals.setdefault(t.sender, BuyerSpend(address=t.sender, origin=origin))
            b.tx_count += 1
            b.total_usd += t.amount_usd
            b.tx_amounts.append(t.amount_usd)

    ranked = sorted(totals.values(), key=lambda b: b.total_usd, reverse=True)
    return bundle, ranked
