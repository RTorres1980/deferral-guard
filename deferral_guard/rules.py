"""Section 409A compliance rules for NQDC elections and distributions.

Every rule returns zero or more :class:`Finding` objects. Rule codes and logic
are kept identical to ``db/03_pkg_409a_rules.sql`` so results reconcile
between the Python engine and the in-database PL/SQL package.

This is an operational screening tool, not legal advice. Final determinations
belong with plan counsel and the plan document.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Iterable

from .models import (
    PERMISSIBLE_EVENTS,
    CompType,
    DeferralElection,
    DistributionRequest,
    Finding,
    Participant,
    Plan,
    Severity,
    SubsequentElection,
    Trigger,
)

#: IRC 402(g)(1)(B) elective deferral limit, used as the de minimis cash-out
#: ceiling under 1.409A-3(j)(4)(v). Update annually from the IRS COLA notice.
LIMIT_402G = {2023: 22_500, 2024: 23_000, 2025: 23_500, 2026: 24_500}


def add_months(d: date, months: int) -> date:
    """Calendar-month arithmetic that clamps to the target month's last day.

    Unlike Oracle's native ADD_MONTHS (which maps month-end to month-end), this
    keeps the day number, so June 30 + 6 months is Dec 30. PKG_409A_RULES uses
    the same logic in its ``add_mo`` helper so both engines reconcile.
    """
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def add_years(d: date, years: int) -> date:
    return add_months(d, 12 * years)


def payment_window_end(designated: date) -> date:
    """Latest date a payment is still treated as made on time (1.409A-3(d)).

    Later of: Dec 31 of the designated date's year, or the 15th day of the
    third calendar month after the designated date.
    """
    year_end = date(designated.year, 12, 31)
    third_month = add_months(designated.replace(day=1), 3)
    return max(year_end, third_month.replace(day=15))


def _finding(code, severity, subject, participant, message, citation, **details):
    return Finding(code, severity, subject, participant, message, citation, details)


# ---------------------------------------------------------------------------
# Deferral elections
# ---------------------------------------------------------------------------

def check_initial_election(e: DeferralElection, p: Participant) -> list[Finding]:
    """ELECT-001 / ELECT-002 / ELECT-003: timing of initial deferral elections."""
    if e.comp_type is CompType.PERFORMANCE_BONUS:
        return _check_performance_bonus(e)

    if e.is_initial_eligibility:
        cite = "Treas. Reg. 1.409A-2(a)(7)"
        if p.eligibility_date is None:
            return [_finding("ELECT-003", Severity.FAIL, e.election_id, e.participant_id,
                             "Newly-eligible election has no eligibility date on file.", cite)]
        deadline = p.eligibility_date + timedelta(days=30)
        if e.election_date > deadline:
            return [_finding("ELECT-003", Severity.FAIL, e.election_id, e.participant_id,
                             f"Newly-eligible election made {e.election_date}, after the "
                             f"30-day window that closed {deadline}.", cite,
                             deadline=deadline.isoformat())]
        return [_finding("ELECT-003", Severity.PASS, e.election_id, e.participant_id,
                         "Newly-eligible election within 30 days; applies only to "
                         "compensation earned after the election.", cite)]

    cite = "Treas. Reg. 1.409A-2(a)(3)"
    deadline = date(e.plan_year - 1, 12, 31)
    if e.election_date > deadline:
        return [_finding("ELECT-001", Severity.FAIL, e.election_id, e.participant_id,
                         f"{e.comp_type.value.title()} election for {e.plan_year} made "
                         f"{e.election_date}; must be made by {deadline}.", cite,
                         deadline=deadline.isoformat())]
    return [_finding("ELECT-001", Severity.PASS, e.election_id, e.participant_id,
                     f"Election made before the {e.plan_year} service year.", cite)]


def _check_performance_bonus(e: DeferralElection) -> list[Finding]:
    cite = "Treas. Reg. 1.409A-2(a)(8)"
    start, end = e.performance_period_start, e.performance_period_end
    if start is None or end is None:
        return [_finding("ELECT-002", Severity.FAIL, e.election_id, e.participant_id,
                         "Performance-based election is missing its performance period.", cite)]
    if add_months(start, 12) > end + timedelta(days=1):
        return [_finding("ELECT-002", Severity.FAIL, e.election_id, e.participant_id,
                         "Performance period is shorter than 12 months, so the "
                         "6-month election rule is unavailable.", cite)]
    deadline = add_months(end, -6)
    if e.election_date > deadline:
        return [_finding("ELECT-002", Severity.FAIL, e.election_id, e.participant_id,
                         f"Performance bonus election made {e.election_date}; must be "
                         f"at least 6 months before period end ({deadline}).", cite,
                         deadline=deadline.isoformat())]
    return [_finding("ELECT-002", Severity.PASS, e.election_id, e.participant_id,
                     "Performance bonus election made 6+ months before period end. "
                     "Confirm the amount was not yet readily ascertainable.", cite)]


def check_subsequent_election(s: SubsequentElection) -> list[Finding]:
    """REDEF-001 / REDEF-002: the 12-month and 5-year re-deferral rules."""
    cite = "Treas. Reg. 1.409A-2(b)(1)"
    out: list[Finding] = []
    lead_deadline = add_months(s.original_payment_date, -12)
    if s.election_date > lead_deadline:
        out.append(_finding("REDEF-001", Severity.FAIL, s.election_id, s.participant_id,
                            f"Re-deferral made {s.election_date}; must be at least 12 months "
                            f"before the original payment date ({s.original_payment_date}).",
                            cite, deadline=lead_deadline.isoformat()))
    else:
        out.append(_finding("REDEF-001", Severity.PASS, s.election_id, s.participant_id,
                            "Re-deferral made 12+ months before original payment date.", cite))

    min_new = add_years(s.original_payment_date, 5)
    if s.new_payment_date < min_new:
        out.append(_finding("REDEF-002", Severity.FAIL, s.election_id, s.participant_id,
                            f"New payment date {s.new_payment_date} is less than 5 years after "
                            f"the original date; earliest allowed is {min_new}.",
                            cite, earliest=min_new.isoformat()))
    else:
        out.append(_finding("REDEF-002", Severity.PASS, s.election_id, s.participant_id,
                            "New payment date pushed out at least 5 years.", cite))
    return out


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

def check_distribution(r: DistributionRequest, p: Participant, plan: Plan) -> list[Finding]:
    """DIST-001 through DIST-007."""
    rid, pid = r.request_id, r.participant_id

    # DIST-001: permissible payment event. De minimis is an acceleration
    # exception, handled separately below.
    if r.trigger is not Trigger.DE_MINIMIS and r.trigger not in PERMISSIBLE_EVENTS:
        return [_finding("DIST-001", Severity.FAIL, rid, pid,
                         f"{r.trigger.value} is not a permissible 409A payment event; an "
                         "in-service withdrawal is an impermissible acceleration.",
                         "Treas. Reg. 1.409A-3(a)")]

    out: list[Finding] = []
    designated: date | None = None

    if r.trigger is Trigger.SEPARATION:
        designated = _check_separation(r, p, plan, out)
    elif r.trigger is Trigger.FIXED_DATE:
        designated = _check_fixed_date(r, out)
    elif r.trigger is Trigger.UNFORESEEABLE_EMERGENCY:
        _check_emergency(r, plan, out)
    elif r.trigger is Trigger.DE_MINIMIS:
        _check_de_minimis(r, plan, out)
    elif r.trigger is Trigger.CHANGE_IN_CONTROL and not plan.allows_change_in_control:
        out.append(_finding("DIST-006", Severity.FAIL, rid, pid,
                            "Plan document does not provide for payment on a change in control.",
                            "Treas. Reg. 1.409A-3(i)(5)"))

    if r.amount > r.account_balance:
        out.append(_finding("DIST-008", Severity.FAIL, rid, pid,
                            f"Requested ${r.amount:,.2f} exceeds the account balance of "
                            f"${r.account_balance:,.2f}.", "Plan recordkeeping control"))

    # DIST-007: payment timing grace window
    if designated is not None and r.payment_date > payment_window_end(designated):
        out.append(_finding("DIST-007", Severity.WARN, rid, pid,
                            f"Payment {r.payment_date} falls after the grace window ending "
                            f"{payment_window_end(designated)}; review for late payment.",
                            "Treas. Reg. 1.409A-3(d)"))

    if not any(f.severity is not Severity.PASS for f in out):
        out.append(_finding("DIST-000", Severity.PASS, rid, pid,
                            f"{r.trigger.value.replace('_', ' ').title()} distribution passes "
                            "all screens.", "Treas. Reg. 1.409A-3"))
    return out


def _check_separation(r, p, plan, out) -> date | None:
    rid, pid = r.request_id, r.participant_id
    if p.separation_date is None:
        out.append(_finding("DIST-001", Severity.FAIL, rid, pid,
                            "Separation payment requested but no separation from service is "
                            "recorded.", "Treas. Reg. 1.409A-1(h)"))
        return None
    if plan.is_public_company and p.is_specified_employee:
        earliest = add_months(p.separation_date, 6)
        if r.payment_date < earliest:
            out.append(_finding("DIST-002", Severity.FAIL, rid, pid,
                                f"Specified employee of a public company: payment {r.payment_date} "
                                f"is inside the six-month delay. Earliest date is {earliest}.",
                                "Treas. Reg. 1.409A-3(i)(2)", earliest=earliest.isoformat()))
        else:
            out.append(_finding("DIST-002", Severity.PASS, rid, pid,
                                "Six-month specified employee delay satisfied.",
                                "Treas. Reg. 1.409A-3(i)(2)"))
        return earliest
    return p.separation_date


def _check_fixed_date(r, out) -> date | None:
    rid, pid = r.request_id, r.participant_id
    if r.scheduled_date is None:
        out.append(_finding("DIST-003", Severity.FAIL, rid, pid,
                            "Fixed-date payment has no scheduled date on the election.",
                            "Treas. Reg. 1.409A-3(i)(1)"))
        return None
    if r.payment_date < r.scheduled_date:
        out.append(_finding("DIST-003", Severity.FAIL, rid, pid,
                            f"Payment {r.payment_date} is before the elected date "
                            f"{r.scheduled_date}: impermissible acceleration.",
                            "Treas. Reg. 1.409A-3(j)(1)"))
    return r.scheduled_date


def _check_emergency(r, plan, out) -> None:
    rid, pid = r.request_id, r.participant_id
    cite = "Treas. Reg. 1.409A-3(i)(3)"
    if not plan.allows_unforeseeable_emergency:
        out.append(_finding("DIST-004", Severity.FAIL, rid, pid,
                            "Plan document does not permit unforeseeable emergency payments.", cite))
        return
    if r.emergency_need_amount is None:
        out.append(_finding("DIST-004", Severity.FAIL, rid, pid,
                            "No documented financial need on file for the emergency request.", cite))
        return
    if r.amount > r.emergency_need_amount:
        out.append(_finding("DIST-004", Severity.FAIL, rid, pid,
                            f"Requested ${r.amount:,.2f} exceeds documented need of "
                            f"${r.emergency_need_amount:,.2f} (need may include taxes on the "
                            "distribution).", cite,
                            excess=round(r.amount - r.emergency_need_amount, 2)))
    else:
        out.append(_finding("DIST-004", Severity.WARN, rid, pid,
                            "Amount is within documented need. Confirm need cannot be relieved "
                            "by insurance, asset liquidation or stopping deferrals.", cite))


def _check_de_minimis(r, plan, out) -> None:
    rid, pid = r.request_id, r.participant_id
    cite = "Treas. Reg. 1.409A-3(j)(4)(v)"
    limit = LIMIT_402G.get(r.payment_date.year)
    if not plan.allows_de_minimis_cashout:
        out.append(_finding("DIST-005", Severity.FAIL, rid, pid,
                            "Plan document does not provide for a de minimis cash-out.", cite))
        return
    if limit is None:
        out.append(_finding("DIST-005", Severity.WARN, rid, pid,
                            f"No 402(g) limit loaded for {r.payment_date.year}; update "
                            "LIMIT_402G.", cite))
        return
    if r.account_balance > limit:
        out.append(_finding("DIST-005", Severity.FAIL, rid, pid,
                            f"Balance ${r.account_balance:,.2f} exceeds the "
                            f"{r.payment_date.year} 402(g) limit of ${limit:,}.", cite,
                            limit=limit))
    elif not r.terminates_entire_interest:
        out.append(_finding("DIST-005", Severity.FAIL, rid, pid,
                            "De minimis cash-out must terminate the participant's entire "
                            "interest in the plan (and aggregated plans).", cite))


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def evaluate(
    plans: Iterable[Plan],
    participants: Iterable[Participant],
    elections: Iterable[DeferralElection] = (),
    subsequent: Iterable[SubsequentElection] = (),
    distributions: Iterable[DistributionRequest] = (),
) -> list[Finding]:
    plan_by_id = {pl.plan_id: pl for pl in plans}
    part_by_id = {p.participant_id: p for p in participants}
    findings: list[Finding] = []
    for e in elections:
        findings += check_initial_election(e, part_by_id[e.participant_id])
    for s in subsequent:
        findings += check_subsequent_election(s)
    for r in distributions:
        p = part_by_id[r.participant_id]
        findings += check_distribution(r, p, plan_by_id[p.plan_id])
    return findings
