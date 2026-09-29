INSERT INTO mvp_history_daily
    (report_date, channel, visits, page_views, orders, revenue_krw)
SELECT report_date, channel, SUM(visits), SUM(page_views), SUM(orders), SUM(revenue_krw)
FROM mvp_raw_daily
WHERE report_date IN (%s, %s)
GROUP BY report_date, channel
