"""Local MariaDB daily report MVP. No live Adobe or LLM requests."""
import argparse
import csv
import hashlib
import json
import logging
import os
import random
import re
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pymysql
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent
KST = ZoneInfo('Asia/Seoul')
CHANNELS = ('paid_search', 'organic_search', 'direct', 'email', 'social')
DEVICES = ('mobile', 'desktop', 'tablet')
METRICS = ('visits', 'page_views', 'orders', 'revenue_krw')
FIELDS = ('date', 'channel', 'device', *METRICS)
VERSION = '1'
LOG = logging.getLogger('databook')


def connect():
    db = os.environ.get('DB_NAME', 'databook_mvp_test')
    if not re.fullmatch(r'databook_mvp_[a-z0-9_]+', db):
        raise ValueError('This MVP writes only to a designated databook_mvp_* test database.')
    return pymysql.connect(
        host=os.environ.get('DB_HOST', '127.0.0.1'),
        port=int(os.environ.get('DB_PORT', '3306')), database=db,
        user=os.environ.get('DB_USER', 'databook_mvp'),
        password=os.environ.get('DB_PASSWORD', ''), charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
        connect_timeout=10, read_timeout=30, write_timeout=30,
    )


def mock_rows(days):
    """Same day always produces the same data, including overlapping reruns."""
    rows = []
    for day in days:
        rng = random.Random(day.isoformat())
        for ci, channel in enumerate(CHANNELS):
            for device, share, rate in zip(DEVICES, (.65, .30, .05), (.023, .036, .018)):
                volume = (4500, 3600, 3000, 1200, 1900)[ci] * share
                volume *= (.84 if day.weekday() >= 5 else 1) * rng.uniform(.97, 1.03)
                cvr = rate * (1.05, 1, 1.12, 1.30, .65)[ci]
                # A fixed synthetic event; never inferred as a real-world cause.
                if day >= date(2026, 9, 21) and channel == 'paid_search' and device == 'mobile':
                    volume *= .62
                    cvr *= .67
                if day >= date(2026, 9, 21) and channel == 'email':
                    volume *= 1.10
                visits = round(volume)
                orders = round(visits * cvr)
                aov = round(72000 * (1.08 if device == 'desktop' else 1) * rng.uniform(.98, 1.02))
                rows.append(dict(date=day.isoformat(), channel=channel, device=device,
                                 visits=visits, page_views=round(visits*rng.uniform(2.6, 3.8)),
                                 orders=orders, revenue_krw=orders*aov))
    return rows


def extract(days, csv_path=None):
    if csv_path:
        with Path(csv_path).open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(FIELDS):
                raise ValueError(f'CSV columns must be {FIELDS}')
            rows = [r for r in reader if r['date'] in {d.isoformat() for d in days}]
    else:
        rows = mock_rows(days)
    return validate(rows, days)


def validate(rows, days):
    expected = {(d.isoformat(), c, v) for d in days for c in CHANNELS for v in DEVICES}
    seen, normalized = set(), []
    for row in rows:
        key = (row['date'], row['channel'], row['device'])
        if key not in expected or key in seen:
            raise ValueError(f'Unexpected or duplicate source key: {key}')
        seen.add(key)
        clean = dict(zip(FIELDS[:3], key))
        for metric in METRICS:
            value = row[metric]
            if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,15}', str(value)):
                raise ValueError(f'Invalid nonnegative integer: {metric} at {key}')
            clean[metric] = int(value)
        if clean['page_views'] < clean['visits']:
            raise ValueError(f'page_views below visits at {key}')
        normalized.append(clean)
    if seen != expected:
        raise ValueError(f'Incomplete source: expected {len(expected)} rows, received {len(seen)}')
    return sorted(normalized, key=lambda r: (r['date'], r['channel'], r['device']))


def lock_name(conn):
    database = conn.db.decode() if isinstance(conn.db, bytes) else conn.db
    return f'databook-mvp:{database}'


