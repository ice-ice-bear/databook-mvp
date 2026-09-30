SELECT report_date, channel,
       SUM(visits) AS visits, SUM(page_views) AS page_views,
       SUM(orders) AS orders, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE report_date IN (%(comparison_date)s, %(report_date)s)
GROUP BY report_date, channel
