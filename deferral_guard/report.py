"""Render findings as CSV and a self-contained HTML exception report."""
from __future__ import annotations

import csv
import html
from collections import Counter
from datetime import date
from pathlib import Path

from .models import Finding, Severity

_AREA = {"ELECT": "Initial elections", "REDEF": "Re-deferrals", "DIST": "Distributions"}


def write_csv(findings: list[Finding], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(findings[0].to_row()))
        writer.writeheader()
        for f in findings:
            writer.writerow(f.to_row())


def write_html(findings: list[Finding], names: dict[str, str], path: Path,
               explanations: dict[int, str] | None = None) -> None:
    explanations = explanations or {}
    sev = Counter(f.severity for f in findings)
    by_area = Counter((_AREA[f.rule_code.split("-")[0]], f.severity) for f in findings)
    exceptions = [(i, f) for i, f in enumerate(findings) if f.severity is not Severity.PASS]
    exceptions.sort(key=lambda x: (x[1].severity is not Severity.FAIL, x[1].rule_code))

    area_rows = "".join(
        f"<tr><td>{a}</td><td>{by_area[(a, Severity.FAIL)]}</td>"
        f"<td>{by_area[(a, Severity.WARN)]}</td><td>{by_area[(a, Severity.PASS)]}</td></tr>"
        for a in _AREA.values()
    )
    exc_rows = "".join(
        f"<tr><td><span class='pill {f.severity.value.lower()}'>{f.severity.value}</span></td>"
        f"<td class='mono'>{f.rule_code}</td><td class='mono'>{f.subject_id}</td>"
        f"<td>{html.escape(names.get(f.participant_id, f.participant_id))}</td>"
        f"<td>{html.escape(f.message)}"
        + (f"<div class='ai'>{html.escape(explanations[i])}</div>" if i in explanations else "")
        + f"</td><td class='cite'>{html.escape(f.citation)}</td></tr>"
        for i, f in exceptions
    )

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeferralGuard Exception Report</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --ink:#1c2430; --muted:#5d6b7c; --line:#e3e7ec;
        --fail:#b42318; --fail-bg:#fde8e7; --warn:#9a6700; --warn-bg:#fff4d6;
        --pass:#1a7f37; --pass-bg:#e6f4ea; --accent:#c74634; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#11151a; --card:#1a2028; --ink:#e7ecf2; --muted:#9aa7b6; --line:#2b333d;
          --fail:#ff8a80; --fail-bg:#3a1d1b; --warn:#f2c661; --warn-bg:#352b12;
          --pass:#7ee2a0; --pass-bg:#14301f; }} }}
body {{ margin:0; background:var(--bg); color:var(--ink);
       font:15px/1.5 -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 48px; }}
header {{ border-left:4px solid var(--accent); padding-left:14px; margin-bottom:20px; }}
h1 {{ margin:0; font-size:24px; }} h2 {{ font-size:17px; margin:28px 0 10px; }}
.sub {{ color:var(--muted); margin-top:4px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }}
.card b {{ display:block; font-size:28px; }} .card span {{ color:var(--muted); font-size:13px; }}
.wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; min-width:640px; }}
th, td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
.mono {{ font-family:ui-monospace, Menlo, monospace; font-size:13px; white-space:nowrap; }}
.cite {{ color:var(--muted); font-size:13px; white-space:nowrap; }}
.pill {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:99px; }}
.fail {{ color:var(--fail); background:var(--fail-bg); }}
.warn {{ color:var(--warn); background:var(--warn-bg); }}
.ai {{ margin-top:6px; font-size:13px; color:var(--muted); border-left:2px solid var(--line); padding-left:8px; }}
footer {{ color:var(--muted); font-size:12px; margin-top:24px; }}
</style></head><body><main>
<header><h1>DeferralGuard 409A Exception Report</h1>
<div class="sub">Run date {date.today().isoformat()} &middot; {len(findings)} rule checks</div></header>
<div class="cards">
 <div class="card"><b style="color:var(--fail)">{sev[Severity.FAIL]}</b><span>Failures</span></div>
 <div class="card"><b style="color:var(--warn)">{sev[Severity.WARN]}</b><span>Warnings for review</span></div>
 <div class="card"><b style="color:var(--pass)">{sev[Severity.PASS]}</b><span>Checks passed</span></div>
</div>
<h2>By area</h2>
<div class="wrap"><table><tr><th>Area</th><th>Fail</th><th>Warn</th><th>Pass</th></tr>{area_rows}</table></div>
<h2>Exception queue</h2>
<div class="wrap"><table><tr><th>Severity</th><th>Rule</th><th>Item</th><th>Participant</th>
<th>Finding</th><th>Citation</th></tr>{exc_rows}</table></div>
<footer>Screening output for operations review. Not legal advice; plan document and counsel govern.
Sample data is fictional.</footer>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
