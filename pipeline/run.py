# @purpose: Orchestrator. Reads config, pulls x402 + MPP buyer spend, aggregates
# the top N, enriches, assesses risk, and renders the static site. Designed to
# run unattended in GitHub Actions once a week.

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pipeline.aggregate import aggregate
from pipeline.enrich import enrich_all
from pipeline.render import RenderRow, render_site
from pipeline.rubric import assess
from pipeline.sources import mppscan, x402scan

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "endpoints.yml"

WINDOW_DAYS = 7
TOP_N = 20


def _load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def _collect_x402(cfg: dict, days: int) -> list[x402scan.BuyerSpend]:
    out: list[x402scan.BuyerSpend] = []
    for entry in cfg.get("x402") or []:
        origin = entry["origin"]
        # slice 1: path_keywords filter not yet applied (Base txs don't carry path).
        # stableenrich.dev has all: true; stablesocial/email with keywords await slice 2.
        if not entry.get("all"):
            print(f"[x402] skipping {origin} — path_keywords filter is slice 2", file=sys.stderr)
            continue
        print(f"[x402] pulling {origin} …", file=sys.stderr)
        _, buyers = x402scan.buyer_spend_for_origin(origin, days=days)
        print(f"[x402] {origin}: {len(buyers)} unique buyers", file=sys.stderr)
        out.extend(buyers)
    return out


def _collect_mpp(cfg: dict, days: int) -> list[mppscan.MppBuyerSpend]:
    hashes = [e["server_hash"] for e in (cfg.get("mpp") or [])]
    buyers = mppscan.buyer_spend_for_servers(hashes, days=days)
    print(f"[mpp] {len(buyers)} buyers (stub; Allium lands in slice 2)", file=sys.stderr)
    return buyers


def main() -> int:
    load_dotenv()
    cfg = _load_config()

    now = dt.datetime.now(dt.timezone.utc)
    window_end = now.date().isoformat()
    window_start = (now - dt.timedelta(days=WINDOW_DAYS)).date().isoformat()
    run_date = now.strftime("%Y-%m-%d %H:%M UTC")

    x402_spend = _collect_x402(cfg, days=WINDOW_DAYS)
    mpp_spend = _collect_mpp(cfg, days=WINDOW_DAYS)
    top = aggregate(x402_spend, mpp_spend, top_n=TOP_N)
    print(f"[aggregate] top {len(top)} buyers across {len(x402_spend)} x402 + {len(mpp_spend)} MPP rows", file=sys.stderr)

    enriched = enrich_all(top)
    rows = [
        RenderRow(buyer=e.buyer, nansen=e.nansen, trm=e.trm, arkham=e.arkham, risk=assess(e))
        for e in enriched
    ]

    render_site(rows, window_start=window_start, window_end=window_end, run_date=run_date)
    print(f"[render] wrote site/ with {len(rows)} wallet reports", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
