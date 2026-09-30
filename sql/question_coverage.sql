-- Verify complete dates before applying optional filters.
SELECT report_date, COUNT(*) AS row_count
FROM mvp_raw_daily
WHERE report_date BETWEEN %s AND %s OR report_date BETWEEN %s AND %s
GROUP BY report_date ORDER BY report_date;
