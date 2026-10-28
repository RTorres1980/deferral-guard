"""Load data/sample into Oracle Autonomous Database and run PKG_409A_RULES.

    pip install oracledb
    export DG_DB_USER=dg DG_DB_PASSWORD=... DG_DB_DSN="<TLS connect string from the ADB console>"
    python scripts/load_to_adb.py --run-rules

Uses python-oracledb thin mode, so no Instant Client or wallet is needed when
the database allows TLS (one-way) connections.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = [
    ("plans.csv", "dg_plans"),
    ("participants.csv", "dg_participants"),
    ("deferral_elections.csv", "dg_deferral_elections"),
    ("subsequent_elections.csv", "dg_subsequent_elections"),
    ("distribution_requests.csv", "dg_distribution_requests"),
]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def convert(value: str):
    if value == "":
        return None
    if DATE_RE.match(value):
        return date.fromisoformat(value)
    return value


def main() -> None:
    import oracledb

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "data" / "sample"))
    parser.add_argument("--run-rules", action="store_true")
    args = parser.parse_args()

    conn = oracledb.connect(user=os.environ["DG_DB_USER"],
                            password=os.environ["DG_DB_PASSWORD"],
                            dsn=os.environ["DG_DB_DSN"])
    with conn, conn.cursor() as cur:
        for filename, table in reversed(TABLES):
            cur.execute(f"DELETE FROM {table}")
        for filename, table in TABLES:
            with (Path(args.data) / filename).open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                cols = reader.fieldnames
                binds = ", ".join(f":{i + 1}" for i in range(len(cols)))
                rows = [[convert(r[c]) for c in cols] for r in reader]
            cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({binds})", rows)
            print(f"{table}: {len(rows)} rows")
        conn.commit()

        if args.run_rules:
            run_id = cur.callfunc("pkg_409a_rules.run_all", oracledb.NUMBER)
            cur.execute("SELECT severity, COUNT(*) FROM dg_compliance_findings "
                        "WHERE run_id = :1 GROUP BY severity ORDER BY severity", [run_id])
            print(f"run {int(run_id)}:", dict(cur.fetchall()))


if __name__ == "__main__":
    main()
