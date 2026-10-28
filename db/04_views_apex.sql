--------------------------------------------------------------------------------
-- DeferralGuard | reporting views
-- These are the data sources for the APEX application pages described in
-- apex/README.md, and the objects exposed to Select AI in 05_select_ai.sql.
--------------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_dg_latest_run AS
SELECT run_id, started_at, finished_at, run_by, finding_count
  FROM dg_rule_runs
 WHERE run_id = (SELECT MAX(run_id) FROM dg_rule_runs WHERE finished_at IS NOT NULL);

CREATE OR REPLACE VIEW v_dg_findings_detail AS
SELECT f.finding_id,
       f.run_id,
       f.rule_code,
       c.rule_area,
       c.rule_name,
       f.severity,
       f.status,
       f.subject_id,
       f.participant_id,
       p.full_name                 AS participant_name,
       pl.plan_id,
       pl.sponsor                  AS plan_sponsor,
       p.is_specified_employee,
       f.message,
       f.citation,
       f.assigned_to,
       f.resolution_note,
       f.ai_explanation,
       d.amount                    AS distribution_amount,
       d.trigger_event,
       d.payment_date
  FROM dg_compliance_findings f
  JOIN dg_rule_catalog  c  ON c.rule_code       = f.rule_code
  JOIN dg_participants  p  ON p.participant_id  = f.participant_id
  JOIN dg_plans         pl ON pl.plan_id        = p.plan_id
  LEFT JOIN dg_distribution_requests d ON d.request_id = f.subject_id;

-- Page 1: dashboard cards and chart
CREATE OR REPLACE VIEW v_dg_run_summary AS
SELECT v.rule_area,
       COUNT(*)                                          AS checks_run,
       COUNT(CASE WHEN v.severity = 'FAIL' THEN 1 END)   AS failures,
       COUNT(CASE WHEN v.severity = 'WARN' THEN 1 END)   AS warnings,
       COUNT(CASE WHEN v.severity = 'PASS' THEN 1 END)   AS passes,
       SUM(CASE WHEN v.severity = 'FAIL' THEN v.distribution_amount END) AS dollars_on_hold
  FROM v_dg_findings_detail v
  JOIN v_dg_latest_run r ON r.run_id = v.run_id
 GROUP BY v.rule_area;

-- Page 2: exception work queue (Interactive Grid; status/assigned_to editable)
CREATE OR REPLACE VIEW v_dg_exception_queue AS
SELECT v.*
  FROM v_dg_findings_detail v
  JOIN v_dg_latest_run r ON r.run_id = v.run_id
 WHERE v.severity IN ('FAIL', 'WARN')
   AND v.status IN ('OPEN', 'IN_REVIEW');

-- Page 3: participant risk ranking
CREATE OR REPLACE VIEW v_dg_participant_risk AS
SELECT v.participant_id,
       v.participant_name,
       v.plan_sponsor,
       v.is_specified_employee,
       COUNT(CASE WHEN v.severity = 'FAIL' THEN 1 END) AS open_failures,
       COUNT(CASE WHEN v.severity = 'WARN' THEN 1 END) AS open_warnings,
       LISTAGG(DISTINCT CASE WHEN v.severity <> 'PASS' THEN v.rule_code END, ', ')
           WITHIN GROUP (ORDER BY CASE WHEN v.severity <> 'PASS' THEN v.rule_code END) AS rule_codes
  FROM v_dg_findings_detail v
  JOIN v_dg_latest_run r ON r.run_id = v.run_id
 GROUP BY v.participant_id, v.participant_name, v.plan_sponsor, v.is_specified_employee;