def acquire_lock(conn):
    # ponytail: one DB-wide pipeline lock; split by report dates if throughput requires it.
    with conn.cursor() as cur:
        cur.execute('SELECT GET_LOCK(%s, 0) AS acquired', (lock_name(conn),))
        if cur.fetchone()['acquired'] != 1:
            raise RuntimeError('Another pipeline run is active. Retry after it finishes.')


def init_db(conn):
    acquire_lock(conn)
    try:
        with conn.cursor() as cur:
            for statement in (ROOT/'sql/schema.sql').read_text().split(';'):
                if statement.strip():
                    cur.execute(statement)
        conn.commit()
    finally:
        with conn.cursor() as cur:
            cur.execute('SELECT RELEASE_LOCK(%s)', (lock_name(conn),))


def load_transform(conn, rows, days):
    """Caller owns the transaction: failed transform rolls back raw replacement too."""
    with conn.cursor() as cur:
        cur.execute("SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('mvp_raw_daily','mvp_history_daily')")
        engines = cur.fetchall()
        if len(engines) != 2 or any(x['ENGINE'] != 'InnoDB' for x in engines):
            raise RuntimeError('Run init-db first. Both MVP tables must use InnoDB.')
        cur.execute('DELETE FROM mvp_raw_daily WHERE report_date IN (%s,%s)', days)
        cur.executemany('INSERT INTO mvp_raw_daily VALUES (%s,%s,%s,%s,%s,%s,%s)',
                        [tuple(r[k] for k in FIELDS) for r in rows])
        LOG.info('load: %s validated rows', len(rows))
        cur.execute('DELETE FROM mvp_history_daily WHERE report_date IN (%s,%s)', days)
        cur.execute((ROOT/'sql/transform.sql').read_text(), days)
        LOG.info('transform: channel aggregates written to history')
        cur.execute('SELECT * FROM mvp_history_daily WHERE report_date IN (%s,%s) '
                    'ORDER BY report_date, channel', days)
        history = cur.fetchall()
        for day in days:
            selected = [h for h in history if h['report_date'] == day]
            if len(selected) != len(CHANNELS):
                raise ValueError('Incomplete transformed data')
            for metric in METRICS:
                if sum(h[metric] for h in selected) != sum(r[metric] for r in rows if r['date'] == day.isoformat()):
                    raise ValueError(f'Transform reconciliation failed: {metric}')
        return history


def divide(numerator, denominator):
    return numerator / denominator if denominator else None


def analyze(history, day):
    totals = {}
    for d in (day-timedelta(days=7), day):
        selected = [h for h in history if h['report_date'] == d]
        total = {k: int(sum(h[k] for h in selected)) for k in METRICS}
        total['orders_per_visit'] = divide(total['orders'], total['visits'])
        total['average_order_value'] = divide(total['revenue_krw'], total['orders'])
        totals[d.isoformat()] = total
    return totals


