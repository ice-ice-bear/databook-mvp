"""Copy a completed report to a local OneDrive folder; OneDrive handles upload."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def configured_folder():
    settings=ROOT/'work/onedrive.json'
    if settings.exists():return json.loads(settings.read_text(encoding='utf-8'))['folder']
    # Only this setting is used; never export or print the .env contents.
    if 'ONEDRIVE_DIR' in os.environ:
        return os.environ['ONEDRIVE_DIR'].strip()
    env = ROOT / '.env'
    if env.exists():
        with env.open(encoding='utf-8') as handle:
            for line in handle:
                key, separator, value = line.partition('=')
                if separator and key.strip() == 'ONEDRIVE_DIR':
                    return value.strip().strip('\"\'')
    return ''


def folder_settings():
    folder=configured_folder()
    return {'folder':folder,'ready':bool(folder and Path(folder).expanduser().is_dir())}


def save_folder(folder):
    if not isinstance(folder,str) or len(folder)>4096:raise ValueError('OneDrive 폴더의 전체 경로를 입력하세요.')
    folder=folder.strip()
    if folder:
        path=Path(folder).expanduser()
        if not path.is_absolute() or not path.is_dir():raise ValueError('이미 존재하는 OneDrive 동기화 폴더의 전체 경로를 입력하세요.')
        try:
            with tempfile.NamedTemporaryFile(dir=path,prefix='.databook-check-'):pass
        except OSError:raise ValueError('이 폴더에 쓸 수 없습니다. 폴더 권한을 확인하세요.') from None
        folder=str(path)
    import pipeline as p
    target=ROOT/'work/onedrive.json';target.parent.mkdir(exist_ok=True)
    p.atomic_json(target,{'folder':folder})
    return folder_settings()


def copy_report(day, folder, reports=ROOT / 'reports'):
    destination = Path(folder).expanduser()
    if not destination.is_absolute() or not destination.is_dir():
        raise ValueError('OneDrive folder must be an existing absolute path. Configure the synced folder in web settings.')
    manifest = json.loads((reports / f'daily_report_{day}.json').read_text(encoding='utf-8'))
    name = manifest['file']
    if Path(name).name != name or not name.endswith('.xlsx'):
        raise ValueError('Invalid report filename in manifest')
    source = reports / name
    if source.is_symlink():
        raise ValueError('Report symlinks are not supported')
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != manifest['file_sha256']:
        raise ValueError('Report checksum mismatch; regenerate the report first')
    target = destination / name
    # Exclusive creation preserves cloud/user edits and concurrent publications.
    try:
        handle = target.open('xb')
    except FileExistsError:
        if not target.is_symlink() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            return target, 'already_copied'
        raise ValueError('OneDrive already contains a different file with this name. Generate a new report version.') from None
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target, 'copied_local'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat,
                        default=datetime.now(timezone(timedelta(hours=9), 'KST')).date()-timedelta(days=1))
    parser.add_argument('--query-id',default='')
    parser.add_argument('--run', action='store_true', help='Run the daily pipeline before copying (scheduler entry point)')
    args = parser.parse_args()
    try:
        if args.run:
            docker = shutil.which('docker')
            if not docker:
                raise ValueError('Docker CLI is required')
            subprocess.run([docker, 'compose', '-f', 'compose.yaml', '-f', 'compose.demo.yaml',
                            'up', '-d', '--wait', 'db', 'example-api'], cwd=ROOT, check=True, timeout=120)
            subprocess.run([docker, 'compose', '-f', 'compose.yaml', '-f', 'compose.demo.yaml',
                            'run', '--rm', 'worker', *(['query-report','--id',args.query_id,'--refresh'] if args.query_id else ['run']), '--date', args.date.isoformat()], cwd=ROOT, check=True, timeout=180)
        folder = configured_folder()
        if not folder:
            print('OneDrive copy disabled: configure a folder in web settings. Local report is preserved.')
            return 0
        target, status = copy_report(args.date, folder)
        print(f'{status}: {target}')
        print('Local copy only. Confirm cloud sync completion in the OneDrive app.')
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f'OneDrive copy failed ({type(error).__name__}). Local report is preserved.', file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
