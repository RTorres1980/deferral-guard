"""Domain model for a nonqualified deferred compensation (NQDC) plan.

These dataclasses mirror the tables in ``db/01_schema.sql`` one-to-one, so the
same records can be evaluated in Python (CI, local demo) or inside Oracle
Autonomous Database (``PKG_409A_RULES``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Trigger(str, Enum):
    """Payment events a participant or administrator can request."""

    SEPARATION = "SEPARATION"
    DISABILITY = "DISABILITY"
    DEATH = "DEATH"
    FIXED_DATE = "FIXED_DATE"
    CHANGE_IN_CONTROL = "CHANGE_IN_CONTROL"
    UNFORESEEABLE_EMERGENCY = "UNFORESEEABLE_EMERGENCY"
    DE_MINIMIS = "DE_MINIMIS"
    IN_SERVICE = "IN_SERVICE"  # not a 409A permissible event; used to catch bad requests


#: The six permissible payment events under Treas. Reg. 1.409A-3(a).
PERMISSIBLE_EVENTS = frozenset(
    {
        Trigger.SEPARATION,
        Trigger.DISABILITY,
        Trigger.DEATH,
        Trigger.FIXED_DATE,
        Trigger.CHANGE_IN_CONTROL,
        Trigger.UNFORESEEABLE_EMERGENCY,
    }
)


class CompType(str, Enum):
    SALARY = "SALARY"
    BONUS = "BONUS"
    PERFORMANCE_BONUS = "PERFORMANCE_BONUS"


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Plan:
    plan_id: str
    sponsor: str
    is_public_company: bool
    allows_unforeseeable_emergency: bool = True
    allows_change_in_control: bool = True
    allows_de_minimis_cashout: bool = True


@dataclass(frozen=True)
class Participant:
    participant_id: str
    plan_id: str
    full_name: str
    is_specified_employee: bool = False
    eligibility_date: date | None = None
    separation_date: date | None = None


@dataclass(frozen=True)
class DeferralElection:
    election_id: str
    participant_id: str
    plan_year: int
    comp_type: CompType
    election_date: date
    is_initial_eligibility: bool = False
    performance_period_start: date | None = None
    performance_period_end: date | None = None


@dataclass(frozen=True)
class SubsequentElection:
    """A re-deferral: participant pushes an existing payment date further out."""

    election_id: str
    participant_id: str
    election_date: date
    original_payment_date: date
    new_payment_date: date


@dataclass(frozen=True)
class DistributionRequest:
    request_id: str
    participant_id: str
    trigger: Trigger
    request_date: date
    payment_date: date
    amount: float
    account_balance: float
    scheduled_date: date | None = None  # for FIXED_DATE elections
    emergency_need_amount: float | None = None  # documented need incl. taxes
    terminates_entire_interest: bool = False


@dataclass(frozen=True)
class Finding:
    rule_code: str
    severity: Severity
    subject_id: str
    participant_id: str
    message: str
    citation: str
    details: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "rule_code": self.rule_code,
            "severity": self.severity.value,
            "subject_id": self.subject_id,
            "participant_id": self.participant_id,
            "message": self.message,
            "citation": self.citation,
        }
