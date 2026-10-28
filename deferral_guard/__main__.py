"""DeferralGuard command line.

    python -m deferral_guard run --data data/sample --out reports
    python -m deferral_guard run --data data/sample --out reports --explain
    python -m deferral_guard classify "I retired on 2026-06-30, please pay out my account"
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .genai import classify_intake, default_provider, explain_finding
from .loader import load_dataset
from .models import Severity
from .report import write_csv, write_html
from .rules import evaluate


def cmd_run(args: argparse.Namespace) -> int:
    ds = load_dataset(args.data)
    findings = evaluate(ds.plans, ds.participants, ds.elections, ds.subsequent, ds.distributions)
    out = Path(args.out)
    write_csv(findings, out / "findings.csv")

    explanations = {}
    if args.explain:
        provider = default_provider()
        for i, f in enumerate(findings):
            if f.severity is Severity.FAIL:
                explanations[i] = explain_finding(f, provider=provider)

    names = {p.participant_id: p.full_name for p in ds.participants}
    write_html(findings, names, out / "exception_report.html", explanations)

    counts = Counter(f.severity.value for f in findings)
    print(f"{len(findings)} checks | FAIL {counts['FAIL']} | WARN {counts['WARN']} | PASS {counts['PASS']}")
    for f in findings:
        if f.severity is Severity.FAIL:
            print(f"  {f.rule_code:<10}{f.subject_id:<8}{f.message}")
    print(f"wrote {out / 'findings.csv'} and {out / 'exception_report.html'}")
    return 1 if args.fail_on_exceptions and counts["FAIL"] else 0


def cmd_classify(args: argparse.Namespace) -> int:
    draft = classify_intake(args.text)
    payload = asdict(draft)
    payload["trigger_event"] = draft.trigger_event.value
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deferral_guard",
                                     description="Section 409A NQDC compliance screening")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="evaluate elections and distributions")
    run.add_argument("--data", default="data/sample")
    run.add_argument("--out", default="reports")
    run.add_argument("--explain", action="store_true",
                     help="add plain-language explanations via OCI Generative AI")
    run.add_argument("--fail-on-exceptions", action="store_true",
                     help="exit 1 when any FAIL finding exists (for scheduled jobs)")
    run.set_defaults(func=cmd_run)

    cls = sub.add_parser("classify", help="classify a participant request with Gen AI")
    cls.add_argument("text")
    cls.set_defaults(func=cmd_classify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
