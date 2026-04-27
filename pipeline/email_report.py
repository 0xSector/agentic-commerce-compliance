# @purpose: Builds and sends the weekly compliance email summary via Resend.
# Flagged (MEDIUM/HIGH) wallets lead, full top-N table follows. Always sends,
# even on all-clear weeks, so silence isn't ambiguous.

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import escape

from pipeline.render import RenderRow

RESEND_URL = "https://api.resend.com/emails"
SITE_BASE = "https://0xsector.github.io/agentic-commerce-compliance"

# Resend account is on sandbox (no verified domain). Sandbox only delivers to
# the account-owner address. Tim forwards from this inbox to timrc23@ and
# tconard@visa.com via Gmail filters. Switch to per-recipient `to:` once a
# domain is verified at resend.com/domains.
SANDBOX_RECIPIENT = "rocklobster233@gmail.com"
SENDER = "compliance <onboarding@resend.dev>"


@dataclass
class EmailSummary:
    subject: str
    html: str
    text: str


def _short(addr: str) -> str:
    return f"{addr[:6]}…{addr[-4:]}" if addr and len(addr) > 12 else addr


def _report_url(addr: str) -> str:
    return f"{SITE_BASE}/reports/{addr}.html"


def _flag_label(flag: str) -> str:
    return {
        "trm_sanctions_match": "TRM sanctions match",
        "trm_mixer_direct_exposure": "TRM mixer (direct)",
        "trm_mixer_indirect_exposure": "TRM mixer (indirect)",
        "trm_category_high_risk": "TRM high-risk category",
        "funding_source_unknown": "Funding source unknown",
        "counterparty_count_under_3": "Counterparty count <3",
    }.get(flag, flag)


def _origins_str(row: RenderRow) -> str:
    parts = list(row.buyer.origins) + [f"mpp:{h[:8]}" for h in row.buyer.mpp_servers]
    return ", ".join(parts) if parts else "—"


def build_summary(
    rows: list[RenderRow], window_start: str, window_end: str, run_date: str,
) -> EmailSummary:
    flagged = [(i, r) for i, r in enumerate(rows, start=1) if r.risk.tier != "LOW"]
    high = [r for _, r in flagged if r.risk.tier == "HIGH"]
    medium = [r for _, r in flagged if r.risk.tier == "MEDIUM"]
    total_usd = sum(r.buyer.total_usd for r in rows)

    flag_count = len(flagged)
    if flag_count == 0:
        subject = f"[Compliance] {window_end} — all clear ({len(rows)} wallets)"
    else:
        subject = (
            f"[Compliance] {window_end} — {flag_count} flagged "
            f"({len(high)}H / {len(medium)}M of {len(rows)})"
        )

    text = _build_text(rows, flagged, high, medium, total_usd, window_start, window_end, run_date)
    html = _build_html(rows, flagged, high, medium, total_usd, window_start, window_end, run_date)
    return EmailSummary(subject=subject, html=html, text=text)


