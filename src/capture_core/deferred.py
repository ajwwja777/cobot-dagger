"""Explicitly defer closed files, reserve indices and retain review receipts."""
import fcntl
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4
from datetime import datetime, timezone
import h5py

NAME = re.compile(r'episode_([0-9]{6})[.]hdf5(?:[.]incomplete)?$')

def confined(root, relative):
    root = Path(root).resolve(strict=True)
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('invalid_deferred_path')
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('deferred_symlink_refused')
    if root not in path.resolve().parents:
        raise ValueError('deferred_path_outside_root')
    return path

@contextmanager
def closed_file(path):
    fd = os.open(str(path), os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('recording_file_still_open') from error
        with os.fdopen(fd, 'r+b', closefd=False) as stream:
            yield stream
    finally:
        os.close(fd)

def metadata(path):
    info = path.stat()
    result = dict(relative_path=path.name, size_bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                  episode_index=int(NAME.fullmatch(path.name)[1]))
    try:
        with h5py.File(path, 'r') as h:
            result['episode_uuid'] = str(UUID(str(h.attrs['episode_uuid'])))
            result['completion_state'] = str(h.attrs.get('completion_state', 'incomplete'))
    except (OSError, KeyError, ValueError):
        result['completion_state'] = 'invalid'
    return result

def latest_blocker(root):
    root = Path(root)
    paths = [p for p in root.glob('episode_*.hdf5*') if NAME.fullmatch(p.name)
             and p.is_file() and not p.is_symlink()]
    if not paths:
        return None
    path = max(paths, key=lambda p: (int(NAME.fullmatch(p.name)[1]), p.name.endswith('.incomplete')))
    return metadata(path)

def atomic(path, payload):
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with temp.open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(temp), str(path))

def defer_file(root, expected):
    path = confined(root, expected['relative_path'])
    match = NAME.fullmatch(path.name)
    if not match or len(Path(expected['relative_path']).parts) not in (1, 4):
        raise ValueError('invalid_deferred_episode_name')
    with closed_file(path) as stream:
        info = os.fstat(stream.fileno())
        if (info.st_size != expected['size_bytes'] or info.st_mtime_ns != expected['mtime_ns']
                or path.stat().st_ino != info.st_ino):
            raise ValueError('recording_changed_check_again')
        uuid = expected.get('episode_uuid') or str(uuid4())
        uuid = str(UUID(uuid))
        # Lock is held on the native inode throughout rename. Corrupt HDF5
        # can also be retained; never clear writer flags or alter its bytes.
        try:
            with h5py.File(stream, 'r') as h:
                if str(h.attrs.get('episode_uuid', '')) != uuid:
                    raise ValueError('deferred_episode_identity_mismatch')
        except OSError:
            if expected.get('episode_uuid'):
                raise ValueError('recording_changed_check_again')
        folder = confined(root, str(path.parent.relative_to(root) / '.deferred' / uuid))
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / path.name
        if target.exists():
            raise ValueError('deferred_archive_collision')
        receipt = path.parent / ('episode_%06d.deferred.json' % int(match[1]))
        if receipt.exists() or receipt.is_symlink():
            raise ValueError('deferred_receipt_collision')
        stream.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        row = {**expected, 'sha256': digest.hexdigest(), 'episode_uuid': uuid, 'history_format': 'deferred',
               'archive_relative_path': str(target.relative_to(root)),
               'receipt_relative_path': str(receipt.relative_to(root)),
               'deferred_at': datetime.now(timezone.utc).isoformat(),
               'review_pending': True, 'episode_outcome': 'unknown',
               'keep_for_training': False, 'status': 'retaining'}
        atomic(receipt, row)
        try:
            os.rename(str(path), str(target))
        except OSError:
            if path.exists() and not target.exists():
                receipt.unlink()
            raise
        row['status'] = 'deferred'
        atomic(receipt, row)
        return row

def list_deferred(root):
    root = Path(root).resolve()
    result = []
    for pattern in ('episode_*.deferred.json', '*/*/*/episode_*.deferred.json'):
        for path in root.glob(pattern):
            try:
                path = confined(root, str(path.relative_to(root)))
                row = json.loads(path.read_text(encoding='utf-8'))
                UUID(row['episode_uuid'])
                if row.get('status') in {'retaining', 'deferred'} and row.get('receipt_relative_path') == str(path.relative_to(root)):
                    target = confined(root, row['archive_relative_path'])
                    if target.is_file() and target.stat().st_size == row['size_bytes']:
                        result.append({**row, 'status': 'deferred'})
            except (OSError, ValueError, KeyError):
                continue
    return result

def delete_deferred(root, uuid):
    rows = [r for r in list_deferred(root) if r['episode_uuid'] == str(UUID(uuid))]
    if len(rows) != 1:
        raise ValueError('deferred_episode_not_found')
    row = rows[0]
    path = confined(root, row['archive_relative_path'])
    with closed_file(path) as stream:
        info = os.fstat(stream.fileno())
        if (info.st_size != row['size_bytes'] or info.st_mtime_ns != row['mtime_ns']
                or path.stat().st_ino != info.st_ino):
            raise ValueError('deferred_recording_changed')
        stream.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        if digest.hexdigest() != row.get('sha256'):
            raise ValueError('deferred_recording_changed')
        path.unlink()
    # Preserve allocation/identity, even after an explicit historical delete.
    row.update(status='deleted', review_pending=False)
    atomic(confined(root, row['receipt_relative_path']), row)
    return {'deleted': True, 'episode_uuid': row['episode_uuid']}