def export_excel(path, rows, history, totals, day, source, run_id):
    wb = Workbook()
    sheet = wb.active
    sheet.title = '일일 보고서'
    prev = day-timedelta(days=7)
    p, c = totals[prev.isoformat()], totals[day.isoformat()]
    sheet.append(['일일 분석 보고서'])
    sheet.append(['데이터', source])
    sheet.append(['보고 대상일', day, '비교일', prev])
    sheet.append(['생성 시각 KST', datetime.now(KST).isoformat(timespec='seconds')])
    sheet.append([])
    sheet.append(['지표', '비교일', '보고일', '변화', '변화 유형'])
    for row_num, (key, label, unit) in enumerate([
        ('visits', '방문 수', '%'), ('orders', '주문 수', '%'),
        ('revenue_krw', '매출 원', '%'), ('orders_per_visit', '주문/방문 비율', 'pp'),
        ('average_order_value', '객단가 원', '%'),
    ], start=7):
        delta = None if p[key] is None or c[key] is None else (
            (c[key]-p[key])*100 if unit == 'pp' else divide(c[key]-p[key], p[key]))
        sheet.append([label, p[key] if p[key] is not None else 'n.a.',
                      c[key] if c[key] is not None else 'n.a.', delta if delta is not None else 'n.a.',
                      '비율 차이' if unit == 'pp' else '상대 증감'])
        for col in (2, 3):
            sheet.cell(row_num, col).number_format = '0.00%' if unit == 'pp' else '#,##0'
        sheet.cell(row_num, 4).number_format = '+0.00"pp";-0.00"pp";0.00"pp"' if unit == 'pp' else '+0.0%;-0.0%;0.0%'
    sheet.append([])
    sheet.append(['채널', '비교일 매출 원', '보고일 매출 원', '증감액 원'])
    for ch in CHANNELS:
        before = next(h['revenue_krw'] for h in history if h['report_date'] == prev and h['channel'] == ch)
        after = next(h['revenue_krw'] for h in history if h['report_date'] == day and h['channel'] == ch)
        sheet.append([ch, before, after, after-before])
        for cell in sheet[sheet.max_row][1:4]:
            cell.number_format = '#,##0;[Red](#,##0);0'
    sheet.append([])
    sheet.append(['계산 기준', '주문/방문 = 총 주문 ÷ 총 방문. 비율 차이는 pp. 0분모는 n.a.'])
    sheet.append(['데이터 범위', '테스트 데이터의 방문은 상호 배타적. 실제 Adobe 총계와는 별도 대조 필요.'])
    sheet.append(['분석 방식', 'SQL 집계와 코드 계산. LLM 미연결.'])
    sheet.append(['실행 ID', run_id])
    sheet['B3'].number_format = sheet['D3'].number_format = 'yyyy-mm-dd'
    detail = wb.create_sheet('조회 데이터')
    detail.append(['날짜', '채널', '디바이스', '방문 수', '페이지 조회 수', '주문 수', '매출 원'])
    for r in rows:
        detail.append([date.fromisoformat(r['date']), *[r[k] for k in FIELDS[1:]]])
    detail.freeze_panes = 'D2'
    detail.auto_filter.ref = detail.dimensions
    for row in detail.iter_rows(min_row=2):
        row[0].number_format = 'yyyy-mm-dd'
        for cell in row[3:]:
            cell.number_format = '#,##0'
    for ws, headers in [(sheet, (6, 13)), (detail, (1,))]:
        ws.sheet_view.showGridLines = False
        for row in ws:
            ws.row_dimensions[row[0].row].height = 24
            for cell in row:
                cell.font = Font(name='Arial', size=11)
                cell.alignment = Alignment(vertical='center')
        for n in headers:
            for cell in ws[n]:
                cell.fill = PatternFill('solid', fgColor='213B54')
                cell.font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
        for col in 'ABCDEFG':
            ws.column_dimensions[col].width = 22 if col != 'A' else 24
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.print_options.horizontalCentered = True
    for row in (2, 4, 20, 21, 22, 23):
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=5)
        sheet.cell(row, 2).alignment = Alignment(wrap_text=True, vertical='center')
        sheet.row_dimensions[row].height = 32
    sheet['A1'].font = Font(name='Arial', size=17, bold=True)
    sheet.print_area = 'A1:E23'
    sheet.page_setup.fitToHeight = 1
    wb.save(path)
    wb.close()


