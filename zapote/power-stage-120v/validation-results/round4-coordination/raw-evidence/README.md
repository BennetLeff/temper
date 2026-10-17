# Round 4 raw evidence release

Published 2026-09-28: [five independent tar assets](https://github.com/BennetLeff/temper/releases/tag/ps120-validation-round4-raw-v1). All five GitHub-reported asset sizes and SHA-256 digests match `assets.json`. Do not concatenate the parts. The frozen raw manifest retains its historical local-only storage label; this publication supersedes that location, without changing the manifest or raw bytes.

The committed `../raw-manifest.json` identifies 12,027 raw files (5,923,554,281
bytes) by relative path, size, and SHA-256. This directory contains the
transport scripts and `assets.json`, which pins five deterministic tar assets
and the SHA-256 of that raw manifest. The tar files themselves belong in the
GitHub release `ps120-validation-round4-raw-v1`; they are not git files.

Restore from the published release, from the repository checkout:

```sh
python3 zapote/power-stage-120v/validation-results/round4-coordination/raw-evidence/restore.py
```

This requires `gh` with access to `BennetLeff/temper`. To use already downloaded
assets, pass `--local-assets /path/to/directory`. The default destination is
`zapote/power-stage-120v/validation-results`; use `--root /path/to/validation-results`
for a separate copy. The destination directory must exist.

Restore verifies all five asset sizes and SHA-256 hashes before extraction.
It accepts only regular archive members named in the raw manifest, once each,
and verifies every member's size and SHA-256 while extracting to a temporary
directory. It rejects unexpected, duplicate, missing, truncated, and
non-regular members. An existing file with different bytes is an error;
matching files are left in place. Destination symlinks are rejected.

To rebuild the release assets from a complete local raw source:

```sh
python3 zapote/power-stage-120v/validation-results/round4-coordination/raw-evidence/build_archive.py \
  --source-root /path/to/validation-results \
  --output-dir /tmp/ps120-round4-release
```

Use an empty output directory. The builder streams files, checks their
manifest size and SHA-256, fixes tar metadata, and sorts paths. Each asset is
below 1.5 billion bytes. Compare the rebuilt `assets.json` byte-for-byte with
the committed copy before uploading the five tar files. `assets.json` itself
is committed and does not need to be a release asset.

The transport checks establish byte identity, not electrical or simulation
validity. `../verify_raw.py /path/to/validation-results` provides an
independent check of the restored files.

Use a trusted destination with stable parent directories during restore. File installation refuses to overwrite a concurrent mismatching file; directory-renaming attacks by another local process are outside this transport's scope.
