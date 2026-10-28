# APEX application blueprint

The APEX app is a thin UI over the views in `db/04_views_apex.sql`. All compliance
logic lives in `PKG_409A_RULES`, so pages contain no business rules and can be
rebuilt quickly with the Create App wizard.

App name: **DeferralGuard** · Theme: Universal Theme (Redwood Light) · Auth: APEX accounts or OCI IAM

| Page | Type | Source | Notes |
|---|---|---|---|
| 1 Dashboard | Cards + Chart | `V_DG_RUN_SUMMARY`, `V_DG_LATEST_RUN` | Fail / Warn / Pass cards; bar chart of failures by rule area; "dollars on hold" card |
| 2 Exception Queue | Interactive Grid | `V_DG_EXCEPTION_QUEUE` | Editable `STATUS`, `ASSIGNED_TO`, `RESOLUTION_NOTE` (DML on `DG_COMPLIANCE_FINDINGS` by `FINDING_ID`); facets on severity, rule area, sponsor |
| 3 Participant Risk | Interactive Report | `V_DG_PARTICIPANT_RISK` | Link to page 4; highlight specified employees |
| 4 Participant Detail | Form + Report | `DG_PARTICIPANTS`, `V_DG_FINDINGS_DETAIL` | Elections, re-deferrals and distributions for one participant |
| 5 New Distribution Request | Form | `DG_DISTRIBUTION_REQUESTS` | Paste participant message into `INTAKE_TEXT`; "Classify with AI" button pre-fills trigger and amounts for the analyst to confirm |
| 6 Ask the Data | Static + PL/SQL | `DBMS_CLOUD_AI.GENERATE` | Text field → Select AI `narrate` against profile `DG_COMPLIANCE_AI` |

## Key page processes

**Run rules (page 1 button, or nightly via DBMS_SCHEDULER):**

```sql
DECLARE
    l_run NUMBER;
BEGIN
    l_run := pkg_409a_rules.run_all;
    apex_application.g_print_success_message := 'Rule run ' || l_run || ' complete.';
END;
```

**Nightly job:**

```sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'DG_NIGHTLY_409A_SCREEN',
        job_type        => 'PLSQL_BLOCK',
        job_action      => 'DECLARE r NUMBER; BEGIN r := pkg_409a_rules.run_all; END;',
        repeat_interval => 'FREQ=DAILY;BYHOUR=5;BYMINUTE=15',
        enabled         => TRUE);
END;
/
```

**Ask the Data (page 6):**

```sql
:P6_ANSWER := DBMS_CLOUD_AI.GENERATE(
                  prompt       => :P6_QUESTION,
                  profile_name => 'DG_COMPLIANCE_AI',
                  action       => 'narrate');
```

**Classify with AI (page 5):** call the Python intake service
(`deferral_guard.genai.classify_intake`, exposed behind an OCI Function or ORDS
endpoint) with `APEX_WEB_SERVICE.MAKE_REST_REQUEST`, or use
`DBMS_CLOUD_AI.GENERATE(action => 'chat')` with the same prompt as
`INTAKE_PROMPT`. The analyst always confirms the draft before saving.

## Why this split

- Deterministic rules decide pass/fail and are unit tested in CI.
- Gen AI only drafts intake and explanations, with a human in the loop.
- APEX stays low-code: every page is a declarative region over a view.
