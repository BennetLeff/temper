# Round 4 raw evidence release QA

Checked 2026-09-28 against committed `../raw-manifest.json` at worktree HEAD
`91888bb29e318eef09c0a292245de88b9016d250`. Source files came from the
round-4 integration worktree's `validation-results` directory; neither the
source files nor the committed raw manifest were changed.

- Raw manifest SHA-256: `40ef4b2194c89dc841cef736fddac93f258cc23319b0128abbb5ff75724cccb5`.
- Manifest coverage: 12,027 unique paths, 5,923,554,281 file bytes.
- Release tag target: `ps120-validation-round4-raw-v1`.
- Local upload directory: `/tmp/ps120-round4-release/` (tar assets only; do not upload its generated `assets.json`).

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `ps120-round4-raw-part-01-of-05.tar` | 1,301,698,560 | `4b88476f9055677c7d738b6822d5446c2f1ac41298fe00cc2473ccf840ed7c66` |
| `ps120-round4-raw-part-02-of-05.tar` | 1,381,857,280 | `50ba65987209d4ade9ae2fd39315965e171f2b3e62ed7c79b5457dd7806aa286` |
| `ps120-round4-raw-part-03-of-05.tar` | 1,384,017,920 | `c2542eb0c509ea5a65150ef63669d64d62422961f2b7b011bb49d0e5359d799b` |
| `ps120-round4-raw-part-04-of-05.tar` | 1,346,897,920 | `38c80c7b92f89e56780a99c47732f8b9f7ac1f008f393b7e9b74d2c5723ecae2` |
| `ps120-round4-raw-part-05-of-05.tar` | 529,162,240 | `652160c6e2214dc5616dc9bb323ddc0a1b053011b3b081c338f42908a1d99e89` |

The largest part is below 1.5 billion bytes and 2 GiB. A second independent
build produced byte-identical `assets.json` and all five tar files (`cmp`).
Local restore from these assets accepted and verified all 12,027 members.
The independent `../verify_raw.py` then reported `12027/12027 round-4 local
files verified` in `/tmp/ps120-round4-restored/validation-results`.

`python3 test_archive.py -v` passed five focused tests covering absent and
corrupted assets; path traversal, absolute, unexpected, symlink, and directory
members; duplicate, missing, truncated, and corrupted members; mismatching
existing files; and destination symlinks. The checks run before installation,
and restore never silently replaces an existing mismatch.

Release-content scan covered only manifest-listed paths. No path contained
`.lib.zip` or ended in `.lib` or `.zip`. A streaming scan found no private-key
headers, GitHub token prefixes, AWS access-key IDs, credential assignments,
Infineon copyright/license markers, or SPICE `.subckt`/`.model` declarations.
The broader vendor-name pass over text and decompressed logs is recorded below.

The broader pass found 14 files containing the vendor name: nine small Python
source snapshots or source-hash metadata files and five small circuit input
files (all 3.8–4.2 KB). It found zero `copyright`, `proprietary`, `licensed
model`, or `.lib.zip` markers in the uncompressed text and decompressed logs.
The circuit inputs have no `.model` or `.subckt` declarations. These are
references to the part/model, not bundled vendor model text. The scan printed
paths and category counts only, never matching content or credentials.

Coordinator review found a check/replace race that could overwrite a different file installed concurrently. A focused test reproduced the old failure (`ValueError not raised`); atomic same-filesystem hard-link installation now refuses replacement and verifies any concurrent winner. The six-test suite passes after the fix. Asset contents/hashes are unchanged. Restore requires a trusted destination whose directory topology is not concurrently changed; it is not a sandbox against another process replacing ancestor directories.

After the atomic installation fix, a fresh full restore to `/tmp/ps120-round4-restored-atomic/validation-results` verified all 12,027 files. GitHub API asset sizes and SHA-256 digests matched all five local assets; the release was published on 2026-09-28 as a prerelease.

Formal review also found that an initially matching destination was skipped after extraction. Removing that shortcut rechecks every destination before installation; mutation tests reject a changed file and restore a deleted file. All eight tests pass, followed by a complete repeat restore of all 12,027 files. These fixes change no archive bytes.

The repository's release workflow automatically attached an unrelated `temper_placer` wheel. After explicit owner approval it was removed; the release has exactly the five tar assets above. The workflow's firmware job failed and its wheel job passed; neither job is an evidence verification or hardware-release gate.
