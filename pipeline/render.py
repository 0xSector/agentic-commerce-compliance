# @purpose: Renders the static site — index page + one report page per
# enriched buyer. Output goes to ./docs/ (served by GitHub Pages).

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline.attribution import Attribution
from pipeline.narrative import Narrative
from pipeline.rubric import RiskAssessment

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = Path(__file__).resolve().parent / "templates"
SITE = ROOT / "docs"


@dataclass
class RenderRow:
    buyer: object        # AggregatedBuyer
    nansen: object
    trm: object
    arkham: object
    risk: RiskAssessment
    narrative: Narrative | None = None
    attributions: dict[str, list[Attribution]] = field(default_factory=dict)


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )


def render_site(rows: list[RenderRow], window_start: str, window_end: str, run_date: str) -> None:
    env = _env()
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "reports").mkdir(parents=True, exist_ok=True)

    idx = env.get_template("index.html.j2").render(
        buyers=rows, window_start=window_start, window_end=window_end, run_date=run_date,
    )
    (SITE / "index.html").write_text(idx)

    docs = env.get_template("docs.html.j2").render()
    (SITE / "docs.html").write_text(docs)

    rpt_tpl = env.get_template("report.html.j2")
    for row in rows:
        html = rpt_tpl.render(row=row, run_date=run_date)
        (SITE / "reports" / f"{row.buyer.address}.html").write_text(html)

    (SITE / ".nojekyll").write_text("")
