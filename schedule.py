"""Write, but do not register, a macOS launchd schedule for yesterday's mock report."""
import plistlib
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if sys.platform != 'darwin':
    raise SystemExit('On Linux use cron/systemd; on Windows use Task Scheduler. See README.')
docker = shutil.which('docker')
if not docker:
    raise SystemExit('Docker CLI is required.')
(root/'logs').mkdir(exist_ok=True)
config = {
    'Label': 'local.databook-mvp.daily',
    'ProgramArguments': [docker, 'compose', '-f', str(root/'compose.yaml'), '-f',
                        str(root/'compose.demo.yaml'), 'run', '--rm', 'worker', 'run'],
    'WorkingDirectory': str(root),
    'StartCalendarInterval': {'Hour': 9, 'Minute': 0},
    'EnvironmentVariables': {'PATH': '/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin'},
    'StandardOutPath': str(root/'logs/schedule.out.log'),
    'StandardErrorPath': str(root/'logs/schedule.err.log'),
}
target = root/'work/local.databook-mvp.daily.plist'
target.parent.mkdir(exist_ok=True)
with target.open('wb') as handle:
    plistlib.dump(config, handle)
print(target)
print('Schedule generated, NOT installed. Runs at 09:00 in the Mac system timezone; '
      'report date is yesterday in Asia/Seoul. Docker Desktop must be running.')
