"""Local browser UI around the existing Compose worker. Run: make web."""
import argparse
import hashlib
import json
import re
import secrets
import subprocess
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import sync_onedrive as sync
import schedule
import query_workspace as workspace

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_hex(24)
BUSY = threading.Lock()
REPORT_NAME = re.compile(r'daily_report_\d{4}-\d{2}-\d{2}(?:_v[2-9]\d*|_v1\d+)?\.xlsx')


def report_summary(day):
    manifest = ROOT/'reports'/f'daily_report_{day}.json'
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text(encoding='utf-8'))
    name = data['file']
    if not REPORT_NAME.fullmatch(name):
        raise ValueError('Invalid report filename')
    path = ROOT/'reports'/name
    if path.is_symlink() or not path.is_file():
        raise ValueError('Report file unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest() != data['file_sha256']:
        raise ValueError('Report checksum mismatch')
    return {k: data.get(k) for k in ('file', 'report_date', 'comparison_date', 'generated_at', 'totals', 'analysis', 'kind', 'query_title', 'preview')} | {
        'source': data['identity']['source']}


def index_data():
    reports = []
    for path in sorted((ROOT/'reports').glob('daily_report_????-??-??.json'), reverse=True):
        try:
            day = date.fromisoformat(path.stem.removeprefix('daily_report_'))
            reports.append(report_summary(day))
        except (ValueError, KeyError, OSError):
            continue
    reports = [r for r in reports if r]
    folder = sync.configured_folder()
    return {'reports': reports, 'default_date': reports[0]['report_date'] if reports else
            (datetime.now(timezone(timedelta(hours=9), 'KST')).date()-timedelta(days=1)).isoformat(),
            'onedrive': 'ready' if folder and Path(folder).expanduser().is_dir() else 'not_configured'}


def worker(*args):
    # ponytail: one local request at a time, no job queue; add a queue for multi-user work.
    result = subprocess.run(['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.demo.yaml',
                             'run', '--rm', 'worker', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=150)
    if result.returncode:
        error = result.stderr
        if 'Incomplete source' in error:
            raise ValueError(error.split('Incomplete source:', 1)[1].splitlines()[0].strip())
        if 'configuration changed' in error:
            raise ValueError('데이터 또는 SQL·LLM 설정이 바뀌었습니다. 새 버전으로 생성 옵션을 선택하세요.')
        for line in error.splitlines():
            if ' ERROR ' in line and any(message in line for message in ('조회 조건', '조회 날짜', '조회 기간', '허용되지 않은 집계')):
                raise ValueError(line.split(' ERROR ', 1)[1])
        if '연결된 DB의 테이블을 선택하세요.' in error:raise ValueError('연결된 DB의 테이블을 선택하세요.')
        for line in error.splitlines():
            if ' ERROR ' in line and any(message in line for message in ('집계 출력 컬럼은', '집계 날짜와 지표 타입을', '보고일·7일 전의', '보고일과 7일 전의', '원본과 집계 합계가', '지원 날짜 변수','파이프라인 ')):
                raise ValueError(line.split(' ERROR ',1)[1])
        codes = re.findall(r'HTTP_\d{3}', error)
        if codes:
            raise ValueError(f'AI 요청이 실패했습니다 ({codes[-1]}). API 키·모델·사용 한도를 확인하세요.')
        if 'LLM answer unavailable' in error or 'Set LLM_PROVIDER' in error:
            raise ValueError('AI 연결을 확인하세요. .env의 공급자·모델·API 키를 설정한 뒤 다시 질문하세요.')
        if any(kind in error for kind in ('ProgrammingError','OperationalError')):
            raise ValueError('SQL을 실행하지 못했습니다. 테이블·컬럼·날짜 변수를 확인하세요.')
        raise RuntimeError('실행하지 못했습니다. Docker Desktop과 DB 상태를 확인하세요. 실행 기록은 logs에 남습니다.')
    return result.stdout


def action(route, body):
    if not isinstance(body, dict):
        raise ValueError('Invalid request')
    if route in ('/api/onedrive','/api/aggregation','/api/sql-files','/api/queries') and schedule.settings()['running']:
        raise ValueError('예약 보고서를 실행 중입니다. 완료 후 설정을 변경하세요.')
    if route == '/api/schedule':
        return schedule.update(body.get('hour'), body.get('minute'), body.get('enabled'), body.get('weekdays'), body.get('query_id'))
    if route=='/api/onedrive':
        return sync.save_folder(body.get('folder'))
    day = date.fromisoformat(body.get('date', ''))
    if route=='/api/queries':
        sql=workspace.validate_sql(body.get('sql'))
        result=json.loads(worker('query','--date',day.isoformat(),'--sql',sql))
        return {'query':workspace.save_query(body.get('title'),sql,body.get('id')),'preview':result}
    if route in ('/api/sql-files','/api/pipeline-preview'):
        name,sql=body.get('name'),body.get('sql')
        workspace.validate_pipeline_sql(name,sql)
        result=json.loads(worker('pipeline-preview','--name',name,'--sql',sql,'--date',day.isoformat()))
        return {'files':workspace.save_pipeline_sql(name,sql),'preview':result} if route=='/api/sql-files' else result
    if route in ('/api/aggregation-preview','/api/aggregation'):
        sql=workspace.validate_sql(body.get('sql'))
        result=json.loads(worker('aggregation-preview','--sql',sql,'--date',day.isoformat()))
        return workspace.save_aggregation(sql) if route=='/api/aggregation' else result
    if route=='/api/table-preview':
        name=body.get('table')
        if not isinstance(name,str) or not name or len(name)>64:raise ValueError('테이블을 선택하세요.')
        return json.loads(worker('table-preview','--table',name,'--date',day.isoformat()))
    if route=='/api/query':
        return json.loads(worker('query','--date',day.isoformat(),'--sql',workspace.validate_sql(body.get('sql'))))
    if route == '/api/ask':
        question = body.get('question', '')
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('질문을 1~2,000자로 입력하세요.')
        if body.get('query_id'):
            if not isinstance(body['query_id'],str):raise ValueError('조회 쿼리를 선택하세요.')
            if not body['query_id'].startswith('table:'):workspace.selected(body['query_id'])
            return json.loads(worker('query-answer','--id',body['query_id'],'--date',day.isoformat(),'--',question))
        return json.loads(worker('ask', '--date', day.isoformat(), '--', question))
    if route == '/api/report':
        new_version = body.get('new_version', False)
        if not isinstance(new_version, bool):
            raise ValueError('Invalid version option')
        query_id=body.get('query_id','')
        if query_id:workspace.selected(query_id)
        worker(*(['query-report','--id',query_id] if query_id else ['run']), '--date', day.isoformat(), *(['--regenerate'] if new_version else []))
        copied = 'not_configured'
        message = 'OneDrive 폴더가 설정되지 않아 로컬에 저장했습니다.'
        folder = sync.configured_folder()
        if folder:
            try:
                _, copied = sync.copy_report(day, folder)
                message = 'OneDrive 폴더 복사 완료. 클라우드 업로드 상태는 OneDrive 앱에서 확인하세요.'
            except (ValueError, OSError, KeyError):
                copied = 'failed'
                message = '보고서는 생성됐지만 OneDrive 복사가 실패했습니다. 폴더 경로·권한을 확인하세요.'
        return {'report': report_summary(day), 'copy_status': copied, 'message': message}
    raise ValueError('Unknown action')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Questions, request bodies and credentials never enter HTTP logs.

    def allowed(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        return self.headers.get('Host') in hosts and self.headers.get('Sec-Fetch-Site') != 'cross-site'

    def respond(self, code, content, content_type='application/json; charset=utf-8', filename=None):
        data = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', f"default-src 'self'; script-src 'nonce-{TOKEN}'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed():
            self.respond(403, {'error': 'Local access only'})
            return
        route = urlsplit(self.path).path
        try:
            if route in ('/', '/questions', '/admin'):
                html = (ROOT/'web/index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
                self.respond(200, html.encode(), 'text/html; charset=utf-8')
            elif route == '/assets/logo.svg':
                self.respond(200,(ROOT/'web/assets/logo.svg').read_bytes(),'image/svg+xml')
            elif route == '/api/reports':
                self.respond(200, index_data())
            elif route == '/api/tables':
                self.respond(200,json.loads(worker('tables')))
            elif route == '/api/queries':
                self.respond(200,workspace.catalog())
            elif route == '/api/onedrive':
                self.respond(200,sync.folder_settings())
            elif route == '/api/aggregation':
                self.respond(200,workspace.aggregation_settings())
            elif route == '/api/sql-files':
                self.respond(200,workspace.pipeline_files())
            elif route == '/api/schedule':
                self.respond(200, schedule.settings())
            elif route.startswith('/reports/'):
                name = unquote(route.removeprefix('/reports/'))
                if not REPORT_NAME.fullmatch(name):
                    self.respond(404, {'error': 'File not found'})
                    return
                file = ROOT/'reports'/name
                if file.is_symlink() or not file.is_file():
                    self.respond(404, {'error': 'File not found'})
                    return
                self.respond(200, file.read_bytes(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', name)
            else:
                self.respond(404, {'error': 'Not found'})
        except (ValueError, KeyError, OSError, RuntimeError, subprocess.TimeoutExpired):
            self.respond(500, {'error': '테이블 조회에 실패했습니다. Docker와 DB 연결을 확인하세요.' if route=='/api/tables' else '보고서 파일을 확인할 수 없습니다. 로컬 reports 폴더를 확인하세요.'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        if not self.allowed() or self.headers.get('X-Databook-Token') != TOKEN or (
                origin and origin != 'http://'+self.headers.get('Host', '')):
            self.respond(403, {'error': 'Request rejected'})
            return
        route = urlsplit(self.path).path
        if route not in ('/api/ask', '/api/report', '/api/schedule', '/api/query', '/api/queries','/api/table-preview','/api/onedrive','/api/aggregation','/api/aggregation-preview','/api/sql-files','/api/pipeline-preview'):
            self.respond(404, {'error': 'Not found'})
            return
        if not BUSY.acquire(blocking=False):
            self.respond(409, {'error': '다른 작업을 실행 중입니다. 완료 후 다시 시도하세요.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16000 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Invalid request body')
            body = json.loads(self.rfile.read(length))
            self.respond(200, action(route, body))
        except (ValueError, TypeError) as error:
            self.respond(400, {'error': str(error) if isinstance(error, ValueError) else '날짜와 입력을 확인하세요.'})
        except subprocess.TimeoutExpired:
            self.respond(504, {'error': '응답 시간이 초과됐습니다. 보고서 목록과 실행 기록을 확인한 뒤 다시 시도하세요.'})
        except (RuntimeError, OSError, KeyError):
            self.respond(503, {'error': '실행하지 못했습니다. Docker Desktop과 로컬 설정을 확인하세요.'})
        finally:
            BUSY.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    stop=threading.Event()
    scheduler=threading.Thread(target=schedule.serve,args=(stop,BUSY),daemon=True)
    scheduler.start()
    print(f'Databook: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
