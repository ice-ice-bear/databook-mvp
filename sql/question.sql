-- summary: previous start/end, current start/end, channel twice, device twice.
SELECT report_date, '전체' AS segment, COUNT(*) AS source_rows, SUM(visits) AS visits, SUM(page_views) AS page_views, SUM(orders) AS orders, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE (report_date BETWEEN %s AND %s OR report_date BETWEEN %s AND %s)
  AND (%s = '' OR channel = %s) AND (%s = '' OR device = %s)
GROUP BY report_date, segment
ORDER BY report_date, segment;
-- channel: previous start/end, current start/end, channel twice, device twice.
SELECT report_date, channel AS segment, COUNT(*) AS source_rows, SUM(visits) AS visits, SUM(page_views) AS page_views, SUM(orders) AS orders, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE (report_date BETWEEN %s AND %s OR report_date BETWEEN %s AND %s)
  AND (%s = '' OR channel = %s) AND (%s = '' OR device = %s)
GROUP BY report_date, segment
ORDER BY report_date, segment;
-- device: previous start/end, current start/end, channel twice, device twice.
SELECT report_date, device AS segment, COUNT(*) AS source_rows, SUM(visits) AS visits, SUM(page_views) AS page_views, SUM(orders) AS orders, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE (report_date BETWEEN %s AND %s OR report_date BETWEEN %s AND %s)
  AND (%s = '' OR channel = %s) AND (%s = '' OR device = %s)
GROUP BY report_date, segment
ORDER BY report_date, segment;
-- daily: previous start/end, current start/end, channel twice, device twice.
SELECT report_date, '일별' AS segment, COUNT(*) AS source_rows, SUM(visits) AS visits, SUM(page_views) AS page_views, SUM(orders) AS orders, SUM(revenue_krw) AS revenue_krw
FROM mvp_raw_daily
WHERE (report_date BETWEEN %s AND %s OR report_date BETWEEN %s AND %s)
  AND (%s = '' OR channel = %s) AND (%s = '' OR device = %s)
GROUP BY report_date, segment
ORDER BY report_date, segment;
