"""Load plan records from CSV (local/CI) into the domain model.

The CSV headers match the Oracle column names, so the same files load into
Autonomous Database with ``scripts/load_to_adb.py`` or Data Load in Database
Actions.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .models import (
    CompType,
    DeferralElection,
    DistributionRequest,
    Participant,
    Plan,
    SubsequentElection,
    Trigger,
)


def _d(v: str) -> date | None:
    return date.fromisoformat(v) if v else None


def _b(v: str) -> bool:
    return v.strip().upper() in {"Y", "YES", "TRUE", "1"}


def _f(v: str) -> float | None:
    return float(v) if v else None


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


@dataclass
class Dataset:
    plans: list[Plan]
    participants: list[Participant]
    elections: list[DeferralElection]
    subsequent: list[SubsequentElection]
    distributions: list[DistributionRequest]


def load_dataset(folder: str | Path) -> Dataset:
    f = Path(folder)
    plans = [
        Plan(r["PLAN_ID"], r["SPONSOR"], _b(r["IS_PUBLIC_COMPANY"]),
             _b(r["ALLOWS_UNFORESEEABLE_EMERGENCY"]), _b(r["ALLOWS_CHANGE_IN_CONTROL"]),
             _b(r["ALLOWS_DE_MINIMIS_CASHOUT"]))
        for r in _rows(f / "plans.csv")
    ]
    participants = [
        Participant(r["PARTICIPANT_ID"], r["PLAN_ID"], r["FULL_NAME"],
                    _b(r["IS_SPECIFIED_EMPLOYEE"]), _d(r["ELIGIBILITY_DATE"]),
                    _d(r["SEPARATION_DATE"]))
        for r in _rows(f / "participants.csv")
    ]
    elections = [
        DeferralElection(r["ELECTION_ID"], r["PARTICIPANT_ID"], int(r["PLAN_YEAR"]),
                         CompType(r["COMP_TYPE"]), _d(r["ELECTION_DATE"]),
                         _b(r["IS_INITIAL_ELIGIBILITY"]), _d(r["PERF_PERIOD_START"]),
                         _d(r["PERF_PERIOD_END"]))
        for r in _rows(f / "deferral_elections.csv")
    ]
    subsequent = [
        SubsequentElection(r["ELECTION_ID"], r["PARTICIPANT_ID"], _d(r["ELECTION_DATE"]),
                           _d(r["ORIGINAL_PAYMENT_DATE"]), _d(r["NEW_PAYMENT_DATE"]))
        for r in _rows(f / "subsequent_elections.csv")
    ]
    distributions = [
        DistributionRequest(r["REQUEST_ID"], r["PARTICIPANT_ID"], Trigger(r["TRIGGER_EVENT"]),
                            _d(r["REQUEST_DATE"]), _d(r["PAYMENT_DATE"]), float(r["AMOUNT"]),
                            float(r["ACCOUNT_BALANCE"]), _d(r["SCHEDULED_DATE"]),
                            _f(r["EMERGENCY_NEED_AMOUNT"]),
                            _b(r["TERMINATES_ENTIRE_INTEREST"]))
        for r in _rows(f / "distribution_requests.csv")
    ]
    return Dataset(plans, participants, elections, subsequent, distributions)
