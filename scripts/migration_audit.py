"""Hash files and check SQLite before/after a stopped-server project move."""
import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    files, links = {}, {}
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(current) / name
            if path.stat(follow_symlinks=False).st_file_attributes & 0x400:
                links[str(path.relative_to(root))] = str(path.resolve())
                dirs.remove(name)
        for name in names:
            path = Path(current) / name
            files[str(path.relative_to(root))] = {'size': path.stat().st_size, 'sha256': digest(path)}
    databases = {}
    for name in ('food_reviews.sqlite3', 'demo_tunnel.sqlite3'):
        path = root / 'instance' / name
        # Caller must stop writers and checkpoint WAL before this audit.
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                raise ValueError(f'Database integrity failed: {name}')
            tables = ['restaurants', 'reviews', 'accounts', 'user_feedback', 'assistant_messages']
            counts = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables}
            account_digest = hashlib.sha256(repr(db.execute('SELECT * FROM accounts ORDER BY id').fetchall()).encode()).hexdigest()
            databases[name] = {'integrity': integrity, 'counts': counts, 'account_digest': account_digest}
    return {'root': str(root), 'files': files, 'links': links, 'databases': databases}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    snapshot = inventory(args.root.resolve())
    if args.verify:
        original = json.loads(args.manifest.read_text(encoding='utf-8'))
        for key in ('files', 'links', 'databases'):
            if original[key] != snapshot[key]:
                if key == 'files':
                    differences = [p for p in set(original[key]) | set(snapshot[key]) if original[key].get(p) != snapshot[key].get(p)]
                    print('Changed paths:', differences[:25])
                raise SystemExit(f'Migration mismatch in {key}; keep source and investigate')
        print(json.dumps({'verified_files': len(snapshot['files']), 'databases': snapshot['databases']}))
    else:
        if args.manifest.exists():
            raise SystemExit('Manifest exists; do not overwrite the checkpoint')
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
        print(json.dumps({'files': len(snapshot['files']), 'bytes': sum(r['size'] for r in snapshot['files'].values()),
                          'databases': snapshot['databases']}))
