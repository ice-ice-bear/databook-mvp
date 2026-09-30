-- Controlled writes. Aggregation SELECT is configured separately in aggregate_daily.sql / web settings.
DELETE FROM mvp_history_daily WHERE report_date IN (%s, %s);
INSERT INTO mvp_history_daily
    (report_date, channel, visits, page_views, orders, revenue_krw)
VALUES (%s, %s, %s, %s, %s, %s);
