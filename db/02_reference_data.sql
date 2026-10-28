--------------------------------------------------------------------------------
-- DeferralGuard | reference data
-- 402(g) limits drive the de minimis cash-out screen (1.409A-3(j)(4)(v)).
-- Add each new year from the IRS cost-of-living notice.
--------------------------------------------------------------------------------

INSERT INTO dg_limit_402g VALUES (2023, 22500);
INSERT INTO dg_limit_402g VALUES (2024, 23000);
INSERT INTO dg_limit_402g VALUES (2025, 23500);
INSERT INTO dg_limit_402g VALUES (2026, 24500);

INSERT INTO dg_rule_catalog VALUES ('ELECT-001', 'Initial election', 'Salary/bonus election made before the service year', 'Treas. Reg. 1.409A-2(a)(3)');
INSERT INTO dg_rule_catalog VALUES ('ELECT-002', 'Initial election', 'Performance-based compensation 6-month election rule', 'Treas. Reg. 1.409A-2(a)(8)');
INSERT INTO dg_rule_catalog VALUES ('ELECT-003', 'Initial election', 'Newly-eligible participant 30-day election window', 'Treas. Reg. 1.409A-2(a)(7)');
INSERT INTO dg_rule_catalog VALUES ('REDEF-001', 'Subsequent election', 'Re-deferral made 12+ months before original payment', 'Treas. Reg. 1.409A-2(b)(1)');
INSERT INTO dg_rule_catalog VALUES ('REDEF-002', 'Subsequent election', 'Re-deferral pushes payment out at least 5 years', 'Treas. Reg. 1.409A-2(b)(1)');
INSERT INTO dg_rule_catalog VALUES ('DIST-000', 'Distribution', 'Distribution passes all screens', 'Treas. Reg. 1.409A-3');
INSERT INTO dg_rule_catalog VALUES ('DIST-001', 'Distribution', 'Permissible payment event', 'Treas. Reg. 1.409A-3(a)');
INSERT INTO dg_rule_catalog VALUES ('DIST-002', 'Distribution', 'Specified employee six-month delay', 'Treas. Reg. 1.409A-3(i)(2)');
INSERT INTO dg_rule_catalog VALUES ('DIST-003', 'Distribution', 'No acceleration of fixed-date payment', 'Treas. Reg. 1.409A-3(j)(1)');
INSERT INTO dg_rule_catalog VALUES ('DIST-004', 'Distribution', 'Unforeseeable emergency limited to documented need', 'Treas. Reg. 1.409A-3(i)(3)');
INSERT INTO dg_rule_catalog VALUES ('DIST-005', 'Distribution', 'De minimis cash-out within 402(g) limit', 'Treas. Reg. 1.409A-3(j)(4)(v)');
INSERT INTO dg_rule_catalog VALUES ('DIST-006', 'Distribution', 'Change in control payment permitted by plan', 'Treas. Reg. 1.409A-3(i)(5)');
INSERT INTO dg_rule_catalog VALUES ('DIST-007', 'Distribution', 'Payment within the designated-date grace window', 'Treas. Reg. 1.409A-3(d)');
INSERT INTO dg_rule_catalog VALUES ('DIST-008', 'Distribution', 'Amount does not exceed account balance', 'Plan recordkeeping control');

COMMIT;
