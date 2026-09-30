-- Question detail. Parameters: comparison date, report date.
SELECT report_date AS date, channel, device, visits, page_views, orders, revenue_krw
FROM mvp_raw_daily
WHERE report_date IN (%s, %s)
ORDER BY report_date, channel, device;
-- Report channel totals use the daily aggregation output.
SELECT report_date, channel, visits, page_views, orders, revenue_krw
FROM mvp_history_daily
WHERE report_date IN (%s, %s)
ORDER BY report_date, channel;
-- Device totals for question comparisons. Same two bound dates.
SELECT report_date, device, SUM(visits) AS visits, SUM(page_views) AS page_views,
       SUM(orders) AS orders, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE report_date IN (%s, %s)
GROUP BY report_date, device;
