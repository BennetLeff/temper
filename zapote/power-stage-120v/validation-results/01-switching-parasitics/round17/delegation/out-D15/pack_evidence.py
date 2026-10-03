#!/usr/bin/env python3
"""Archive scalar raw evidence; keep large, fully hashed waveforms local."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    members = []
    with (HERE / 'raw-evidence.tar.gz').open('wb') as output:
        with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|') as archive:
                roots = [HERE / 'raw', *sorted(HERE.glob('recovery-itl4-*/raw'))]
                for path in sorted(file for root in roots for file in root.rglob('*')):
                    if path.is_symlink():
                        raise ValueError(f'Symlink is not evidence: {path}')
                    if not path.is_file():
                        continue
                    if path.suffix.lower() == '.lib':
                        raise ValueError(f'Licensed model must not ship: {path}')
                    data = path.read_bytes()
                    name = path.relative_to(HERE).as_posix()
                    included = path.name != 'waves.raw.gz'
                    members.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                    'included_in_archive': included})
                    if included:
                        item = tarfile.TarInfo(name)
                        item.size = len(data)
                        item.mode = 0o644
                        item.mtime = 0
                        archive.addfile(item, io.BytesIO(data))
    path = HERE / 'raw-evidence.tar.gz'
    metadata = {'archive': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'member_count': sum(m['included_in_archive'] for m in members), 'files': members}
    (HERE / 'raw-manifest.json').write_text(json.dumps(metadata, indent=2) + '\n')
    # Verify the compressed deliverable independently of directory traversal.
    expected = {m['path']: m for m in members if m['included_in_archive']}
    with tarfile.open(path) as archive:
        actual = archive.getmembers()
        assert len(actual) == len(expected)
        for item in actual:
            assert item.isfile() and item.name in expected and not item.name.startswith('/')
            assert '..' not in Path(item.name).parts
            stream = archive.extractfile(item)
            assert stream is not None
            assert hashlib.sha256(stream.read()).hexdigest() == expected[item.name]['sha256']
    print(json.dumps({'archive_bytes': path.stat().st_size, 'verified_members': len(expected),
                      'local_only_waveforms': len(members) - len(expected)}))


if __name__ == '__main__':
    main()
