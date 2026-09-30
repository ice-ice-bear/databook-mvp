"""Adobe Analytics 2.0: read-only preflight and channel/device daily breakdowns."""
import copy
import json
import os
import re
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import providers

METRICS = ('visits', 'page_views', 'orders', 'revenue_krw')


def setting(name, default='', required=False):
    value = os.environ.get('ADOBE_' + name, default).strip()
    if required and not value:
        raise ValueError('Adobe 설정 누락: ADOBE_' + name)
    return value


class Client:
    def __init__(self):
        self.client_id = setting('CLIENT_ID', required=True)
        self.secret = setting('CLIENT_SECRET', required=True)
        self.scopes = setting('SCOPES', required=True)
        self.company = setting('GLOBAL_COMPANY_ID')
        self.rsid = setting('REPORT_SUITE_ID')
        self.token, self.expires = '', 0

    def _request(self, url, payload=None, token=False):
        # ponytail: three bounded retries, no persistent queue; add durable jobs for unattended use.
        for attempt in range(3):
            try:
                if token:
                    body = urlencode({'grant_type': 'client_credentials', 'client_id': self.client_id,
                                      'client_secret': self.secret, 'scope': self.scopes}).encode()
                    request = Request(url, data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
                    with urlopen(request, timeout=30) as response:
                        content = response.read(1_000_001)
                    if len(content) > 1_000_000:
                        raise ValueError('Adobe 응답 크기 제한 초과')
                    return json.loads(content)
                headers = {'Authorization': 'Bearer ' + self.access_token(), 'x-api-key': self.client_id,
                           'Accept': 'application/json'}
                if self.company:
                    headers['x-proxy-global-company-id'] = self.company
                return providers.request_json(url, payload, headers)
            except HTTPError as error:
                code = error.code
                if code == 401 and not token and attempt == 0:
                    self.token = ''
                    continue
                if code in (429, 500, 502, 503, 504) and attempt < 2:
                    try:
                        delay = min(10, max(1, int(error.headers.get('Retry-After', 2 ** attempt))))
                    except (ValueError, TypeError, AttributeError):
                        delay = 2 ** attempt
                    time.sleep(delay)
                    continue
                raise RuntimeError(f'Adobe 요청 실패 (HTTP_{code}). 권한·설정·호출 한도를 확인하세요.') from None
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError('Adobe 연결 실패. 네트워크와 API 상태를 확인하세요.') from None
            except (ValueError, TypeError, KeyError):
                raise ValueError('Adobe 응답 형식을 확인하세요.') from None

    def access_token(self):
        if not self.token or time.monotonic() >= self.expires:
            data = self._request('https://ims-na1.adobelogin.com/ims/token/v3', token=True)
            if not isinstance(data, dict) or not isinstance(data.get('access_token'), str) or not data['access_token']:
                raise ValueError('Adobe 토큰 응답을 확인하세요.')
            try:
                lifetime = float(data['expires_in'])
                if not 0 < lifetime <= 86400 * 30:
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                raise ValueError('Adobe 토큰 유효기간을 확인하세요.') from None
            self.token = data['access_token']
            self.expires = time.monotonic() + max(0, lifetime - 60)
        return self.token

    def api(self, path, payload=None):
        if not self.company or not self.rsid:
            raise ValueError('Adobe 설정 누락: ADOBE_GLOBAL_COMPANY_ID / ADOBE_REPORT_SUITE_ID')
        return self._request('https://analytics.adobe.io/api/' + quote(self.company, safe='') + '/' + path, payload)

    def suite(self):
        data = self.api('reportsuites/collections/suites/' + quote(self.rsid, safe='') + '?expansion=name,currency')
        if not isinstance(data, dict):
            raise ValueError('Adobe Report Suite 응답을 확인하세요.')
        return {key: data.get(key) for key in ('rsid', 'name', 'currency', 'timezoneZoneinfo')}

    def check(self):
        discovery = self._request('https://analytics.adobe.io/discovery/me')
        if not isinstance(discovery, dict) or not isinstance(discovery.get('imsOrgs'), list):
            raise ValueError('Adobe 회사 조회 응답을 확인하세요.')
        result = {'authenticated': True, 'companies': [
            {'globalCompanyId': company.get('globalCompanyId'), 'companyName': company.get('companyName')}
            for org in discovery['imsOrgs'] for company in org.get('companies', [])]}
        if self.company and self.rsid:
            result['suite'] = self.suite()
            for kind in ('dimensions', 'metrics'):
                values = self.api(kind + '?' + urlencode({'rsid': self.rsid}))
                if not isinstance(values, list):
                    raise ValueError('Adobe 메타데이터 응답을 확인하세요.')
                result[kind] = [{'id': value.get('id'), 'title': value.get('title')} for value in values]
        return result

    def report(self, day, dimension, item=None):
        ids = [setting('METRIC_' + name.upper(), default) for name, default in zip(METRICS,
               ('metrics/visits', 'metrics/pageviews', 'metrics/orders', 'metrics/revenue'))]
        if any(not re.fullmatch(r'[\w./:-]{1,200}', value) for value in [dimension, *ids]):
            raise ValueError('Adobe 차원·지표 ID를 확인하세요.')
        filters = [{'type': 'dateRange', 'dateRange': f'{day}T00:00:00.000/{day + timedelta(days=1)}T00:00:00.000'}]
        if setting('SEGMENT_ID'):
            filters.append({'type': 'segment', 'segmentId': setting('SEGMENT_ID')})
        metrics = [{'columnId': str(i), 'id': value} for i, value in enumerate(ids)]
        container = {'metrics': metrics}
        if item is not None:
            container['metricFilters'] = [{'id': '0', 'type': 'breakdown',
                'dimension': setting('CHANNEL_DIMENSION', 'variables/marketingchannel'), 'itemId': item}]
            for metric in metrics:
                metric['filters'] = ['0']
        body = {'rsid': self.rsid, 'globalFilters': filters, 'metricContainer': container,
                'dimension': dimension, 'settings': {'limit': 1000, 'page': 0, 'countRepeatInstances': True}}
        rows, seen, totals = [], set(), None
        # ponytail: cap at 10k items per breakdown; larger exports need Data Warehouse/Feeds.
        for page in range(10):
            body['settings']['page'] = page
            data = self.api('reports', copy.deepcopy(body))
            if (not isinstance(data, dict) or data.get('columns', {}).get('columnIds') != ['0', '1', '2', '3']
                    or not isinstance(data.get('rows'), list) or type(data.get('lastPage')) is not bool):
                raise ValueError('Adobe 보고서 응답·지표 순서를 확인하세요.')
            if page == 0:
                totals = data.get('summaryData', {}).get('filteredTotals', data.get('summaryData', {}).get('totals'))
                if not isinstance(totals, list) or len(totals) != 4:
                    raise ValueError('Adobe 보고서 총계를 확인하세요.')
            for row in data['rows']:
                if (not isinstance(row, dict) or not isinstance(row.get('itemId'), str)
                        or row['itemId'] in seen or not isinstance(row.get('value'), str)
                        or not isinstance(row.get('data'), list) or len(row['data']) != 4):
                    raise ValueError('Adobe 보고서 행·중복 항목을 확인하세요.')
                seen.add(row['itemId'])
                rows.append(row)
            if data['lastPage']:
                return rows, dict(zip(METRICS, totals))
            if not data['rows']:
                raise ValueError('Adobe 페이지 조회가 완료되지 않았습니다.')
        raise ValueError('Adobe 보고서 페이지 제한 초과. 범위나 차원을 줄이세요.')

    def collect(self, days):
        suite = self.suite()
        rows, totals = [], {}
        for day in days:
            channels, totals[day.isoformat()] = self.report(day, setting('CHANNEL_DIMENSION', 'variables/marketingchannel'))
            if len(channels) > 50:
                raise ValueError('Adobe 채널 50개 제한 초과. 수집 범위를 조정하세요.')
            for channel in channels:
                devices, _ = self.report(day, setting('DEVICE_DIMENSION', 'variables/mobiledevicetype'), channel['itemId'])
                rows.extend(dict(date=day.isoformat(), channel=channel['value'], device=device['value'],
                                 **dict(zip(METRICS, device['data']))) for device in devices)
        return {'suite': suite, 'totals': totals, 'rows': rows,
                'date_basis': 'Report Suite timezone; daily [00:00, next 00:00)', 'writes_database': False}


def mapping(name, expected):
    try:
        values = json.loads(setting(name, required=True))
    except json.JSONDecodeError:
        raise ValueError('Adobe 매핑 JSON 형식 오류: ADOBE_' + name) from None
    if (not isinstance(values, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in values.items())
            or set(values.values()) != set(expected) or len(values) != len(expected)):
        raise ValueError('Adobe 매핑은 현재 MVP 차원과 일대일 대응해야 합니다: ADOBE_' + name)
    return values


def normalized(result, days):
    import pipeline as p
    if setting('MAPPING_CONFIRMED', 'false') != 'true':
        raise ValueError('Adobe 미리보기와 매핑을 확인한 뒤 ADOBE_MAPPING_CONFIRMED=true로 설정하세요.')
    suite = result['suite']
    if suite.get('currency') != 'KRW' or suite.get('timezoneZoneinfo') != setting('REPORT_SUITE_TIMEZONE', required=True):
        raise ValueError('Adobe Report Suite 통화(KRW)·시간대 설정을 확인하세요.')
    channels, devices = mapping('CHANNEL_MAP', p.CHANNELS), mapping('DEVICE_MAP', p.DEVICES)
    def integer(value):
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or number > 999999999999999 or number != number.to_integral_value():
                raise ValueError()
            return int(number)
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError('Adobe 지표는 현재 MVP에서 음수 없는 정수만 지원합니다. 반올림하지 않습니다.') from None
    rows = []
    for row in result['rows']:
        if row['channel'] not in channels or row['device'] not in devices:
            raise ValueError('Adobe 미매핑 채널·디바이스가 있습니다. 미리보기로 실제 값을 확인하세요.')
        rows.append(dict(date=row['date'], channel=channels[row['channel']], device=devices[row['device']],
                         **{name: integer(row[name]) for name in METRICS}))
    rows = p.validate(rows, days)  # Missing combinations are never invented or silently zero-filled.
    for day in days:
        for name in METRICS:
            if sum(row[name] for row in rows if row['date'] == day.isoformat()) != integer(result['totals'][day.isoformat()][name]):
                raise ValueError('Adobe 분해 행 합계와 API 총계가 다릅니다. 방문 중복·세그먼트·누락 기준을 확인하세요.')
    return rows


def daily_rows(days):
    # Fail before network traffic when writes have not been enabled explicitly.
    if setting('MAPPING_CONFIRMED', 'false') != 'true':
        raise ValueError('Adobe 미리보기와 매핑을 확인한 뒤 ADOBE_MAPPING_CONFIRMED=true로 설정하세요.')
    return normalized(Client().collect(days), days)
