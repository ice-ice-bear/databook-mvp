-- Schema must be transactional before any writes.
SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('mvp_raw_daily', 'mvp_history_daily');
-- Parameters: comparison date, report date. Python reconciles these totals with input.
SELECT report_date, channel, visits, page_views, orders, revenue_krw
FROM mvp_history_daily
WHERE report_date IN (%s, %s)
ORDER BY report_date, channel;
