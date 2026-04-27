# Secrets

All secrets live in GitHub Actions Secrets (`Settings → Secrets and variables → Actions`). Never commit keys.

| Secret | Purpose | Where to get it |
|---|---|---|
| `TRM_API_KEY` | Address screening via `api.trmlabs.com/public/v1/screening/addresses` | TRM dashboard |
| `ARKHAM_API_KEY` | Entity attribution | Arkham dashboard |
| `ALLIUM_API_KEY` | Tempo MPP tx + spender data | Allium dashboard (VCA contract) |
| `AGENTCASH_WALLET_PRIVATE_KEY` | Paying for Nansen Profiler calls via agentcash | Funded Base wallet with USDC — **dedicated CI wallet, not your personal one**. The workflow derives the address automatically and writes `~/.agentcash/wallet.json` at job start. Fund with ~$20 USDC on Base for multi-month buffer (~$0.07/wallet × 10 wallets × 50 weeks ≈ $35). |
| `RESEND_API_KEY` | Sending the weekly email summary via Resend | Resend dashboard → API Keys |

## Set them via CLI

```bash
gh secret set TRM_API_KEY         --body "…"
gh secret set ARKHAM_API_KEY      --body "…"
gh secret set ALLIUM_API_KEY      --body "…"
gh secret set AGENTCASH_WALLET_PRIVATE_KEY --body "…"
gh secret set RESEND_API_KEY      --body "…"
```

## Email delivery

Resend account is on sandbox (no verified sender domain). Sandbox only delivers to the account-owner address. The weekly email is sent to `rocklobster233@gmail.com`, then forwarded by a Gmail filter to `timrc23@gmail.com` and `tconard@visa.com`.

**Gmail filter setup** (once, in rocklobster233@gmail.com):
1. Settings → Filters and Blocked Addresses → Create a new filter.
2. From: `onboarding@resend.dev`. Subject: `[Compliance]`.
3. Forward to: `timrc23@gmail.com` and `tconard@visa.com` (each must first be added under "Forwarding and POP/IMAP" → "Add a forwarding address" and confirmed).

To send directly to multiple recipients later, verify a domain at resend.com/domains, change `SENDER` and the recipient list in `pipeline/email_report.py`, and remove the Gmail filter.

## Local dev

Copy `.env.example` to `.env` and fill in. `.env` is gitignored.

## Rotation

If a key ever appears in a chat transcript, commit log, or file, rotate it immediately at the provider dashboard.
