from datetime import date
from pathlib import Path

import pytest

from deferral_guard.loader import load_dataset
from deferral_guard.models import (
    CompType,
    DeferralElection,
    DistributionRequest,
    Participant,
    Plan,
    Severity,
    SubsequentElection,
    Trigger,
)
from deferral_guard.rules import (
    add_months,
    check_distribution,
    check_initial_election,
    check_subsequent_election,
    evaluate,
    payment_window_end,
)

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"

PUBLIC = Plan("PL", "Public Co", is_public_company=True)
PRIVATE_NO_UE = Plan("PV", "Private Co", is_public_company=False,
                     allows_unforeseeable_emergency=False)


def worst(findings):
    order = {Severity.PASS: 0, Severity.WARN: 1, Severity.FAIL: 2}
    return max(findings, key=lambda f: order[f.severity])


def codes(findings, severity=Severity.FAIL):
    return {f.rule_code for f in findings if f.severity is severity}


# --- date helpers ---------------------------------------------------------

@pytest.mark.parametrize("d, m, expected", [
    (date(2026, 8, 31), 6, date(2027, 2, 28)),
    (date(2026, 6, 30), 6, date(2026, 12, 30)),
    (date(2027, 1, 15), -12, date(2026, 1, 15)),
    (date(2024, 2, 29), 12, date(2025, 2, 28)),
])
def test_add_months(d, m, expected):
    assert add_months(d, m) == expected


def test_payment_window_uses_later_of_year_end_or_third_month():
    assert payment_window_end(date(2026, 3, 1)) == date(2026, 12, 31)
    assert payment_window_end(date(2026, 12, 1)) == date(2027, 3, 15)


# --- initial elections ----------------------------------------------------

def p(**kw):
    base = dict(participant_id="P1", plan_id="PL", full_name="Test")
    base.update(kw)
    return Participant(**base)


def test_salary_election_must_precede_plan_year():
    ok = DeferralElection("E1", "P1", 2026, CompType.SALARY, date(2025, 12, 31))
    late = DeferralElection("E2", "P1", 2026, CompType.SALARY, date(2026, 1, 1))
    assert worst(check_initial_election(ok, p())).severity is Severity.PASS
    assert codes(check_initial_election(late, p())) == {"ELECT-001"}


def test_newly_eligible_30_day_window():
    part = p(eligibility_date=date(2026, 2, 10))
    inside = DeferralElection("E1", "P1", 2026, CompType.SALARY, date(2026, 3, 12), True)
    outside = DeferralElection("E2", "P1", 2026, CompType.SALARY, date(2026, 3, 13), True)
    assert worst(check_initial_election(inside, part)).severity is Severity.PASS
    assert codes(check_initial_election(outside, part)) == {"ELECT-003"}


def test_performance_bonus_six_month_rule():
    on_time = DeferralElection("E1", "P1", 2026, CompType.PERFORMANCE_BONUS,
                               date(2026, 6, 30), False, date(2026, 1, 1), date(2026, 12, 31))
    late = DeferralElection("E2", "P1", 2026, CompType.PERFORMANCE_BONUS,
                            date(2026, 7, 1), False, date(2026, 1, 1), date(2026, 12, 31))
    short = DeferralElection("E3", "P1", 2026, CompType.PERFORMANCE_BONUS,
                             date(2026, 2, 1), False, date(2026, 4, 1), date(2026, 12, 31))
    assert worst(check_initial_election(on_time, p())).severity is Severity.PASS
    assert codes(check_initial_election(late, p())) == {"ELECT-002"}
    assert codes(check_initial_election(short, p())) == {"ELECT-002"}


# --- subsequent elections -------------------------------------------------

def test_redeferral_twelve_month_and_five_year_rules():
    good = SubsequentElection("S1", "P1", date(2026, 1, 15), date(2027, 1, 15), date(2032, 1, 15))
    bad = SubsequentElection("S2", "P1", date(2026, 6, 1), date(2027, 3, 1), date(2030, 3, 1))
    assert codes(check_subsequent_election(good)) == set()
    assert codes(check_subsequent_election(bad)) == {"REDEF-001", "REDEF-002"}


# --- distributions --------------------------------------------------------

def req(trigger, payment, amount=10_000, balance=50_000, **kw):
    return DistributionRequest("D1", "P1", trigger, date(2026, 1, 1), payment, amount, balance, **kw)


