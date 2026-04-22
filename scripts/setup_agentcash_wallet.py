#!/usr/bin/env python3
# @purpose: Write ~/.agentcash/wallet.json from the AGENTCASH_WALLET_PRIVATE_KEY
# env var so agentcash CLI can find a wallet in CI. Runs once at workflow start.

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from eth_account import Account


def main() -> int:
    pk = (os.environ.get("AGENTCASH_WALLET_PRIVATE_KEY") or "").strip()
    if not pk:
        print("AGENTCASH_WALLET_PRIVATE_KEY not set — skipping wallet bootstrap", file=sys.stderr)
        return 0
    if not pk.startswith("0x"):
        pk = "0x" + pk

    acct = Account.from_key(pk)
    wallet = {
        "privateKey": pk,
        "address": acct.address,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    home = Path.home() / ".agentcash"
    home.mkdir(parents=True, exist_ok=True)
    (home / "wallet.json").write_text(json.dumps(wallet, indent=2))
    # Minimal state file so agentcash doesn't re-run onboarding.
    (home / "state.json").write_text(json.dumps({"onboarded": True}))
    print(f"Wrote ~/.agentcash/wallet.json for address {acct.address}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
