--------------------------------------------------------------------------------
-- DeferralGuard | Select AI on Autonomous Database (OCI Generative AI)
-- Lets compliance staff ask plain-English questions of the findings, e.g.
--   SELECT AI narrate which specified employees have open distribution failures;
--
-- Prerequisites (run once as ADMIN):
--   GRANT EXECUTE ON DBMS_CLOUD    TO dg;
--   GRANT EXECUTE ON DBMS_CLOUD_AI TO dg;
--
-- Replace the <placeholders> below. Never commit real OCIDs or keys.
--------------------------------------------------------------------------------

-- Option A: API signing key credential
BEGIN
    DBMS_CLOUD.CREATE_CREDENTIAL(
        credential_name => 'DG_OCI_GENAI_CRED',
        user_ocid       => '<user_ocid>',
        tenancy_ocid    => '<tenancy_ocid>',
        private_key     => '<private_key_contents_without_header_lines>',
        fingerprint     => '<key_fingerprint>'
    );
END;
/

-- Option B (preferred in production): resource principal, no stored key.
--   As ADMIN: EXEC DBMS_CLOUD_ADMIN.ENABLE_RESOURCE_PRINCIPAL(username => 'DG');
--   Then use "credential_name": "OCI$RESOURCE_PRINCIPAL" in the profile below.

BEGIN
    DBMS_CLOUD_AI.CREATE_PROFILE(
        profile_name => 'DG_COMPLIANCE_AI',
        attributes   => '{
            "provider"           : "oci",
            "credential_name"    : "DG_OCI_GENAI_CRED",
            "region"             : "us-chicago-1",
            "oci_compartment_id" : "<compartment_ocid>",
            "comments"           : true,
            "object_list"        : [
                {"owner": "DG", "name": "V_DG_FINDINGS_DETAIL"},
                {"owner": "DG", "name": "V_DG_PARTICIPANT_RISK"},
                {"owner": "DG", "name": "V_DG_RUN_SUMMARY"},
                {"owner": "DG", "name": "DG_RULE_CATALOG"}
            ]
        }'
    );
END;
/

-- Column comments give the model business context ("comments": true above).
COMMENT ON COLUMN dg_compliance_findings.severity IS 'PASS, WARN or FAIL outcome of a Section 409A rule';
COMMENT ON COLUMN dg_participants.is_specified_employee IS 'Y if a key employee of a public company subject to the six-month delay';
COMMENT ON COLUMN dg_distribution_requests.trigger_event IS 'Payment event: separation, disability, death, fixed date, change in control, unforeseeable emergency, de minimis';

-- Session usage -----------------------------------------------------------------
EXEC DBMS_CLOUD_AI.SET_PROFILE('DG_COMPLIANCE_AI');

SELECT AI showsql how many open failures are there by plan sponsor;
SELECT AI narrate which specified employees have distribution failures and why;

-- From PL/SQL or an APEX process (no session profile needed):
SELECT DBMS_CLOUD_AI.GENERATE(
           prompt       => 'Summarize the open 409A exceptions for the plan committee in three bullets',
           profile_name => 'DG_COMPLIANCE_AI',
           action       => 'narrate') AS committee_summary
  FROM dual;