def _build_text(rows, flagged, high, medium, total_usd, window_start, window_end, run_date):
    lines: list[str] = []
    lines.append(f"Agentic Commerce Compliance — weekly snapshot")
    lines.append(f"Window: {window_start} → {window_end}  (run {run_date})")
    lines.append("")
    lines.append(
        f"Top {len(rows)} buyers · ${total_usd:,.2f} total · "
        f"{len(high)} HIGH · {len(medium)} MEDIUM · {len(rows) - len(flagged)} LOW"
    )
    lines.append(f"Site: {SITE_BASE}/")
    lines.append("")

    if flagged:
        lines.append("=" * 60)
        lines.append("FLAGGED WALLETS (non-low risk)")
        lines.append("=" * 60)
        for rank, r in flagged:
            b = r.buyer
            lines.append("")
            lines.append(f"#{rank}  [{r.risk.tier}]  {b.address}")
            lines.append(f"  Spend (7d):   ${b.total_usd:,.2f}  ({b.total_tx} tx)")
            lines.append(f"  Origins:      {_origins_str(r)}")
            if r.risk.flags:
                lines.append(f"  Flags:        {', '.join(_flag_label(f) for f in r.risk.flags)}")
            if r.nansen.funding_source:
                lines.append(f"  Funding:      {r.nansen.funding_source}")
            if r.trm.categories:
                lines.append(f"  TRM cats:     {', '.join(r.trm.categories[:5])}")
            lines.append(f"  Report:       {_report_url(b.address)}")
    else:
        lines.append("No non-low-risk wallets this week.")

    lines.append("")
    lines.append("=" * 60)
    lines.append(f"FULL TOP {len(rows)}")
    lines.append("=" * 60)
    lines.append(f"{'#':>3}  {'tier':<7}  {'address':<44}  {'spend':>12}  {'tx':>4}  origin")
    for i, r in enumerate(rows, start=1):
        b = r.buyer
        lines.append(
            f"{i:>3}  {r.risk.tier:<7}  {b.address:<44}  "
            f"${b.total_usd:>10,.2f}  {b.total_tx:>4}  {_origins_str(r)[:40]}"
        )
    lines.append("")
    lines.append(f"Methodology: {SITE_BASE}/docs.html")
    return "\n".join(lines)