def test_in_service_withdrawal_is_not_permissible():
    assert codes(check_distribution(req(Trigger.IN_SERVICE, date(2026, 2, 1)), p(), PUBLIC)) == {"DIST-001"}


def test_specified_employee_six_month_delay():
    part = p(is_specified_employee=True, separation_date=date(2026, 6, 30))
    early = req(Trigger.SEPARATION, date(2026, 12, 29))
    on_time = req(Trigger.SEPARATION, date(2026, 12, 30))
    assert codes(check_distribution(early, part, PUBLIC)) == {"DIST-002"}
    assert codes(check_distribution(on_time, part, PUBLIC)) == set()


def test_six_month_delay_does_not_apply_to_private_company():
    part = p(is_specified_employee=True, separation_date=date(2026, 6, 30), plan_id="PV")
    plan = Plan("PV", "Private", is_public_company=False)
    assert codes(check_distribution(req(Trigger.SEPARATION, date(2026, 7, 15)), part, plan)) == set()


def test_separation_requires_recorded_separation():
    assert codes(check_distribution(req(Trigger.SEPARATION, date(2026, 7, 1)), p(), PUBLIC)) == {"DIST-001"}


def test_fixed_date_acceleration_and_late_payment():
    early = req(Trigger.FIXED_DATE, date(2026, 12, 1), scheduled_date=date(2027, 1, 15))
    late = req(Trigger.FIXED_DATE, date(2028, 1, 2), scheduled_date=date(2027, 1, 15))
    assert codes(check_distribution(early, p(), PUBLIC)) == {"DIST-003"}
    assert codes(check_distribution(late, p(), PUBLIC), Severity.WARN) == {"DIST-007"}


def test_unforeseeable_emergency_limited_to_need():
    over = req(Trigger.UNFORESEEABLE_EMERGENCY, date(2026, 2, 1), amount=60_000,
               balance=200_000, emergency_need_amount=48_750)
    within = req(Trigger.UNFORESEEABLE_EMERGENCY, date(2026, 2, 1), amount=40_000,
                 balance=200_000, emergency_need_amount=48_750)
    excess = [f for f in check_distribution(over, p(), PUBLIC) if f.rule_code == "DIST-004"][0]
    assert excess.severity is Severity.FAIL and excess.details["excess"] == 11_250
    assert codes(check_distribution(within, p(), PUBLIC), Severity.WARN) == {"DIST-004"}
    assert codes(check_distribution(within, p(), PRIVATE_NO_UE)) == {"DIST-004"}


def test_de_minimis_uses_402g_limit_and_full_termination():
    ok = req(Trigger.DE_MINIMIS, date(2026, 10, 20), amount=24_500, balance=24_500,
             terminates_entire_interest=True)
    over = req(Trigger.DE_MINIMIS, date(2026, 10, 20), amount=24_501, balance=24_501,
               terminates_entire_interest=True)
    partial = req(Trigger.DE_MINIMIS, date(2026, 10, 20), amount=5_000, balance=20_000)
    assert codes(check_distribution(ok, p(), PUBLIC)) == set()
    assert codes(check_distribution(over, p(), PUBLIC)) == {"DIST-005"}
    assert codes(check_distribution(partial, p(), PUBLIC)) == {"DIST-005"}


def test_amount_cannot_exceed_balance():
    r = req(Trigger.DEATH, date(2026, 3, 1), amount=60_000, balance=50_000)
    assert codes(check_distribution(r, p(), PUBLIC)) == {"DIST-008"}


# --- sample dataset reconciles to expected exceptions ---------------------

def test_sample_dataset_expected_exceptions():
    ds = load_dataset(SAMPLE)
    findings = evaluate(ds.plans, ds.participants, ds.elections, ds.subsequent, ds.distributions)
    failed = {(f.subject_id, f.rule_code) for f in findings if f.severity is Severity.FAIL}
    assert failed == {
        ("E-2002", "ELECT-001"),
        ("E-2005", "ELECT-002"),
        ("E-2006", "ELECT-003"),
        ("S-3002", "REDEF-001"),
        ("S-3002", "REDEF-002"),
        ("S-3003", "REDEF-001"),
        ("D-4001", "DIST-002"),
        ("D-4003", "DIST-004"),
        ("D-4004", "DIST-001"),
        ("D-4006", "DIST-004"),
        ("D-4008", "DIST-003"),
        ("D-4009", "DIST-005"),
    }
