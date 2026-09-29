-- Test schema only. Existing AA schemas must be mapped before integration.
CREATE TABLE IF NOT EXISTS mvp_raw_daily (
    report_date DATE NOT NULL,
    channel VARCHAR(32) NOT NULL,
    device VARCHAR(16) NOT NULL,
    visits BIGINT NOT NULL CHECK (visits >= 0),
    page_views BIGINT NOT NULL CHECK (page_views >= 0),
    orders BIGINT NOT NULL CHECK (orders >= 0),
    revenue_krw BIGINT NOT NULL CHECK (revenue_krw >= 0),
    PRIMARY KEY (report_date, channel, device)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mvp_history_daily (
    report_date DATE NOT NULL,
    channel VARCHAR(32) NOT NULL,
    visits BIGINT NOT NULL,
    page_views BIGINT NOT NULL,
    orders BIGINT NOT NULL,
    revenue_krw BIGINT NOT NULL,
    PRIMARY KEY (report_date, channel)
) ENGINE=InnoDB;
