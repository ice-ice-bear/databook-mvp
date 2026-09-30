"""Host-only checks; never connects to OneDrive or an LLM."""
import hashlib
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sync_onedrive as sync


def fails(call, kind=ValueError):
    try:
        call()
    except kind:
        return
    raise AssertionError('Expected failure')


def check():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reports, destination = root/'reports', root/'OneDrive Personal'
        reports.mkdir()
        destination.mkdir()
        day = date(2026, 9, 29)
        name = f'daily_report_{day}.xlsx'
        content = b'example completed report'
        (reports/name).write_bytes(content)
        manifest = reports/f'daily_report_{day}.json'
        manifest.write_text(json.dumps({'file': name, 'file_sha256': hashlib.sha256(content).hexdigest()}))
        target, status = sync.copy_report(day, str(destination), reports)
        assert status == 'copied_local' and target.read_bytes() == content
        assert sync.copy_report(day, str(destination), reports)[1] == 'already_copied'
        target.write_bytes(b'user edit')
        fails(lambda: sync.copy_report(day, str(destination), reports))
        assert target.read_bytes() == b'user edit'
        fails(lambda: sync.copy_report(day, str(root/'missing'), reports))
        fails(lambda: sync.copy_report(day, 'relative', reports))
        target.unlink()
        with patch.object(sync.os, 'fsync', side_effect=OSError('disk full')):
            fails(lambda: sync.copy_report(day, str(destination), reports), OSError)
        assert not target.exists() and (reports/name).read_bytes() == content
        (reports/name).write_bytes(b'corrupt')
        fails(lambda: sync.copy_report(day, str(destination), reports))
        with patch.object(sync, 'ROOT', root), patch.dict(sync.os.environ, {}, clear=True):
            (root/'.env').write_text('OPENAI_API_KEY=do-not-export\nONEDRIVE_DIR="/tmp/folder with spaces"\n')
            assert sync.configured_folder() == '/tmp/folder with spaces'
            with patch.dict(sync.os.environ, {'ONEDRIVE_DIR': ''}):
                assert sync.configured_folder() == ''
            saved=sync.save_folder(str(destination))
            assert saved=={'folder':str(destination),'ready':True}
            with patch.dict(sync.os.environ, {'ONEDRIVE_DIR': '/env-fallback'}):
                assert sync.configured_folder()==str(destination)
            fails(lambda:sync.save_folder('relative'))
            fails(lambda:sync.save_folder(str(root/'missing')))
            with patch.object(sync.tempfile,'NamedTemporaryFile',side_effect=OSError):
                fails(lambda:sync.save_folder(str(destination)))
            assert sync.configured_folder()==str(destination)
            assert not list(destination.glob('.databook-check-*'))
            assert sync.save_folder('')=={'folder':'','ready':False}
    print('PASS: OneDrive local copy, duplicate, no overwrite, missing path, rollback, checksum and config')


if __name__ == '__main__':
    check()
