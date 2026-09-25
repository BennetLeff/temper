# Rejected 133-component construction

Preserved on 2026-09-19 before restoring the canonical 54-component baseline.
Not accepted, not fully routed, and not qualified for fabrication or powered use.

`snapshot/` mirrors repository paths for the authored source, poses, outline,
modified baseline test/build adapter, protection integration adapter, and full
candidate board/schematic/library environment. `archive-receipt.json` records
SHA-256 hashes for every saved file and every restored tracked file. The PCB
hash in the archive is `ae47d43a4c65e30fac5d54f52422d57bc8338a5b90e60f4c4c810041316913cb`.

Retained source/native exports are still at `../../source-build-07` and
`../../native-05`. The nine Rust logic tests bind the latter manifest and are
historical checks, not tests of the restored canonical baseline.

The saved scripts are historical copies with their original repository-relative
path assumptions. Do not run them in the snapshot directory or copy them back
over active tools without explicitly reconstructing an isolated experiment.
See [the reduction decision](../ARCHITECTURE-REDUCTION.md) for current direction.
