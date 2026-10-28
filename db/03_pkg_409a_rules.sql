--------------------------------------------------------------------------------
-- DeferralGuard | PKG_409A_RULES
-- In-database 409A screening engine. Rule codes and logic mirror
-- deferral_guard/rules.py; tests/test_rules.py documents expected outcomes.
--
--   DECLARE l_run NUMBER;
--   BEGIN l_run := pkg_409a_rules.run_all; DBMS_OUTPUT.PUT_LINE(l_run); END;
--
-- Screening tool only; final determinations rest with plan counsel.
--------------------------------------------------------------------------------

CREATE OR REPLACE PACKAGE pkg_409a_rules AUTHID DEFINER AS
    -- Day-preserving month arithmetic (Jun 30 + 6 = Dec 30), clamped to month end.
    FUNCTION add_mo (p_date IN DATE, p_months IN PLS_INTEGER) RETURN DATE DETERMINISTIC;

    -- Last date a payment counts as on time for a designated date (1.409A-3(d)).
    FUNCTION payment_window_end (p_designated IN DATE) RETURN DATE DETERMINISTIC;

    -- Evaluate every election and distribution; returns the new RUN_ID.
    FUNCTION run_all RETURN NUMBER;
END pkg_409a_rules;
/

CREATE OR REPLACE PACKAGE BODY pkg_409a_rules AS

    g_run_id NUMBER;
    g_count  PLS_INTEGER := 0;

    FUNCTION ymd (p_date IN DATE) RETURN VARCHAR2 IS
    BEGIN
        RETURN TO_CHAR(p_date, 'YYYY-MM-DD');
    END ymd;

    FUNCTION money (p_amt IN NUMBER) RETURN VARCHAR2 IS
    BEGIN
        RETURN TRIM(TO_CHAR(p_amt, 'FM$999,999,999,990.00'));
    END money;

    FUNCTION add_mo (p_date IN DATE, p_months IN PLS_INTEGER) RETURN DATE DETERMINISTIC IS
        l_first DATE := ADD_MONTHS(TRUNC(p_date, 'MM'), p_months);
    BEGIN
        RETURN LEAST(l_first + (EXTRACT(DAY FROM p_date) - 1), LAST_DAY(l_first));
    END add_mo;

    FUNCTION payment_window_end (p_designated IN DATE) RETURN DATE DETERMINISTIC IS
    BEGIN
        RETURN GREATEST(ADD_MONTHS(TRUNC(p_designated, 'YYYY'), 12) - 1,
                        ADD_MONTHS(TRUNC(p_designated, 'MM'), 3) + 14);
    END payment_window_end;

    PROCEDURE add_finding (
        p_rule        IN VARCHAR2,
        p_severity    IN VARCHAR2,
        p_subject     IN VARCHAR2,
        p_participant IN VARCHAR2,
        p_message     IN VARCHAR2
    ) IS
    BEGIN
        INSERT INTO dg_compliance_findings
            (run_id, rule_code, severity, subject_id, participant_id, message, citation, status)
        SELECT g_run_id, p_rule, p_severity, p_subject, p_participant, SUBSTR(p_message, 1, 1000),
               c.citation, CASE p_severity WHEN 'PASS' THEN 'RESOLVED' ELSE 'OPEN' END
          FROM dg_rule_catalog c
         WHERE c.rule_code = p_rule;
        g_count := g_count + 1;
    END add_finding;

    ---------------------------------------------------------------------------
    -- Initial deferral elections: ELECT-001 / 002 / 003
    ---------------------------------------------------------------------------
    PROCEDURE check_elections IS
        l_deadline DATE;
    BEGIN
        FOR e IN (SELECT de.*, p.eligibility_date
                    FROM dg_deferral_elections de
                    JOIN dg_participants p ON p.participant_id = de.participant_id)
        LOOP
            IF e.comp_type = 'PERFORMANCE_BONUS' THEN
                IF e.perf_period_start IS NULL OR e.perf_period_end IS NULL THEN
                    add_finding('ELECT-002', 'FAIL', e.election_id, e.participant_id,
                        'Performance-based election is missing its performance period.');
                ELSIF add_mo(e.perf_period_start, 12) > e.perf_period_end + 1 THEN
                    add_finding('ELECT-002', 'FAIL', e.election_id, e.participant_id,
                        'Performance period is shorter than 12 months, so the 6-month election rule is unavailable.');
                ELSE
                    l_deadline := add_mo(e.perf_period_end, -6);
                    IF e.election_date > l_deadline THEN
                        add_finding('ELECT-002', 'FAIL', e.election_id, e.participant_id,
                            'Performance bonus election made ' || ymd(e.election_date) ||
                            '; must be at least 6 months before period end (' || ymd(l_deadline) || ').');
                    ELSE
                        add_finding('ELECT-002', 'PASS', e.election_id, e.participant_id,
                            'Performance bonus election made 6+ months before period end.');
                    END IF;
                END IF;

            ELSIF e.is_initial_eligibility = 'Y' THEN
                IF e.eligibility_date IS NULL THEN
                    add_finding('ELECT-003', 'FAIL', e.election_id, e.participant_id,
                        'Newly-eligible election has no eligibility date on file.');
                ELSIF e.election_date > e.eligibility_date + 30 THEN
                    add_finding('ELECT-003', 'FAIL', e.election_id, e.participant_id,
                        'Newly-eligible election made ' || ymd(e.election_date) ||
                        ', after the 30-day window that closed ' || ymd(e.eligibility_date + 30) || '.');
                ELSE
                    add_finding('ELECT-003', 'PASS', e.election_id, e.participant_id,
                        'Newly-eligible election within 30 days; prospective compensation only.');
                END IF;

            ELSE
                l_deadline := TO_DATE(TO_CHAR(e.plan_year - 1) || '-12-31', 'YYYY-MM-DD');
                IF e.election_date > l_deadline THEN
                    add_finding('ELECT-001', 'FAIL', e.election_id, e.participant_id,
                        INITCAP(e.comp_type) || ' election for ' || e.plan_year || ' made ' ||
                        ymd(e.election_date) || '; must be made by ' || ymd(l_deadline) || '.');
                ELSE
                    add_finding('ELECT-001', 'PASS', e.election_id, e.participant_id,
                        'Election made before the ' || e.plan_year || ' service year.');
                END IF;
            END IF;
        END LOOP;
    END check_elections;

    ---------------------------------------------------------------------------
    -- Subsequent (re-deferral) elections: REDEF-001 / 002
    ---------------------------------------------------------------------------
    PROCEDURE check_subsequent IS
    BEGIN
        FOR s IN (SELECT * FROM dg_subsequent_elections) LOOP
            IF s.election_date > add_mo(s.original_payment_date, -12) THEN
                add_finding('REDEF-001', 'FAIL', s.election_id, s.participant_id,
                    'Re-deferral made ' || ymd(s.election_date) ||
                    '; must be at least 12 months before the original payment date (' ||
                    ymd(s.original_payment_date) || ').');
            ELSE
                add_finding('REDEF-001', 'PASS', s.election_id, s.participant_id,
                    'Re-deferral made 12+ months before original payment date.');
            END IF;

            IF s.new_payment_date < add_mo(s.original_payment_date, 60) THEN
                add_finding('REDEF-002', 'FAIL', s.election_id, s.participant_id,
                    'New payment date ' || ymd(s.new_payment_date) ||
                    ' is less than 5 years after the original; earliest allowed is ' ||
                    ymd(add_mo(s.original_payment_date, 60)) || '.');
            ELSE
                add_finding('REDEF-002', 'PASS', s.election_id, s.participant_id,
                    'New payment date pushed out at least 5 years.');
            END IF;
        END LOOP;
    END check_subsequent;

    ---------------------------------------------------------------------------
    -- Distributions: DIST-000 .. DIST-008
    ---------------------------------------------------------------------------
    PROCEDURE check_distributions IS
        l_designated DATE;
        l_issue      BOOLEAN;
        l_limit      dg_limit_402g.limit_amount%TYPE;

        PROCEDURE flag (p_rule VARCHAR2, p_sev VARCHAR2, p_req VARCHAR2, p_part VARCHAR2, p_msg VARCHAR2) IS
        BEGIN
            add_finding(p_rule, p_sev, p_req, p_part, p_msg);
            IF p_sev <> 'PASS' THEN
                l_issue := TRUE;
            END IF;
        END flag;
    BEGIN
        FOR r IN (SELECT d.*, p.is_specified_employee, p.separation_date,
                         pl.is_public_company, pl.allows_unforeseeable_emergency,
                         pl.allows_change_in_control, pl.allows_de_minimis_cashout
                    FROM dg_distribution_requests d
                    JOIN dg_participants p  ON p.participant_id = d.participant_id
                    JOIN dg_plans        pl ON pl.plan_id       = p.plan_id)
        LOOP
            l_designated := NULL;
            l_issue      := FALSE;

            IF r.trigger_event = 'IN_SERVICE' THEN
                flag('DIST-001', 'FAIL', r.request_id, r.participant_id,
                    'IN_SERVICE is not a permissible 409A payment event; an in-service withdrawal is an impermissible acceleration.');
                CONTINUE;
            END IF;

            CASE r.trigger_event
            WHEN 'SEPARATION' THEN
                IF r.separation_date IS NULL THEN
                    flag('DIST-001', 'FAIL', r.request_id, r.participant_id,
                        'Separation payment requested but no separation from service is recorded.');
                ELSIF r.is_public_company = 'Y' AND r.is_specified_employee = 'Y' THEN
                    l_designated := add_mo(r.separation_date, 6);
                    IF r.payment_date < l_designated THEN
                        flag('DIST-002', 'FAIL', r.request_id, r.participant_id,
                            'Specified employee of a public company: payment ' || ymd(r.payment_date) ||
                            ' is inside the six-month delay. Earliest date is ' || ymd(l_designated) || '.');
                    ELSE
                        flag('DIST-002', 'PASS', r.request_id, r.participant_id,
                            'Six-month specified employee delay satisfied.');
                    END IF;
                ELSE
                    l_designated := r.separation_date;
                END IF;

            WHEN 'FIXED_DATE' THEN
                IF r.scheduled_date IS NULL THEN
                    flag('DIST-003', 'FAIL', r.request_id, r.participant_id,
                        'Fixed-date payment has no scheduled date on the election.');
                ELSE
                    l_designated := r.scheduled_date;
                    IF r.payment_date < r.scheduled_date THEN
                        flag('DIST-003', 'FAIL', r.request_id, r.participant_id,
                            'Payment ' || ymd(r.payment_date) || ' is before the elected date ' ||
                            ymd(r.scheduled_date) || ': impermissible acceleration.');
                    END IF;
                END IF;

            WHEN 'UNFORESEEABLE_EMERGENCY' THEN
                IF r.allows_unforeseeable_emergency = 'N' THEN
                    flag('DIST-004', 'FAIL', r.request_id, r.participant_id,
                        'Plan document does not permit unforeseeable emergency payments.');
                ELSIF r.emergency_need_amount IS NULL THEN
                    flag('DIST-004', 'FAIL', r.request_id, r.participant_id,
                        'No documented financial need on file for the emergency request.');
                ELSIF r.amount > r.emergency_need_amount THEN
                    flag('DIST-004', 'FAIL', r.request_id, r.participant_id,
                        'Requested ' || money(r.amount) || ' exceeds documented need of ' ||
                        money(r.emergency_need_amount) || ' (need may include taxes on the distribution).');
                ELSE
                    flag('DIST-004', 'WARN', r.request_id, r.participant_id,
                        'Amount is within documented need. Confirm need cannot be relieved by insurance, asset liquidation or stopping deferrals.');
                END IF;

            WHEN 'DE_MINIMIS' THEN
                BEGIN
                    SELECT limit_amount INTO l_limit
                      FROM dg_limit_402g
                     WHERE limit_year = EXTRACT(YEAR FROM r.payment_date);
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN l_limit := NULL;
                END;

                IF r.allows_de_minimis_cashout = 'N' THEN
                    flag('DIST-005', 'FAIL', r.request_id, r.participant_id,
                        'Plan document does not provide for a de minimis cash-out.');
                ELSIF l_limit IS NULL THEN
                    flag('DIST-005', 'WARN', r.request_id, r.participant_id,
                        'No 402(g) limit loaded for ' || EXTRACT(YEAR FROM r.payment_date) || '; update DG_LIMIT_402G.');
                ELSIF r.account_balance > l_limit THEN
                    flag('DIST-005', 'FAIL', r.request_id, r.participant_id,
                        'Balance ' || money(r.account_balance) || ' exceeds the ' ||
                        EXTRACT(YEAR FROM r.payment_date) || ' 402(g) limit of ' || money(l_limit) || '.');
                ELSIF r.terminates_entire_interest = 'N' THEN
                    flag('DIST-005', 'FAIL', r.request_id, r.participant_id,
                        'De minimis cash-out must terminate the participant''s entire interest in the plan (and aggregated plans).');
                END IF;

            WHEN 'CHANGE_IN_CONTROL' THEN
                IF r.allows_change_in_control = 'N' THEN
                    flag('DIST-006', 'FAIL', r.request_id, r.participant_id,
                        'Plan document does not provide for payment on a change in control.');
                END IF;

            ELSE
                NULL;  -- DEATH, DISABILITY: permissible; balance and timing checks below
            END CASE;

            IF r.amount > r.account_balance THEN
                flag('DIST-008', 'FAIL', r.request_id, r.participant_id,
                    'Requested ' || money(r.amount) || ' exceeds the account balance of ' ||
                    money(r.account_balance) || '.');
            END IF;

            IF l_designated IS NOT NULL AND r.payment_date > payment_window_end(l_designated) THEN
                flag('DIST-007', 'WARN', r.request_id, r.participant_id,
                    'Payment ' || ymd(r.payment_date) || ' falls after the grace window ending ' ||
                    ymd(payment_window_end(l_designated)) || '; review for late payment.');
            END IF;

            IF NOT l_issue THEN
                add_finding('DIST-000', 'PASS', r.request_id, r.participant_id,
                    INITCAP(REPLACE(r.trigger_event, '_', ' ')) || ' distribution passes all screens.');
            END IF;
        END LOOP;
    END check_distributions;

    FUNCTION run_all RETURN NUMBER IS
    BEGIN
        g_count := 0;
        INSERT INTO dg_rule_runs (finding_count) VALUES (NULL)
        RETURNING run_id INTO g_run_id;

        check_elections;
        check_subsequent;
        check_distributions;

        UPDATE dg_rule_runs
           SET finished_at = SYSTIMESTAMP, finding_count = g_count
         WHERE run_id = g_run_id;
        COMMIT;
        RETURN g_run_id;
    END run_all;

END pkg_409a_rules;
/
