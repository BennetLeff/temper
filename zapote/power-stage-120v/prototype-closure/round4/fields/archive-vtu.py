#!/usr/bin/env python3
"""Losslessly archive owned completed VTUs; verify restoration before unlink.

This is storage orchestration, not numerical analysis. Source/round2/native19
and active runs are excluded. Gzip files and per-run manifests remain local.
"""

import argparse
import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path


def digest_stream(stream) -> str:
    value = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        value.update(chunk)
    return value.hexdigest()


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return digest_stream(stream)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('work', type=Path, nargs='+')
    args = parser.parse_args()
    root = (Path.cwd()/'output/temper-prototype-closure/round4/fields').resolve()
    for work in args.work:
        work = work.resolve()
        if not work.is_relative_to(root) or work == root:
            raise ValueError('outside owned round4 run directory')
        result = json.loads((work/'result.json').read_text())
        resource = json.loads(work.with_name(work.name+'-resource.json').read_text())
        if not result['converged'] or result['exit_code'] != 0 or resource['status'] != 'COMPLETED' or resource['exit_code'] != 0:
            raise ValueError('refusing active, incomplete or rejected run')
        manifest_path = work/'vtu-archive.json'
        records = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
        if args.restore:
            for record in records:
                raw = work/record['raw']
                compressed = work/record['gzip']
                if not raw.resolve().is_relative_to(work) or not compressed.resolve().is_relative_to(work):
                    raise ValueError('archive manifest path escapes owned run')
                if raw.exists():
                    if digest(raw) != record['raw_sha256']:
                        raise ValueError('existing restored file differs')
                    continue
                temporary = raw.with_suffix('.vtu.restore-tmp')
                with gzip.open(compressed,'rb') as source,temporary.open('xb') as target:
                    shutil.copyfileobj(source,target,1024*1024)
                if digest(temporary) != record['raw_sha256']:
                    raise ValueError('restored file hash differs; original gzip retained')
                os.replace(temporary,raw)
            print(f'Restored {len(records)} verified VTU files in {work.name}',flush=True)
            continue
        for raw in sorted(work.glob('mesh/**/case*.vtu')):
            if not raw.resolve().is_relative_to(work):
                raise ValueError('VTU symlink escapes run directory')
            previous = next((r for r in records if r['raw']==str(raw.relative_to(work))),None)
            if previous:
                if digest(raw) != previous['raw_sha256']:
                    raise ValueError('previously archived raw file changed')
                with gzip.open(work/previous['gzip'],'rb') as stream:
                    if digest_stream(stream) != previous['raw_sha256']:
                        raise ValueError('existing archive is invalid')
                raw.unlink()
                continue
            compressed = raw.with_suffix('.vtu.gz')
            temporary = raw.with_suffix('.vtu.gz.tmp')
            if compressed.exists():
                raise ValueError('unregistered archive exists; refusing overwrite')
            before = raw.stat()
            expected = digest(raw)
            with raw.open('rb') as source,temporary.open('xb') as target:
                with gzip.GzipFile(filename='',mode='wb',compresslevel=1,fileobj=target,mtime=0) as archive:
                    shutil.copyfileobj(source,archive,1024*1024)
            with gzip.open(temporary,'rb') as restored:
                if digest_stream(restored) != expected:
                    raise ValueError('decompressed hash differs; raw file retained')
            after = raw.stat()
            if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                raise ValueError('raw file changed during archive; raw retained')
            os.replace(temporary,compressed)
            records.append({'raw':str(raw.relative_to(work)),'gzip':str(compressed.relative_to(work)),'raw_sha256':expected,'gzip_sha256':digest(compressed),'raw_bytes':before.st_size,'gzip_bytes':compressed.stat().st_size,'decompressed_sha256_verified':True})
            manifest_temporary = manifest_path.with_suffix('.json.tmp')
            manifest_temporary.write_text(json.dumps(records,indent=2)+'\n')
            os.replace(manifest_temporary,manifest_path)
            raw.unlink()
        print(f'Archived {len(records)} verified VTU files in {work.name}',flush=True)


if __name__ == '__main__':
    main()
