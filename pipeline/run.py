# @purpose: Orchestrator. Reads config, pulls x402 + MPP buyer spend, aggregates
# the top N, enriches, assesses risk, builds narrative, renders the site.

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pipeline.aggregate import AggregatedBuyer, aggregate
from pipeline.attribution import Attribution, attribute, discover_endpoints
from pipeline.email_report import send_weekly
from pipeline.enrich import enrich_all
from pipeline.narrative import build as build_narrative
from pipeline.render import RenderRow, render_site
from pipeline.rubric import assess
from pipeline.sources import allium, x402scan
from pipeline.sources.mppscan import MppBuyerSpend

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "endpoints.yml"

WINDOW_DAYS = 7
TOP_N = 10


def _load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def _collect_x402(cfg: dict, days: int, price_lists: dict[str, list]) -> list[x402scan.BuyerSpend]:
    """Collect buyer spend per x402 origin.

    `all: true` origins pass through unfiltered — every endpoint is in scope.

    Origins with `path_keywords` use real path filtering: discover endpoints +
    prices via agentcash, pick the endpoints whose path matches any keyword,
    then only count on-chain transfers whose amount equals a qualifying price.
    Shared prices between qualifying and non-qualifying endpoints are included
    (false-positive leaning — compliance prefers over-inclusion).
    """
    out: list[x402scan.BuyerSpend] = []
    for entry in cfg.get("x402") or []:
        origin = entry["origin"]
        url = origin if origin.startswith("http") else f"https://{origin}"

        if entry.get("all"):
            print(f"[x402] pulling {origin} (all endpoints) …", file=sys.stderr)
            _, buyers = x402scan.buyer_spend_for_origin(origin, days=days)
        else:
            keywords = [k.lower() for k in (entry.get("path_keywords") or [])]
            if not keywords:
                print(f"[x402] skipping {origin} — no allowlist and no keywords", file=sys.stderr)
                continue
            endpoints = price_lists.get(origin)
            if endpoints is None:
                endpoints = discover_endpoints(url)
                price_lists[origin] = endpoints
            qualifying = [e for e in endpoints if any(k in e.path.lower() for k in keywords)]
            if not qualifying:
                print(f"[x402] {origin}: no endpoints matched path_keywords, skipping", file=sys.stderr)
                continue
            allowed_prices = {e.price_usd for e in qualifying}
            print(
                f"[x402] pulling {origin} (filtered: {len(qualifying)}/{len(endpoints)} endpoints, "
                f"{len(allowed_prices)} distinct prices) …",
                file=sys.stderr,
            )
            _, buyers = x402scan.buyer_spend_for_origin(origin, days=days, allowed_prices=allowed_prices)

        print(f"[x402] {origin}: {len(buyers)} unique buyers", file=sys.stderr)
        out.extend(buyers)
    return out


def _collect_mpp(cfg: dict, days: int) -> list[MppBuyerSpend]:
    hashes = [e["server_hash"] for e in (cfg.get("mpp") or [])]
    if not hashes:
        return []
    if not os.environ.get("ALLIUM_API_KEY"):
        print("[mpp] ALLIUM_API_KEY not set — skipping MPP (Tempo) collection", file=sys.stderr)
        return []
    try:
        buyers = allium.buyer_spend_for_servers(hashes, days=days)
    except Exception as ex:
        print(f"[mpp] Allium failed: {ex}", file=sys.stderr)
        return []
    print(f"[mpp] {len(buyers)} buyers across {len(hashes)} server(s)", file=sys.stderr)
    return buyers


def _discover_price_lists(origins: list[str]) -> dict[str, list]:
    """Run agentcash discover once per origin — cached for the run."""
    out: dict[str, list] = {}
    for o in origins:
        url = o if o.startswith("http") else f"https://{o}"
        try:
            endpoints = discover_endpoints(url)
        except Exception as ex:
            print(f"[discover] {o} failed: {ex}", file=sys.stderr)
            endpoints = []
        print(f"[discover] {o}: {len(endpoints)} endpoints with price", file=sys.stderr)
        out[o] = endpoints
    return out


def _attrib_for_buyer(buyer: AggregatedBuyer, price_lists: dict[str, list]) -> dict[str, list[Attribution]]:
    by_origin: dict[str, list[Attribution]] = {}
    for origin, amounts in buyer.amounts_by_origin.items():
        endpoints = price_lists.get(origin) or []
        if endpoints:
            by_origin[origin] = attribute(amounts, endpoints)
    return by_origin


def main() -> int:
    load_dotenv()
    cfg = _load_config()

    now = dt.datetime.now(dt.timezone.utc)
    window_end = now.date().isoformat()
    window_start = (now - dt.timedelta(days=WINDOW_DAYS)).date().isoformat()
    run_date = now.strftime("%Y-%m-%d %H:%M UTC")

    # Discover price lists up-front — needed for (a) path-keyword filtering in
    # `_collect_x402` and (b) per-buyer attribution at render time.
    all_origins = sorted({(e["origin"]) for e in (cfg.get("x402") or [])})
    price_lists = _discover_price_lists(all_origins)

    x402_spend = _collect_x402(cfg, days=WINDOW_DAYS, price_lists=price_lists)
    mpp_spend = _collect_mpp(cfg, days=WINDOW_DAYS)
    top = aggregate(x402_spend, mpp_spend, top_n=TOP_N)
    print(f"[aggregate] top {len(top)} buyers across {len(x402_spend)} x402 + {len(mpp_spend)} MPP rows", file=sys.stderr)

    enriched = enrich_all(top)
    rows: list[RenderRow] = []
    for idx, e in enumerate(enriched, start=1):
        attrs = _attrib_for_buyer(e.buyer, price_lists)
        risk = assess(e)
        narrative = build_narrative(e, rank=idx, attrs_by_origin=attrs, tier=risk.tier)
        rows.append(RenderRow(
            buyer=e.buyer, nansen=e.nansen, trm=e.trm, arkham=e.arkham,
            risk=risk, narrative=narrative, attributions=attrs,
        ))

    render_site(rows, window_start=window_start, window_end=window_end, run_date=run_date)
    print(f"[render] wrote docs/ with {len(rows)} wallet reports", file=sys.stderr)

    if os.environ.get("SKIP_EMAIL") == "1":
        print("[email] SKIP_EMAIL=1 — not sending", file=sys.stderr)
    else:
        send_weekly(rows, window_start=window_start, window_end=window_end, run_date=run_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
