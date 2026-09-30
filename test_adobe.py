"""Offline Adobe contract check. No credentials, live API, DB writes or LLM calls."""
import copy
import io
import json
import os
from datetime import date, timedelta
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

import adobe
import pipeline as p
import providers


def fails(call, text):
    try:
        call()
    except (ValueError, RuntimeError) as error:
        assert text in str(error), str(error)
        assert 'test-secret' not in str(error) and 'test-token' not in str(error)
        return
    raise AssertionError('Expected rejection')


def check():
    days = (date(2026, 9, 20), date(2026, 9, 27))
    expected = p.validate(p.mock_rows(days), days)
    channel_map = {f'Channel {i}': ch for i, ch in enumerate(p.CHANNELS)}
    device_map = {f'Device {i}': device for i, device in enumerate(p.DEVICES)}
    env = {'ADOBE_CLIENT_ID': 'test-client', 'ADOBE_CLIENT_SECRET': 'test-secret', 'ADOBE_SCOPES': 'test-scope',
           'ADOBE_GLOBAL_COMPANY_ID': 'test-company', 'ADOBE_REPORT_SUITE_ID': 'test-rsid',
           'ADOBE_REPORT_SUITE_TIMEZONE': 'Asia/Seoul', 'ADOBE_MAPPING_CONFIRMED': 'true',
           'ADOBE_CHANNEL_MAP': json.dumps(channel_map), 'ADOBE_DEVICE_MAP': json.dumps(device_map),
           'DATA_PROVIDER': 'adobe', 'LLM_PROVIDER': 'none'}
    requests = []
    def response(url, payload=None, headers=None):
        assert headers['Authorization'] == 'Bearer test-token'
        assert headers['x-api-key'] == 'test-client' and 'test-secret' not in url
        if url.endswith('/discovery/me'):
            return {'imsOrgs': [{'companies': [{'globalCompanyId': 'test-company', 'companyName': 'Test'}]}]}
        if '/reportsuites/' in url:
            return {'rsid': 'test-rsid', 'currency': 'KRW', 'timezoneZoneinfo': 'Asia/Seoul'}
        if '/dimensions?' in url or '/metrics?' in url:
            return [{'id': 'test-id', 'title': 'Test'}]
        requests.append(copy.deepcopy(payload))
        assert payload['rsid'] == 'test-rsid'
        bounds = payload['globalFilters'][0]['dateRange'].split('/')
        day = date.fromisoformat(bounds[0][:10])
        assert bounds[1] == f'{day + timedelta(days=1)}T00:00:00.000'
        values = [row for row in expected if row['date'] == day.isoformat()]
        container = payload['metricContainer']
        if payload['dimension'] == 'variables/marketingchannel':
            page = payload['settings']['page']
            labels = list(channel_map)[0:2] if page == 0 else list(channel_map)[2:]
            rows = [{'itemId': label[-1], 'value': label, 'data': [sum(row[m] for row in values if row['channel'] == channel_map[label])
                      for m in p.METRICS]} for label in labels]
            last = page == 1
        else:
            assert all(m['filters'] == ['0'] for m in container['metrics'])
            item = container['metricFilters'][0]
            assert item['dimension'] == 'variables/marketingchannel' and item['type'] == 'breakdown'
            ch = channel_map['Channel ' + item['itemId']]
            rows = [{'itemId': label[-1], 'value': label, 'data': [float(next(row[m] for row in values if row['channel'] == ch and row['device'] == device_map[label]))
                      for m in p.METRICS]} for label in device_map]
            last = True
        return {'columns': {'columnIds': ['0', '1', '2', '3']}, 'rows': rows, 'lastPage': last,
                'summaryData': {'totals': [sum(row[m] for row in values) for m in p.METRICS]}}
    def token(request, timeout):
        assert timeout == 30 and request.full_url == 'https://ims-na1.adobelogin.com/ims/token/v3'
        form = parse_qs(request.data.decode())
        assert form['client_secret'] == ['test-secret'] and form['grant_type'] == ['client_credentials']
        return io.BytesIO(b'{"access_token":"test-token","expires_in":3600}')
    with patch.dict(os.environ, env, clear=True), patch.object(adobe, 'urlopen', side_effect=token) as auth, patch.object(providers, 'request_json', side_effect=response):
        client = adobe.Client()
        metadata = client.check()
        assert metadata['authenticated'] and metadata['metrics'][0]['id'] == 'test-id'
        raw = client.collect(days)
        assert not raw['writes_database'] and len(raw['rows']) == 30
        assert adobe.normalized(raw, days) == expected
        assert auth.call_count == 1 and len(requests) == 14
        assert p.extract(days) == expected
        assert '가상' not in providers.llm_config()['prompt']
        for change, text in (({'currency': 'USD'}, '통화'), ({'timezoneZoneinfo': 'US/Pacific'}, '시간대')):
            altered = copy.deepcopy(raw); altered['suite'].update(change)
            fails(lambda: adobe.normalized(altered, days), text)
        altered = copy.deepcopy(raw); altered['rows'][0]['revenue_krw'] = 1.5
        fails(lambda: adobe.normalized(altered, days), '정수')
        altered = copy.deepcopy(raw); altered['rows'].pop()
        fails(lambda: adobe.normalized(altered, days), 'Incomplete source')
        altered = copy.deepcopy(raw); altered['totals'][str(days[0])]['visits'] += 1
        fails(lambda: adobe.normalized(altered, days), '합계')
        altered = copy.deepcopy(raw); altered['rows'][0]['channel'] = 'Unknown'
        fails(lambda: adobe.normalized(altered, days), '미매핑')
        with patch.dict(os.environ, {'ADOBE_MAPPING_CONFIRMED': 'false'}), patch.object(adobe.Client, 'collect') as collect:
            fails(lambda: p.extract(days), 'MAPPING_CONFIRMED'); collect.assert_not_called()
        with patch.object(providers, 'request_json', side_effect=[HTTPError('hidden',401,'test-secret',{},None), {'ok': True}]):
            assert client.api('metrics') == {'ok': True} and auth.call_count == 3
        with patch.object(providers, 'request_json', side_effect=[HTTPError('hidden',429,'test-secret',{},None), {'ok': True}]), patch.object(adobe.time, 'sleep') as sleep:
            assert client.api('metrics') == {'ok': True}; sleep.assert_called_once()
        with patch.object(providers, 'request_json', side_effect=HTTPError('hidden',403,'test-secret',{},None)):
            fails(lambda: client.api('metrics'), 'HTTP_403')
        with patch.object(providers, 'request_json', return_value={'rows': [], 'lastPage': False}):
            fails(lambda: client.report(days[0], 'variables/marketingchannel'), '응답')
        # Preflight must never connect to the DB, even with incomplete credentials.
        with patch.dict(os.environ, {'ADOBE_CLIENT_ID': ''}), patch.object(p, 'connect') as connect, patch('sys.argv', ['pipeline.py', 'adobe-check']):
            assert p.main() == 1; connect.assert_not_called()
    import web
    failure=web.subprocess.CompletedProcess([],1,'','2026-09-30 ERROR Adobe 요청 실패 (HTTP_403). 권한을 확인하세요.')
    with patch.object(web.subprocess,'run',return_value=failure):
        fails(lambda:web.worker('run'),'Adobe 요청 실패')
    print('Adobe offline contract checks passed')


if __name__ == '__main__':
    check()
