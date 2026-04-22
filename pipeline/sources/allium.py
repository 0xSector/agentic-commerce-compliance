# @purpose: Allium client + Tempo MPP buyer query. Replaces the mppscan stub.
# Pattern ported from tenet-boi/hex/cells/02_data.py (POST create -> POST run).
# Excludes the session-model escrow that dominates raw MPP volume.

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from pipeline.sources.mppscan import MppBuyerSpend

ALLIUM_BASE = "https://api.allium.so/api/v1/explorer/queries"

# MPP event on Tempo — same invariants as tenet-boi's existing production SQL.
MPP_CONTRACT = "0x20c000000000000000000000b9537d11c60e8b50"
MPP_TOPIC = "0x57bc7354aa85aed339e000bccffabbc529466af35f0772c8f8ee1145927de7f0"
# Session-model escrow we intentionally exclude (pending proper handling).
EXCLUDED_ESCROW_TOPIC = "0x00000000000000000000000003acdc3e7bb74f1c5d29b1118f920e1b5fc62fd7"

AMOUNT_EXPR = (
    "CAST(TO_NUMBER(LPAD(LTRIM(SUBSTRING(data, 3), '0'), 32, '0'), "
    "'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX') / 1000000.0 AS DECIMAL(28, 6))"
)


def _headers() -> dict:
    key = (os.environ.get("ALLIUM_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ALLIUM_API_KEY not set — required for MPP (Tempo) data")
    return {"X-API-KEY": key, "Content-Type": "application/json"}


def _run_sql(sql: str, title: str) -> list[dict]:
    create = requests.post(
        ALLIUM_BASE,
        headers=_headers(),
        json={"title": title, "config": {"sql": sql, "limit": 10000}},
        timeout=60,
    )
    create.raise_for_status()
    qid = create.json()["query_id"]
    run = requests.post(f"{ALLIUM_BASE}/{qid}/run", headers=_headers(), json={}, timeout=300)
    run.raise_for_status()
    return run.json().get("data") or []


def buyer_spend_last_n_days(days: int = 7) -> list[MppBuyerSpend]:
    """All buyers + per-server spend on MPP (Tempo) in the last `days` window.

    The `to_address` in the MPP event is the server hash. We return one row per
    (buyer, server) pair; the aggregator dedupes buyers across servers.

    People/identity filtering at the MPP level is slice 2.5 — for now this
    returns ALL MPP buyers, which the caller can filter against a server
    allowlist. The simplest cut for now: include every MPP buyer and tag the
    server, then filter in aggregate.py against the config allowlist.
    """
    sql = f"""
WITH mpp AS (
  SELECT
    LOWER('0x' || RIGHT(topic1, 40)) AS buyer,
    LOWER(RIGHT(topic2, 64)) AS server_hash,
    {AMOUNT_EXPR} AS usdc_amount
  FROM tempo.raw.logs
  WHERE address = '{MPP_CONTRACT}'
    AND topic0 = '{MPP_TOPIC}'
    AND block_timestamp >= DATEADD(day, -{days}, CURRENT_TIMESTAMP())
    AND topic1 != topic2
    AND topic1 != '{EXCLUDED_ESCROW_TOPIC}'
    AND topic2 != '{EXCLUDED_ESCROW_TOPIC}'
)
SELECT
  buyer,
  server_hash,
  COUNT(*) AS tx_count,
  ROUND(SUM(usdc_amount), 4) AS total_usd
FROM mpp
GROUP BY buyer, server_hash
ORDER BY total_usd DESC
"""
    rows = _run_sql(sql, "[PRODUCTION] Agentic Commerce Compliance — MPP weekly buyers")
    return [
        MppBuyerSpend(
            address=r["buyer"],
            server_hash=r["server_hash"],
            tx_count=int(r["tx_count"]),
            total_usd=float(r["total_usd"]),
        )
        for r in rows
    ]


def buyer_spend_for_servers(server_hashes: list[str], days: int = 7) -> list[MppBuyerSpend]:
    """Scoped variant — only return MPP buyers on specific server hashes."""
    all_rows = buyer_spend_last_n_days(days=days)
    allow = {h.lower() for h in server_hashes}
    # server_hash in SQL is raw topic2 (no 0x padding); normalize for comparison
    return [r for r in all_rows if r.server_hash.lower().lstrip("0").zfill(64) in
            {h.lower().lstrip("0x").zfill(64) for h in server_hashes} or r.server_hash in allow]