def _build_html(rows, flagged, high, medium, total_usd, window_start, window_end, run_date):
    def tier_color(t: str) -> str:
        return {"HIGH": "#b91c1c", "MEDIUM": "#b45309", "LOW": "#6b7280"}.get(t, "#6b7280")

    parts: list[str] = []
    parts.append('<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:780px;color:#111;font-size:14px;line-height:1.5">')
    parts.append(f'<h2 style="margin:0 0 4px">Agentic Commerce Compliance</h2>')
    parts.append(f'<div style="color:#6b7280;font-size:13px">Window {escape(window_start)} → {escape(window_end)} · run {escape(run_date)}</div>')
    parts.append('<div style="margin:16px 0;padding:12px 14px;background:#f9fafb;border-radius:6px;font-size:14px">')
    parts.append(
        f'Top {len(rows)} buyers · <b>${total_usd:,.2f}</b> total · '
        f'<span style="color:{tier_color("HIGH")}"><b>{len(high)} HIGH</b></span> · '
        f'<span style="color:{tier_color("MEDIUM")}"><b>{len(medium)} MEDIUM</b></span> · '
        f'{len(rows) - len(flagged)} LOW'
    )
    parts.append(f'<br><a href="{SITE_BASE}/" style="color:#2563eb">View full site →</a>')
    parts.append('</div>')

    if flagged:
        parts.append('<h3 style="margin:24px 0 8px">Flagged wallets (non-low risk)</h3>')
        for rank, r in flagged:
            b = r.buyer
            parts.append(
                f'<div style="margin:0 0 14px;padding:12px 14px;border-left:4px solid {tier_color(r.risk.tier)};background:#fafafa;border-radius:4px">'
            )
            parts.append(
                f'<div style="font-size:13px;color:#6b7280">#{rank} · '
                f'<span style="color:{tier_color(r.risk.tier)};font-weight:600">{escape(r.risk.tier)}</span></div>'
            )
            parts.append(
                f'<div style="font-family:ui-monospace,monospace;font-size:13px;margin:2px 0 6px">'
                f'<a href="{_report_url(b.address)}" style="color:#111;text-decoration:none;border-bottom:1px dotted #999">{escape(b.address)}</a></div>'
            )
            parts.append('<table style="font-size:13px;border-collapse:collapse"><tbody>')
            parts.append(f'<tr><td style="color:#6b7280;padding:1px 12px 1px 0">Spend (7d)</td><td>${b.total_usd:,.2f} ({b.total_tx} tx)</td></tr>')
            parts.append(f'<tr><td style="color:#6b7280;padding:1px 12px 1px 0">Origins</td><td>{escape(_origins_str(r))}</td></tr>')
            if r.risk.flags:
                flag_html = ", ".join(escape(_flag_label(f)) for f in r.risk.flags)
                parts.append(f'<tr><td style="color:#6b7280;padding:1px 12px 1px 0">Flags</td><td>{flag_html}</td></tr>')
            if r.nansen.funding_source:
                parts.append(f'<tr><td style="color:#6b7280;padding:1px 12px 1px 0">Funding</td><td>{escape(r.nansen.funding_source)}</td></tr>')
            if r.trm.categories:
                parts.append(f'<tr><td style="color:#6b7280;padding:1px 12px 1px 0">TRM cats</td><td>{escape(", ".join(r.trm.categories[:5]))}</td></tr>')
            parts.append('</tbody></table>')
            parts.append(f'<div style="margin-top:6px"><a href="{_report_url(b.address)}" style="color:#2563eb;font-size:13px">Full report →</a></div>')
            parts.append('</div>')
    else:
        parts.append('<div style="margin:16px 0;padding:14px;background:#ecfdf5;border-left:4px solid #059669;border-radius:4px"><b>All clear.</b> No non-low-risk wallets this week.</div>')

    parts.append(f'<h3 style="margin:24px 0 8px">Full top {len(rows)}</h3>')
    parts.append('<table style="border-collapse:collapse;font-size:13px;width:100%">')
    parts.append('<thead><tr style="text-align:left;border-bottom:1px solid #e5e7eb">')
    parts.append('<th style="padding:6px 8px">#</th><th style="padding:6px 8px">Tier</th><th style="padding:6px 8px">Address</th><th style="padding:6px 8px;text-align:right">Spend</th><th style="padding:6px 8px;text-align:right">Tx</th><th style="padding:6px 8px">Origins</th>')
    parts.append('</tr></thead><tbody>')
    for i, r in enumerate(rows, start=1):
        b = r.buyer
        parts.append('<tr style="border-bottom:1px solid #f3f4f6">')
        parts.append(f'<td style="padding:6px 8px">{i}</td>')
        parts.append(f'<td style="padding:6px 8px;color:{tier_color(r.risk.tier)};font-weight:600">{escape(r.risk.tier)}</td>')
        parts.append(
            f'<td style="padding:6px 8px;font-family:ui-monospace,monospace">'
            f'<a href="{_report_url(b.address)}" style="color:#2563eb;text-decoration:none">{escape(_short(b.address))}</a></td>'
        )
        parts.append(f'<td style="padding:6px 8px;text-align:right">${b.total_usd:,.2f}</td>')
        parts.append(f'<td style="padding:6px 8px;text-align:right">{b.total_tx}</td>')
        parts.append(f'<td style="padding:6px 8px;color:#6b7280">{escape(_origins_str(r)[:40])}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table>')
    parts.append(f'<div style="margin-top:18px;color:#6b7280;font-size:12px">Methodology: <a href="{SITE_BASE}/docs.html" style="color:#6b7280">{SITE_BASE}/docs.html</a></div>')
    parts.append('</div>')
    return "".join(parts)


def send(summary: EmailSummary) -> bool:
    """Returns True on 200/202, False on any failure. Does not raise."""
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if not api_key:
        print("[email] RESEND_API_KEY not set — skipping send", file=sys.stderr)
        return False

    payload = {
        "from": SENDER,
        "to": [SANDBOX_RECIPIENT],
        "subject": summary.subject,
        "html": summary.html,
        "text": summary.text,
    }
    req = urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            print(f"[email] sent ({resp.status}): {body[:200]}", file=sys.stderr)
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as ex:
        print(f"[email] HTTP {ex.code}: {(ex.read() or b'').decode()[:300]}", file=sys.stderr)
        return False
    except Exception as ex:
        print(f"[email] failed: {ex}", file=sys.stderr)
        return False


def send_weekly(rows: list[RenderRow], window_start: str, window_end: str, run_date: str) -> bool:
    summary = build_summary(rows, window_start, window_end, run_date)
    return send(summary)
