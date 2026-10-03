#!/usr/bin/env python3
"""Pack raw simulation receipts; preserve local tree and verify every member."""
from __future__ import annotations

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    members = sorted(p for p in (HERE / 'raw').rglob('*') if p.is_file())
    ledger = {}
    for path in members:
        assert not path.is_symlink()
        assert path.name in {'run.log', 'params.inc', '.spiceinit', 'result.json'}
        ledger[str(path.relative_to(HERE))] = hashlib.sha256(path.read_bytes()).hexdigest()
    archive = HERE / 'raw-evidence.tar.gz'
    with archive.open('wb') as file, gzip.GzipFile(filename='', mode='wb', fileobj=file, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as tar:
            for path in members:
                info = tar.gettarinfo(str(path), arcname=str(path.relative_to(HERE)))
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ''
                with path.open('rb') as source:
                    tar.addfile(info, source)
    with tarfile.open(archive, 'r:gz') as tar:
        assert len(tar.getmembers()) == len(ledger)
        for member in tar.getmembers():
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            source = tar.extractfile(member)
            assert source is not None
            assert hashlib.sha256(source.read()).hexdigest() == ledger[member.name]
    (HERE / 'raw-evidence-sha256.json').write_text(json.dumps({'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'member_count': len(ledger), 'members': ledger}, indent=2) + '\n')
    print(f'Verified {len(ledger)} regular relative members; no vendor libraries or symlinks.')


if __name__ == '__main__':
    main()
