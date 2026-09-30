-- Parameters: comparison date, report date.
DELETE FROM mvp_raw_daily WHERE report_date IN (%s, %s);
-- executemany: date, channel, device, visits, page_views, orders, revenue_krw.
INSERT INTO mvp_raw_daily
    (report_date, channel, device, visits, page_views, orders, revenue_krw)
VALUES (%s, %s, %s, %s, %s, %s, %s);
