# Round-3 raw evidence

The round-3 packet is 566 MB. Reports, scripts, sources and summary outputs
(378 files, about 20 MB) are in git. The raw evidence (per-case run
directories, ngspice logs, compressed waveforms, heat-field arrays, and data
files of 2 MB or more: 3,327 files, 546 MB) goes to the GitHub release
`ps120-validation-round3-raw-v1`, asset `ps120-round3-raw-evidence.tar`
(SHA-256 in `asset.env`).

**Published 2026-09-28:** [round-3 evidence release](https://github.com/BennetLeff/temper/releases/tag/ps120-validation-round3-raw-v1), with explicit owner approval. The rebuilt archive and GitHub's uploaded asset digest both match `asset.env`: `a4690f17bb2e4ccf4d9527bc3c114b0447a21d54375a7dd601de7c5be9eccd10`. Asset size is 549,529,600 bytes. The tag targets `91888bb29e318eef09c0a292245de88b9016d250`; this is historical round-3 evidence, not a hardware release. Local copies remain available. The tarball is rebuilt byte-for-byte by `build_archive.py`; a test extraction verified 3,327/3,327 files. The owner chose this split on 2026-09-28 (storage option 1).

- `manifest.json`: every archived file's path, size and SHA-256. The rule is
  recorded in the file.
- `build_archive.py`: rebuilds the tarball from the files; the output is
  byte-reproducible (two builds gave the same SHA-256).
- `restore.sh`: downloads the asset, checks its SHA-256, extracts it into
  `validation-results/`, and verifies every file with `verify.py`.
- `../../.gitignore` keeps the restored files out of git.

The two copies of `switching-events.csv` (task 03 input, task 05 output) are
byte-identical. Both are archived at their original paths, so the scripts
that read them work unchanged after a restore.

No vendor model is in the archive: a full scan found no Infineon model text,
only ngspice's listing of internal node names in four B1 logs.

Restore before rerunning any round-3 script that reads raw runs or arrays
(for example `round3-coordination/check_handoffs.py`).
