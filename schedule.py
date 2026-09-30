"""Cross-platform weekday scheduler. Uses KST and local JSON settings, no OS registration."""
import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT/'work/schedule.json'
KST = timezone(timedelta(hours=9), 'KST')


def next_run(hour, minute, now, weekdays=tuple(range(7))):
    now=now.astimezone(KST)
    for offset in range(8):
        due=(now+timedelta(days=offset)).replace(hour=hour,minute=minute,second=0,microsecond=0)
        if due > now and due.weekday() in weekdays:
            return due
    raise ValueError('실행할 요일을 하나 이상 선택하세요.')


def settings():
    if TARGET.exists():
        data=json.loads(TARGET.read_text(encoding='utf-8'))
        data.setdefault('weekdays',list(range(7)))
        data.setdefault('query_id','')
        if data.get('running') and (datetime.now(KST)-datetime.fromisoformat(data['last_run']['started_at'])).total_seconds()>360:
            data['running']=False
            data['last_run']['status']='interrupted'
        return data
    return {'hour':9, 'minute':0, 'enabled':False, 'timezone':'Asia/Seoul (KST, UTC+09:00)',
            'next_run':None, 'running':False, 'last_run':None, 'weekdays':list(range(7)), 'query_id':''}


def save(data):
    TARGET.parent.mkdir(exist_ok=True)
    temp=TARGET.with_name(f'.schedule-{os.getpid()}-{threading.get_ident()}.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(TARGET)


def update(hour, minute, enabled, weekdays=None, query_id=None):
    if type(enabled) is not bool:
        raise ValueError('예약 사용 여부를 확인하세요.')
    if type(hour) is not int or type(minute) is not int or not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError('실행 시각은 00:00~23:59로 설정하세요.')
    current=settings()
    if query_id is not None:
        if query_id:
            from query_workspace import selected
            selected(query_id)
        current['query_id']=query_id
    weekdays=current['weekdays'] if weekdays is None else weekdays
    if (not isinstance(weekdays,list) or not 1 <= len(weekdays) <= 7 or
            any(type(d) is not int or not 0 <= d <= 6 for d in weekdays) or len(set(weekdays))!=len(weekdays)):
        raise ValueError('실행할 요일을 하나 이상 선택하세요 (월~일).')
    if current['running']:
        raise ValueError('예약 작업 실행 중입니다. 완료 후 설정을 변경하세요.')
    current.update(hour=hour,minute=minute,enabled=enabled,weekdays=sorted(weekdays),
                   next_run=next_run(hour,minute,datetime.now(KST),weekdays).isoformat() if enabled else None)
    save(current)
    return current


def tick(now=None, busy=None):
    now=(now or datetime.now(KST)).astimezone(KST)
    data=settings()
    if not data['enabled'] or not data['next_run']:
        return
    due=datetime.fromisoformat(data['next_run'])
    if now < due:
        return
    if due.date() < now.date() or now.weekday() not in data['weekdays']:
        # ponytail: no historical backfill; use manual reports for days missed while stopped.
        data['next_run']=next_run(data['hour'],data['minute'],now,data['weekdays']).isoformat()
        save(data)
        return
    if busy and not busy.acquire(blocking=False):
        return
    try:
        # One attempt per KST day even when web and standalone schedulers run together.
        claim=ROOT/'work'/f'schedule_{now.date()}.claim'
        try:
            claim.open('x').close()
        except FileExistsError:
            data=settings()
            if not data['running']:
                data['next_run']=next_run(data['hour'],data['minute'],now,data['weekdays']).isoformat()
                save(data)
            return
        day=(now.date()-timedelta(days=1)).isoformat()
        data.update(running=True,next_run=next_run(data['hour'],data['minute'],now,data['weekdays']).isoformat(),
                    last_run={'report_date':day,'status':'running','started_at':now.isoformat()})
        save(data)
        try:
            result=subprocess.run([sys.executable,str(ROOT/'sync_onedrive.py'),'--run','--date',day,*(['--query-id',data['query_id']] if data['query_id'] else [])],
                                  cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',
                                  env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=330)
            (ROOT/'logs').mkdir(exist_ok=True)
            for name,content in [('out',result.stdout),('err',result.stderr)]:
                with (ROOT/'logs'/f'schedule.{name}.log').open('a',encoding='utf-8') as log:
                    log.write(f'\n[{now.isoformat()}]\n'+content)
            status='succeeded' if result.returncode==0 else 'failed'
            manifest=ROOT/'reports'/f'daily_report_{day}.json'
            if status=='succeeded' and manifest.exists() and json.loads(manifest.read_text(encoding='utf-8')).get('analysis',{}).get('status') in ('failed','not_configured'):
                status='partial'  # Numeric Excel can succeed while the configured LLM fails.
            data['last_run'].update(status=status,exit_code=result.returncode)
        except (OSError,subprocess.TimeoutExpired,ValueError) as error:
            data['last_run'].update(status='failed',error=type(error).__name__)
        finally:
            data['running']=False
            data['last_run']['finished_at']=datetime.now(KST).isoformat()
            save(data)
    finally:
        if busy:
            busy.release()


def serve(stop, busy=None):
    # ponytail: one local scheduler, no retries or queue; add durable jobs for unattended server use.
    while not stop.is_set():
        try:
            tick(busy=busy)
        except (OSError,ValueError,KeyError):
            print('Scheduler settings unavailable. Check work/schedule.json.',file=sys.stderr)
        stop.wait(15)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve',action='store_true')
    args=parser.parse_args()
    if args.serve:
        try: serve(threading.Event())
        except KeyboardInterrupt: pass
    else:
        print(json.dumps(settings(),ensure_ascii=False,indent=2))
