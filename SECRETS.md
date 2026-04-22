# Secrets

All secrets live in GitHub Actions Secrets (`Settings → Secrets and variables → Actions`). Never commit keys.

| Secret | Purpose | Where to get it |
|---|---|---|
| `TRM_API_KEY` | Address screening via `api.trmlabs.com/public/v1/screening/addresses` | TRM dashboard |
| `ARKHAM_API_KEY` | Entity attribution | Arkham dashboard |
| `ALLIUM_API_KEY` | Tempo MPP tx + spender data | Allium dashboard (VCA contract) |
| `AGENTCASH_WALLET_PRIVATE_KEY` | Paying for Nansen Profiler calls via agentcash | Funded Base wallet with USDC — **dedicated CI wallet, not your personal one**. The workflow derives the address automatically and writes `~/.agentcash/wallet.json` at job start. Fund with ~$20 USDC on Base for multi-month buffer (~$0.07/wallet × 20 wallets × 50 weeks ≈ $70). |

## Set them via CLI

```bash
gh secret set TRM_API_KEY         --body "…"
gh secret set ARKHAM_API_KEY      --body "…"
gh secret set ALLIUM_API_KEY      --body "…"
gh secret set AGENTCASH_WALLET_PRIVATE_KEY --body "…"
```

## Local dev

Copy `.env.example` to `.env` and fill in. `.env` is gitignored.

## Rotation

If a key ever appears in a chat transcript, commit log, or file, rotate it immediately at the provider dashboard.
