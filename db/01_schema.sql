--------------------------------------------------------------------------------
-- DeferralGuard | Oracle Autonomous Database schema
-- Run as the application schema owner (e.g. DG) in Database Actions > SQL,
-- SQLcl or SQL Developer. Compatible with Autonomous Database 19c and 23ai.
--------------------------------------------------------------------------------

CREATE TABLE dg_plans (
    plan_id                         VARCHAR2(20)  PRIMARY KEY,
    sponsor                         VARCHAR2(200) NOT NULL,
    is_public_company               CHAR(1)       DEFAULT 'N' NOT NULL CHECK (is_public_company IN ('Y','N')),
    allows_unforeseeable_emergency  CHAR(1)       DEFAULT 'Y' NOT NULL CHECK (allows_unforeseeable_emergency IN ('Y','N')),
    allows_change_in_control        CHAR(1)       DEFAULT 'Y' NOT NULL CHECK (allows_change_in_control IN ('Y','N')),
    allows_de_minimis_cashout       CHAR(1)       DEFAULT 'Y' NOT NULL CHECK (allows_de_minimis_cashout IN ('Y','N'))
);

CREATE TABLE dg_participants (
    participant_id         VARCHAR2(20)  PRIMARY KEY,
    plan_id                VARCHAR2(20)  NOT NULL REFERENCES dg_plans,
    full_name              VARCHAR2(200) NOT NULL,
    is_specified_employee  CHAR(1)       DEFAULT 'N' NOT NULL CHECK (is_specified_employee IN ('Y','N')),
    eligibility_date       DATE,
    separation_date        DATE
);

CREATE TABLE dg_deferral_elections (
    election_id             VARCHAR2(20) PRIMARY KEY,
    participant_id          VARCHAR2(20) NOT NULL REFERENCES dg_participants,
    plan_year               NUMBER(4)    NOT NULL,
    comp_type               VARCHAR2(20) NOT NULL CHECK (comp_type IN ('SALARY','BONUS','PERFORMANCE_BONUS')),
    election_date           DATE         NOT NULL,
    is_initial_eligibility  CHAR(1)      DEFAULT 'N' NOT NULL CHECK (is_initial_eligibility IN ('Y','N')),
    perf_period_start       DATE,
    perf_period_end         DATE
);

CREATE TABLE dg_subsequent_elections (
    election_id            VARCHAR2(20) PRIMARY KEY,
    participant_id         VARCHAR2(20) NOT NULL REFERENCES dg_participants,
    election_date          DATE         NOT NULL,
    original_payment_date  DATE         NOT NULL,
    new_payment_date       DATE         NOT NULL
);

CREATE TABLE dg_distribution_requests (
    request_id                  VARCHAR2(20)  PRIMARY KEY,
    participant_id              VARCHAR2(20)  NOT NULL REFERENCES dg_participants,
    trigger_event               VARCHAR2(30)  NOT NULL CHECK (trigger_event IN
                                    ('SEPARATION','DISABILITY','DEATH','FIXED_DATE','CHANGE_IN_CONTROL',
                                     'UNFORESEEABLE_EMERGENCY','DE_MINIMIS','IN_SERVICE')),
    request_date                DATE          NOT NULL,
    payment_date                DATE          NOT NULL,
    amount                      NUMBER(14,2)  NOT NULL CHECK (amount > 0),
    account_balance             NUMBER(14,2)  NOT NULL,
    scheduled_date              DATE,
    emergency_need_amount       NUMBER(14,2),
    terminates_entire_interest  CHAR(1)       DEFAULT 'N' NOT NULL CHECK (terminates_entire_interest IN ('Y','N')),
    -- free-text intake from the participant; classified by OCI Generative AI
    intake_text                 CLOB,
    ai_summary                  VARCHAR2(4000)
);

-- Reference data -------------------------------------------------------------

CREATE TABLE dg_limit_402g (
    limit_year   NUMBER(4)  PRIMARY KEY,
    limit_amount NUMBER(10) NOT NULL
);

CREATE TABLE dg_rule_catalog (
    rule_code    VARCHAR2(12)  PRIMARY KEY,
    rule_area    VARCHAR2(30)  NOT NULL,
    rule_name    VARCHAR2(200) NOT NULL,
    citation     VARCHAR2(100) NOT NULL
);

-- Results --------------------------------------------------------------------

CREATE TABLE dg_rule_runs (
    run_id        NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    finished_at   TIMESTAMP WITH TIME ZONE,
    run_by        VARCHAR2(128) DEFAULT SYS_CONTEXT('USERENV','SESSION_USER') NOT NULL,
    finding_count NUMBER
);

CREATE TABLE dg_compliance_findings (
    finding_id      NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          NUMBER        NOT NULL REFERENCES dg_rule_runs,
    rule_code       VARCHAR2(12)  NOT NULL,
    severity        VARCHAR2(4)   NOT NULL CHECK (severity IN ('PASS','WARN','FAIL')),
    subject_id      VARCHAR2(20)  NOT NULL,
    participant_id  VARCHAR2(20)  NOT NULL,
    message         VARCHAR2(1000) NOT NULL,
    citation        VARCHAR2(100) NOT NULL,
    -- workflow columns maintained from the APEX exception queue
    status          VARCHAR2(12)  DEFAULT 'OPEN' NOT NULL CHECK (status IN ('OPEN','IN_REVIEW','RESOLVED','WAIVED')),
    assigned_to     VARCHAR2(128),
    resolution_note VARCHAR2(4000),
    ai_explanation  VARCHAR2(4000)
);

CREATE INDEX dg_findings_run_ix  ON dg_compliance_findings (run_id, severity);
CREATE INDEX dg_findings_part_ix ON dg_compliance_findings (participant_id);

COMMENT ON TABLE dg_compliance_findings IS
  'Output of PKG_409A_RULES.RUN_ALL. One row per rule outcome per election or distribution.';
