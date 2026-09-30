"""HTTP checks with fake worker output; no paid API calls or cloud writes."""
import http.client
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import web


def check():
    server = web.ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(method, path, body=None, extra=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        headers = {'Content-Type': 'application/json', 'X-Databook-Token': web.TOKEN, **(extra or {})}
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        data = response.read()
        status = response.status
        conn.close()
        return status, data
    try:
        assert request('GET', '/')[0] == 200
        assert request('GET', '/questions')[0] == 200
        assert request('GET', '/admin')[0] == 200
        assert request('GET','/assets/logo.svg')[0]==200
        assert request('GET','/assets/../.env')[0]==404
        with patch.object(web.workspace,'catalog',return_value=[]):assert request('GET','/api/queries')[0]==200
        with patch.object(web,'worker',return_value='{}'):assert request('GET','/api/tables')[0]==200
        with tempfile.TemporaryDirectory() as tmp, patch.object(web.workspace,'STORE',Path(tmp)/'queries.json'), patch.object(web.workspace,'PIPELINE_STORE',Path(tmp)/'pipeline_sql.json'), patch.object(web.schedule,'settings',return_value={'running':False}):
            body={'date':'2026-09-29','title':'분석','sql':'SELECT 1 AS value'}
            with patch.object(web,'worker',return_value='{"columns":["value"],"rows":[{"value":1}],"truncated":false}') as run:
                saved=json.loads(request('POST','/api/queries',body)[1])['query']
                assert run.call_count==1
                assert json.loads(request('POST','/api/queries',dict(body,id=saved['id']))[1])['query']['id']==saved['id']
                assert run.call_count==2
                builtin=web.workspace.catalog()[0]
                assert request('POST','/api/queries',dict(body,id=builtin['id']))[0]==200
                assert web.workspace.selected(builtin['id'])['sql']==body['sql']
            before=web.workspace.STORE.read_bytes()
            with patch.object(web,'worker',side_effect=ValueError('SQL 실행 실패')):
                assert request('POST','/api/queries',dict(body,id=saved['id'],sql='SELECT missing'))[0]==400
                assert web.workspace.STORE.read_bytes()==before
            file=web.workspace.pipeline_files()[0]
            stage={'date':'2026-09-29','name':file['name'],'sql':file['sql']}
            with patch.object(web,'worker',return_value='{"validated":true,"columns":[],"rows":[],"truncated":false}') as run:
                assert request('POST','/api/sql-files',stage)[0]==200 and run.call_count==1
                assert run.call_args.args[0]=='pipeline-preview'
            before=web.workspace.PIPELINE_STORE.read_bytes()
            with patch.object(web,'worker',side_effect=ValueError('검증 실패')):
                assert request('POST','/api/sql-files',stage)[0]==400
                assert web.workspace.PIPELINE_STORE.read_bytes()==before
        with tempfile.TemporaryDirectory() as tmp, patch.object(web.sync,'ROOT',Path(tmp)), patch.object(web.workspace,'AGGREGATION',Path(tmp)/'work/aggregation.json'), patch.object(web.schedule,'settings',return_value={'running':False}):
            assert request('POST','/api/onedrive',{'folder':tmp})[0]==200
            assert json.loads(request('GET','/api/onedrive')[1])['ready']
            assert request('POST','/api/onedrive',{'folder':'relative'})[0]==400
            assert json.loads(request('GET','/api/onedrive')[1])['folder']==tmp
            sql=web.workspace.aggregation_settings()['default_sql']
            body={'date':'2026-09-29','sql':sql}
            with patch.object(web,'worker',return_value='{"validated":true,"rows":[],"columns":[]}') as run:
                assert request('POST','/api/aggregation-preview',body)[0]==200
                assert not web.workspace.AGGREGATION.exists()
                assert request('POST','/api/aggregation',body)[0]==200
                assert run.call_args.args==('aggregation-preview','--sql',sql,'--date','2026-09-29')
                assert json.loads(request('GET','/api/aggregation')[1])['sql']==sql
                saved=web.workspace.AGGREGATION.read_bytes()
            with patch.object(web,'worker',side_effect=ValueError('원본과 집계 합계가 다릅니다.')):
                assert request('POST','/api/aggregation',dict(body,sql=sql.replace('SUM(visits)','SUM(visits)+1')))[0]==400
                assert web.workspace.AGGREGATION.read_bytes()==saved
            assert request('POST','/api/aggregation',dict(body,sql='DELETE FROM mvp_raw_daily'))[0]==400
            with patch.object(web.schedule,'settings',return_value={'running':True}):
                assert request('POST','/api/onedrive',{'folder':''})[0]==400
        assert request('POST','/api/query',{'date':'2026-09-29','sql':'DELETE FROM mvp_raw_daily'})[0]==400
        assert request('POST','/api/table-preview',{'date':'2026-09-29','table':None})[0]==400
        with patch.object(web,'worker',return_value='{"rows":[],"columns":[]}') as run:
            assert request('POST','/api/table-preview',{'date':'2026-09-29','table':'mvp_history_daily'})[0]==200
            assert run.call_args.args==('table-preview','--table','mvp_history_daily','--date','2026-09-29')
        with patch.object(web.schedule, 'settings', return_value={'enabled':False}):
            assert json.loads(request('GET','/api/schedule')[1])['enabled'] is False
        with patch.object(web.schedule, 'update', return_value={'enabled':True}) as update:
            assert request('POST','/api/schedule',{'hour':9,'minute':30,'enabled':True})[0]==200
            update.assert_called_once_with(9,30,True,None,None)
            update.reset_mock()
            assert request('POST','/api/schedule',{'hour':9,'minute':30,'enabled':True,'weekdays':[0,2,4]})[0]==200
            update.assert_called_once_with(9,30,True,[0,2,4],None)
        assert request('GET', '/.env')[0] == 404
        assert request('GET', '/reports/%2e%2e%2f.env')[0] == 404
        assert request('GET', '/', extra={'Host': 'evil.example'})[0] == 403
        assert request('GET', '/', extra={'Sec-Fetch-Site': 'cross-site'})[0] == 403
        body = {'date': '2026-09-29', 'question': 'compare'}
        assert request('POST', '/api/ask', body, {'X-Databook-Token': ''})[0] == 403
        assert request('POST', '/api/ask', body, {'Origin': 'https://evil.example'})[0] == 403
        assert request('POST', '/api/ask', {'date': 'invalid'})[0] == 400
        with patch.object(web, 'worker', return_value=json.dumps({'answer': '<script>text</script>', 'rows': 30})) as run:
            status, data = request('POST', '/api/ask', body)
            assert status == 200 and json.loads(data)['rows'] == 30
            assert run.call_args.args == ('ask', '--date', '2026-09-29', '--', 'compare')
            assert request('POST','/api/ask',dict(body,query_id='table:mvp_history_daily'))[0]==200
            assert run.call_args.args==('query-answer','--id','table:mvp_history_daily','--date','2026-09-29','--','compare')
        web.BUSY.acquire()
        try:
            assert request('POST', '/api/ask', body)[0] == 409
        finally:
            web.BUSY.release()
        with patch.object(web, 'worker', return_value=''), patch.object(web, 'report_summary', return_value={'file': 'test.xlsx'}):
            with patch.object(web.sync, 'configured_folder', return_value=''):
                assert json.loads(request('POST', '/api/report', {'date': '2026-09-29'})[1])['copy_status'] == 'not_configured'
            with patch.object(web.sync, 'configured_folder', return_value='/example'), patch.object(web.sync, 'copy_report', side_effect=OSError):
                assert json.loads(request('POST', '/api/report', {'date': '2026-09-29'})[1])['copy_status'] == 'failed'
        with tempfile.TemporaryDirectory() as tmp, patch.object(web, 'ROOT', Path(tmp)):
            reports = Path(tmp)/'reports'
            reports.mkdir()
            source = Path(tmp)/'secret'
            source.write_text('private')
            (reports/'daily_report_2026-09-29.xlsx').symlink_to(source)
            assert request('GET', '/reports/daily_report_2026-09-29.xlsx')[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print('PASS: local HTTP, CSRF/host guard, inputs, no secret/path downloads, Q&A dispatch, busy and copy failure')


if __name__ == '__main__':
    check()
