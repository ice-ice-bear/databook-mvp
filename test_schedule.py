"""KST scheduling checks without Docker, OS registration or cloud writes."""
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import schedule as s


def check():
    with tempfile.TemporaryDirectory() as tmp, patch.object(s,'ROOT',Path(tmp)),patch.object(s,'TARGET',Path(tmp)/'work/schedule.json'):
        assert not s.settings()['enabled']
        state=s.update(9,0,True)
        assert state['next_run'].endswith('+09:00')
        previous=s.TARGET.read_bytes()
        monday=datetime(2026,9,28,9,0,tzinfo=s.KST)
        assert s.next_run(9,0,monday,[0]).date().isoformat()=='2026-10-05'
        assert s.next_run(9,0,monday,[2,4]).date().isoformat()=='2026-09-30'
        assert s.next_run(9,0,monday.astimezone(timezone.utc),[2,4]).hour==9
        assert s.next_run(10,0,monday,[0]).date()==monday.date()
        for days in ([],[True],[7],[-1],[0,0],'월'):
            try:s.update(9,0,True,days)
            except ValueError:pass
            else:raise AssertionError('Invalid weekdays accepted')
            assert s.TARGET.read_bytes()==previous
        for hour,minute,enabled in [(24,0,True),(9,60,True),(True,0,True),(9,0,1)]:
            try: s.update(hour,minute,enabled)
            except ValueError: pass
            else: raise AssertionError('Invalid settings accepted')
            assert s.TARGET.read_bytes()==previous
        now=datetime(2026,9,30,9,0,tzinfo=s.KST)
        state.update(next_run=now.isoformat());s.save(state)
        lock=threading.Lock();lock.acquire()
        with patch.object(s.subprocess,'run') as run:
            s.tick(now,lock);run.assert_not_called()
        lock.release()
        result=subprocess.CompletedProcess([],0,stdout='ok',stderr='')
        with patch.object(s.subprocess,'run',return_value=result) as run:
            s.tick(now.astimezone(timezone.utc),lock)
            assert run.call_args.args[0][-2:]==['--date','2026-09-29']
            assert s.settings()['last_run']['status']=='succeeded' and not lock.locked()
            assert s.settings()['next_run']==(now+timedelta(days=1)).isoformat()
            # Saving another time on the same day must not run twice.
            data=s.settings();data['next_run']=now.isoformat();s.save(data)
            s.tick(now,lock);assert run.call_count==1
        data=s.settings();data['next_run']=(now+timedelta(days=1)).isoformat();s.save(data)
        with patch.object(s.subprocess,'run',side_effect=subprocess.TimeoutExpired([],330)):
            s.tick(now+timedelta(days=1),lock)
            assert s.settings()['last_run']['status']=='failed' and not s.settings()['running']
        data=s.settings();data['next_run']=now.isoformat();s.save(data)
        with patch.object(s.subprocess,'run') as run:
            s.tick(now+timedelta(days=3));run.assert_not_called()  # No historical backfill.
        data=s.settings();data.update(query_id='saved-query',next_run=(now+timedelta(days=5)).isoformat());s.save(data)
        with patch.object(s.subprocess,'run',return_value=result) as run:
            s.tick(now+timedelta(days=5),lock)
            assert run.call_args.args[0][-2:]==['--query-id','saved-query']
        s.update(10,15,False,[0,2,4]);assert s.settings()['next_run'] is None
        assert s.settings()['weekdays']==[0,2,4]
        # A due date on an unselected weekday must never launch a worker.
        data=s.settings();data.update(enabled=True,next_run=(now+timedelta(days=3)).isoformat(),weekdays=[0]);s.save(data)
        with patch.object(s.subprocess,'run') as run:
            s.tick(now+timedelta(days=3));run.assert_not_called()
        data=s.settings();data.update(running=True,last_run={'status':'running','started_at':datetime.now(s.KST).isoformat()});s.save(data)
        try: s.update(9,0,False)
        except ValueError: pass
        else: raise AssertionError('Running task settings changed')
        data['last_run']['started_at']=(datetime.now(s.KST)-timedelta(minutes=7)).isoformat();s.save(data)
        assert s.settings()['last_run']['status']=='interrupted'
    print('PASS: weekday selection, KST across host timezones, validation, busy lock, once/day, failure, missed days and interrupted jobs')


if __name__=='__main__':check()
