-- Core aggregation queries for the NHS A&E four-hour target analysis.
-- Run against data/nhs_ae.duckdb (table: ae_attendances) after src/load_db.py.
-- One block per business question - copy/paste into DuckDB CLI, Python
-- (con.execute(...)), or the notebook as needed.
--
-- Note on methodology: total_attendances, in_4_hours and pct_in_4_hours are
-- derived in src/clean.py from six raw sub-columns (Type 1/2/Other, each
-- split into walk-in and pre-booked) - the source files don't publish a
-- single "total" column. wait_4_12h_dta / wait_12h_plus_dta are a distinct
-- metric (trolley wait after the decision to admit) and are NOT folded into
-- the four-hour attendance standard used here.


-- 1. National monthly four-hour performance
-- What's the headline trend everyone quotes?
SELECT
    period,
    SUM(total_attendances)                                   AS total_attendances,
    SUM(in_4_hours)                                           AS in_4_hours,
    ROUND(100.0 * SUM(in_4_hours) / SUM(total_attendances), 2) AS pct_in_4_hours
FROM ae_attendances
GROUP BY period
ORDER BY period;


-- 2. Worst and best performing trusts (latest month)
-- Who's furthest from the 95% target right now?
WITH latest_period AS (
    SELECT MAX(period) AS period FROM ae_attendances
)
SELECT
    a.org_code,
    a.org_name,
    a.region,
    a.total_attendances,
    a.in_4_hours,
    ROUND(100.0 * a.in_4_hours / NULLIF(a.total_attendances, 0), 2) AS pct_in_4_hours
FROM ae_attendances a
JOIN latest_period lp USING (period)
WHERE a.total_attendances > 0
ORDER BY pct_in_4_hours ASC;


-- 3. Trust-level trend over time
-- Is a given trust improving, flat, or deteriorating? Parameterise org_code.
SELECT
    period,
    org_code,
    org_name,
    total_attendances,
    ROUND(100.0 * in_4_hours / NULLIF(total_attendances, 0), 2) AS pct_in_4_hours
FROM ae_attendances
WHERE org_code = 'REPLACE_ME'
ORDER BY period;


-- 4. Seasonality: national performance by calendar month
-- Does winter really hit performance as hard as the headlines say?
-- Volume-weighted (sum of attendances / sum in 4 hours), not a plain average
-- across orgs - a plain average lets small, near-100%-performing urgent
-- treatment centres drown out the large acute trusts that actually drive
-- national performance.
SELECT
    EXTRACT(MONTH FROM period) AS calendar_month,
    ROUND(100.0 * SUM(in_4_hours) / SUM(total_attendances), 2) AS avg_pct_in_4_hours
FROM ae_attendances
WHERE total_attendances > 0
GROUP BY calendar_month
ORDER BY calendar_month;


-- 5. Attendance type mix over time
-- Has the split between Type 1 (major A&E), Type 2, and Type 3
-- (urgent treatment centres etc.) shifted? Walk-in and pre-booked
-- attendances are combined per type here.
SELECT
    period,
    SUM(attendances_type1 + attendances_type1_booked) AS type1,
    SUM(attendances_type2 + attendances_type2_booked) AS type2,
    SUM(attendances_type3 + attendances_type3_booked) AS type3
FROM ae_attendances
GROUP BY period
ORDER BY period;


-- 6. Trusts that crossed the 95% -> below 95% -> below 75% thresholds
-- Track how many trusts have fallen through each performance band each month.
SELECT
    period,
    COUNT(*) FILTER (WHERE pct >= 95)                  AS trusts_meeting_target,
    COUNT(*) FILTER (WHERE pct >= 75 AND pct < 95)      AS trusts_below_target,
    COUNT(*) FILTER (WHERE pct < 75)                    AS trusts_severely_below
FROM (
    SELECT
        period,
        org_code,
        100.0 * in_4_hours / NULLIF(total_attendances, 0) AS pct
    FROM ae_attendances
    WHERE total_attendances > 0
) t
GROUP BY period
ORDER BY period;


-- 7. Regional performance
-- The raw files carry a "Parent Org" field (NHS England's seven regions:
-- London, Midlands, North East and Yorkshire, North West, South East,
-- South West, East of England) which clean.py maps straight to `region` -
-- no separate trust-to-region lookup needed.
SELECT
    region,
    period,
    ROUND(100.0 * SUM(in_4_hours) / SUM(total_attendances), 2) AS pct_in_4_hours
FROM ae_attendances
WHERE total_attendances > 0
GROUP BY region, period
ORDER BY region, period;


-- 7b. Regional performance, latest month only, ranked
WITH latest_period AS (
    SELECT MAX(period) AS period FROM ae_attendances
)
SELECT
    a.region,
    SUM(a.total_attendances)                                     AS total_attendances,
    ROUND(100.0 * SUM(a.in_4_hours) / SUM(a.total_attendances), 2) AS pct_in_4_hours
FROM ae_attendances a
JOIN latest_period lp USING (period)
WHERE a.total_attendances > 0
GROUP BY a.region
ORDER BY pct_in_4_hours ASC;
