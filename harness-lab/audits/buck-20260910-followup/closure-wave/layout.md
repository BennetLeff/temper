# Buck layout closeout summary

Date: 2026-09-10

## Corrected candidate

The corrected L2 candidate is retained at `../layout/candidate-v5/candidate.kicad_pcb`
under the follow-up audit and was copied unchanged into the scratch run. Its
SHA-256 is `1d1ae546a0e78fe4c923b5cee736bc0811ca13a7cca33853274052f556d13ac3`.
Native KiCad collection plus the existing Rust engineering-layout judge passed:

- ground return C9.2 -> U3.1: 11.2875 mm;
- input path C9.1 -> U3.3: 5.4375 mm;
- minimum power width: 0.6 mm;
- presentation: pass; findings: none.

The proof is `layout-evidence/native-candidate/judge-result.json`. It is a candidate-only
check; `hardware_validated` remains false and missing connector/inductor 3D
models remain report-only.

## Frozen positive witnesses

The frozen run's 12 positives were existing witness boards, each repeated
three times. They did not use the corrected candidate and do not constitute a
reference refresh. Board hashes were:

| Variant | Board SHA-256 |
|---|---|
| buck-dev-a | `83f754360019ddfbaf01d5be31fe52856669d0354684d29ff17d8064187117d2` |
| buck-dev-b | `032f1697989b0ae56eb7bfcc2a97a03b196602bd433cc7e032c7d35b1836d59f` |
| buck-res-a | `0e7fd7854170dfffdfce4322ecb8dcfb67d411dd69c363768156b31b8283d939` |
| buck-res-b | `913a83fd1c1ac8d3631441c7c5791a9a3d7f4c3374b13b60aa8ff78d11059bb7` |

## Native negative-control crash

The `buck-dev-a` missing-terminal-connection mutant was replayed directly
against both `/opt/homebrew/bin/kicad-cli` and its real target
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`, with
`--all-track-errors --severity-all`, a seeded temporary `KICAD_CONFIG_HOME`,
and `MaximumThreads=1`.

The Homebrew symlink resolves directly to the app binary. The symlink command
crashed three out of three times with exit 133 and no JSON report:

`Swift/SwiftNativeNSArray.swift:78: Fatal error: Array index out of range`

The explicit app-binary invocation also crashed (exit 134, no report). The
untouched witness passed three out of three under the same argv and config.
Replay logs and reports are retained in `layout-evidence/drc-replay/` and
`layout-evidence/direct-real/`. Original frozen-run artifacts remain at
`/tmp/temper-buck-close-20260910/layout/frozen-qualification/`.

Wrong-net, moved-terminal, and changed-rules mutants each ran twice with the
same configuration, exited 0, and produced reports. Their semantic rejection
is supplied by the Rust judge: wrong-net and moved-terminal returned fail with
the expected findings. The missing-route Rust-only replay also returned fail
with `unrouted:*` findings in `layout-evidence/negative-evals/missing-terminal-rust-judge.json`.

Conclusion: the missing-route native negative control is blocked by a real
KiCad CLI crash, not by the Python collector or a wrapper misconfiguration.
It must remain an unresolved qualification blocker; omitting DRC checks or
treating the crash as a rejection would be invalid.
