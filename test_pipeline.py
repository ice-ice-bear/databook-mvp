"""One integration check against the isolated MariaDB demo. Run via Compose."""
import hashlib
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

import pipeline as p


def expect_failure(call, kind):
    try:
        call()
    except kind:
        return
    raise AssertionError(f'Expected {kind.__name__}')


def check():
    day = date(2026, 9, 27)
    days = (day-timedelta(days=7), day)
    source = p.ROOT/'data/adobe_mock_daily.csv'
    rows = p.extract(days, source)
    assert len(rows) == 30
    assert p.divide(1, 0) is None
    expect_failure(lambda: p.validate(rows[:-1], days), ValueError)
    expect_failure(lambda: p.validate(rows+[rows[0]], days), ValueError)
    expect_failure(lambda: p.validate([dict(rows[0], visits=-1), *rows[1:]], days), ValueError)
    expect_failure(lambda: p.extract((date(2025, 1, 1), date(2025, 1, 8)), source), ValueError)
    with tempfile.TemporaryDirectory() as tmp, p.connect() as conn:
        root = Path(tmp)
        p.init_db(conn)
        kwargs = dict(csv_path=source, report_dir=root/'reports', log_dir=root/'logs')
        output = p.run(conn, day, **kwargs)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        wb = load_workbook(output, data_only=True)
        assert wb['일일 보고서']['B9'].value == 24079860
        assert wb['일일 보고서']['C9'].value == 22273572
        assert wb['조회 데이터'].max_row == 31
        assert wb['일일 보고서']['B3'].value.date() == day
        wb.close()
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS n FROM mvp_raw_daily WHERE report_date IN (%s,%s)', days)
            assert cur.fetchone()['n'] == 30
            cur.execute('SELECT COUNT(*) AS n FROM mvp_history_daily WHERE report_date IN (%s,%s)', days)
            assert cur.fetchone()['n'] == 10
        conn.commit()
        assert p.run(conn, day, **kwargs) == output
        assert len(list((root/'reports').glob('*.xlsx'))) == 1
        regenerated = p.run(conn, day, regenerate=True, **kwargs)
        assert regenerated.stem.endswith('_v2')
        assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
        assert p.run(conn, day, **kwargs) == regenerated
        with patch.object(conn, 'host', 'another-database-host'):
            expect_failure(lambda: p.run(conn, day, **kwargs), ValueError)
        with p.connect() as second:
            p.acquire_lock(second)
            expect_failure(lambda: p.run(conn, day, **kwargs), RuntimeError)
        # Changed input must not silently reuse an earlier report.
        expect_failure(lambda: p.run(conn, day, report_dir=root/'reports', log_dir=root/'logs'), ValueError)
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM mvp_raw_daily WHERE report_date IN (%s,%s) ORDER BY report_date,channel,device', days)
            before = cur.fetchall()
        conn.commit()
        with patch.object(p, 'export_excel', side_effect=OSError('simulated disk full')):
            expect_failure(lambda: p.run(conn, day, regenerate=True, report_dir=root/'reports', log_dir=root/'logs'), OSError)
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM mvp_raw_daily WHERE report_date IN (%s,%s) ORDER BY report_date,channel,device', days)
            assert cur.fetchall() == before, 'Failed export must roll back changed raw input'
        conn.commit()
        assert not (root/'reports'/f'daily_report_{day}_v3.xlsx').exists()
        assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
        states = [json.loads(f.read_text())['status'] for f in (root/'logs').glob('*.json')]
        assert {'succeeded', 'failed', 'skipped'} <= set(states)
        # Zero denominator should be a visible n.a., not a spreadsheet error or false zero.
        zero = [dict(r, visits=0, page_views=0, orders=0, revenue_krw=0) for r in rows]
        p.validate(zero, days)
        conn.begin()
        history = p.load_transform(conn, zero, days)
        totals = p.analyze(history, day)
        assert totals[day.isoformat()]['orders_per_visit'] is None
        p.export_excel(root/'zero.xlsx', zero, history, totals, day, 'zero test', 'test')
        conn.rollback()
        wb = load_workbook(root/'zero.xlsx', data_only=True)
        assert wb['일일 보고서']['C10'].value == 'n.a.'
        assert wb['일일 보고서']['D9'].value == 'n.a.'
        wb.close()
    print('PASS: MariaDB load/SQL/export; known totals; duplicate/missing/invalid input; '
          'idempotency; versions; concurrent lock; changed input; rollback; zero denominator.')


if __name__ == '__main__':
    check()
