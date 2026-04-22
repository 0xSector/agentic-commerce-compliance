# Agentic Commerce Compliance

Weekly compliance monitoring for the top buyers of people-search / identity APIs across agentic commerce rails.

- **Chains**: Base (x402) + Tempo (MPP)
- **Sources**: x402scan (Base), Allium (Tempo MPP), Nansen (wallet profile, via agentcash), TRM (sanctions/address screening), Arkham (entity attribution)
- **Cadence**: Weekly, Monday 08:00 CT via GitHub Actions
- **Output**: Static site served by GitHub Pages

## What it does

Each week:

1. Collect last week's transactions for people/identity-tagged endpoints on StableEnrich, StableSocial, StableEmail (x402) and equivalent merchants on MPP.
2. Aggregate unique buyer wallets across all qualifying endpoints and rank by total USD spend.
3. Take the top 20. For each: pull Nansen profile (funding, balance, counterparties), TRM screening (sanctions/mixer exposure), Arkham entity attribution.
4. Apply the risk rubric → LOW / MEDIUM / HIGH tier with narrative.
5. Render per-wallet reports + overview index. Commit `docs/` so GitHub Pages redeploys.

## Architecture

```
pipeline/
  run.py                orchestrator — wires the stages
  sources/
    x402scan.py         Base — weekly tx + merchant/resource stats
    mppscan.py          Tempo — Allium primary, mppscan RSC scrape fallback
    nansen.py           Wallet profile via agentcash x402 micropayments
    trm.py              Sanctions + address screening
    arkham.py           Entity attribution
  tag.py                people/identity endpoint classifier
  aggregate.py          dedupe + rank top 20 buyers
  enrich.py             fan-out enrichment per top-20 wallet
  rubric.py             risk tier from facts (LOW/MEDIUM/HIGH)
  render.py             Jinja2 → docs/index.html + docs/reports/*.html
config/
  endpoints.yml         merchant allowlist + path keyword filter
  rubric.yml            risk rubric thresholds
```

## Running locally

```bash
# one-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# set secrets (see SECRETS.md)
cp .env.example .env
# edit .env

# run the pipeline — writes to ./docs/
python -m pipeline.run
```

## Scheduled runs

`.github/workflows/weekly.yml` runs Monday at 13:00 UTC (08:00 CT), executes the pipeline, and commits the `docs/` output back to `main`. GitHub Pages serves from `docs/` on the `main` branch.

## Scope & framing

Research/narrative, not a formal compliance screening. Onchain data only. Attribution hypotheses are explicit and always distinguish fact from inference.

## Status

**Slice 1**: scaffolding + x402scan collector + classifier + top-N aggregator + rendering skeleton + workflow. MPP + wallet enrichment stubbed.

**Slice 2**: Allium for Tempo, Nansen/TRM/Arkham enrichment, rubric, narrative, real reports.