def atomic_json(path, obj):
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.json-', suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            json.dump(obj, out, ensure_ascii=False, indent=2, default=str)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def run(conn, day, csv_path=None, regenerate=False, report_dir=None, log_dir=None):
    reports = Path(report_dir or os.environ.get('REPORT_DIR', ROOT/'reports'))
    logs = Path(log_dir or os.environ.get('LOG_DIR', ROOT/'logs'))
    reports.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    record = {'run_id': run_id, 'report_date': day.isoformat(), 'status': 'running',
              'started_at': datetime.now(KST).isoformat(), 'stage': 'lock'}
    record_path = logs/f'{run_id}.json'
    atomic_json(record_path, record)
    locked, temporary = False, None
    try:
        acquire_lock(conn)
        locked = True
        record['stage'] = 'extract'
        days = (day-timedelta(days=7), day)
        rows = extract(days, csv_path)
        fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        source = f'CSV 테스트 데이터: {Path(csv_path).name}' if csv_path else '가상 데이터 (mock)'
        identity = {'version': VERSION, 'input_sha256': fingerprint, 'source': source,
                    'database_sha256': hashlib.sha256(f'{conn.host}:{conn.port}:{conn.db}'.encode()).hexdigest(),
                    'transform_sha256': hashlib.sha256((ROOT/'sql/transform.sql').read_bytes()).hexdigest()}
        manifest_path = reports/f'daily_report_{day}.json'
        if manifest_path.exists() and not regenerate:
            previous = json.loads(manifest_path.read_text())
            existing = reports/Path(previous['file']).name
            if previous['identity'] != identity:
                raise ValueError('Input, database or SQL changed. Use --regenerate to create a new report version.')
            if existing.exists() and hashlib.sha256(existing.read_bytes()).hexdigest() == previous['file_sha256']:
                record.update(status='skipped', file=existing.name, stage='complete')
                return existing
        version, output = 1, reports/f'daily_report_{day}.xlsx'
        while output.exists():
            version += 1
            output = reports/f'daily_report_{day}_v{version}.xlsx'
        record['stage'] = 'load_transform'
        atomic_json(record_path, record)
        conn.begin()
        history = load_transform(conn, rows, days)
        totals = analyze(history, day)
        record['stage'] = 'export'
        atomic_json(record_path, record)
        handle, temporary = tempfile.mkstemp(dir=reports, prefix='.report-', suffix='.xlsx')
        os.close(handle)
        export_excel(temporary, rows, history, totals, day, source, run_id)
        # Build before commit: export failure rolls back both raw and history writes.
        conn.commit()
        record['stage'] = 'publish'
        atomic_json(record_path, record)
        # Hard-link publication is atomic and refuses to overwrite an existing file.
        os.link(temporary, output)
        atomic_json(manifest_path, {'run_id': run_id, 'file': output.name, 'identity': identity,
                    'file_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'totals': totals,
                    'report_date': day.isoformat(), 'comparison_date': days[0].isoformat(),
                    'generated_at': datetime.now(KST).isoformat()})
        record.update(status='succeeded', file=output.name, stage='complete')
        LOG.info('complete: %s', output.name)
        return output
    except Exception as error:
        conn.rollback()
        record.update(status='failed', error_type=type(error).__name__)
        # Do not serialize DB exceptions or connection credentials into public reports.
        raise
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
        record['finished_at'] = datetime.now(KST).isoformat()
        try:
            atomic_json(record_path, record)
        finally:
            if locked:
                with conn.cursor() as cur:
                    cur.execute('SELECT RELEASE_LOCK(%s)', (lock_name(conn),))


def main():
    parser = argparse.ArgumentParser(description='MariaDB → SQL → daily Excel local MVP (mock/CSV only)')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init-db', help='Create two MVP tables in a designated TEST database only')
    report = commands.add_parser('run', help='Generate a new dated Excel report')
    report.add_argument('--date', type=date.fromisoformat,
                        default=datetime.now(KST).date()-timedelta(days=1), help='Report date, default yesterday KST')
    report.add_argument('--csv', type=Path, help='Normalized CSV; omit for deterministic mock data')
    report.add_argument('--regenerate', action='store_true', help='Preserve prior report and publish a new version')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        with connect() as conn:
            if args.command == 'init-db':
                init_db(conn)
                LOG.info('MVP test schema ready')
            else:
                print(run(conn, args.date, args.csv, args.regenerate))
    except (ValueError, RuntimeError) as error:
        LOG.error('%s', error)
        return 1
    except Exception as error:
        LOG.error('%s: operation failed; check local DB/service configuration and logs.', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
