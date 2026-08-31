<!-- provenance: commit=41eaa9a3d54b15bb9342dc42357a4bde3f3663d2 dirty=UNKNOWN -->
# Oracle re-pin 1/2: `_via_validation_run_py_oracle.py` — independently validated, applied

2026-08-17. Board sha256 `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
(unchanged by this document/commit — verified before and after). Main at
session start: `775a7a40e`.

This re-pin was NOT applied on the strength of
`docs/evidence/2026-08-17-oracle-hash-drift-evidence-and-repin-values.md`'s
own document (that document explicitly declined to apply it and asked the
next agent to validate independently). Everything below is this session's
own, independent reproduction.

## What was independently confirmed

1. **Git archaeology, reproduced from scratch**: `a5da999cb` (PR #1148,
   2026-08-15) fixed a real determinism defect in
   `ViaValidationStage`'s "Removed plane vias (first 5)" diagnostic —
   `plane_vias_removed` was appended in `state.vias`' frozenset iteration
   order (PYTHONHASHSEED-salted, since `Via.net`/`Via.layers` are strings)
   and printed unsorted, so an otherwise byte-identical run's stdout varied
   across processes. Fix: `sorted(plane_vias_removed)[:5]` in the oracle,
   `plane_vias_removed.sort()?` (via `PyList::sort()`, a plain Python-tuple
   value comparison, never repr/hash) in the Rust port
   (`via_validation_stage.rs`), applied identically to both arms.
   - `git diff a5da999cb HEAD -- .../_via_validation_run_py_oracle.py` is
     empty — confirmed the oracle file has not moved since that commit.
   - `git show a5da999cb --stat` lists 6 files changed; the test file
     carrying `_PINNED` is not among them, despite the commit message
     claiming the digest was re-pinned there. The two new tests the message
     also claims (`test_vv_plane_vias_removed_multi_entry_order_is_pinned`,
     `test_vv_plane_vias_removed_order_is_hash_seed_independent`) do not
     exist anywhere in the tree (confirmed by grep) — the same
     squash/merge dropped more of the commit's stated diff than the one
     dict line.
   - `scripts/oracle_hashes.json`'s whole-file entry WAS correctly advanced
     in the same commit and still matches the file's current sha256sum
     exactly (`5f892fa3d0daf9b640c2d392870f5b01053bb232ed9fa1f73bf61d9a83b39dde`)
     — confirmed live, not from the prior document's say-so.
   - Hashing the oracle body (the `test_oracle_bodies_match_pinned_digests`
     algorithm) at `a5da999cb^` (pre-fix) reproduces the stale pinned value
     `7dc872f0c07048db02cc3413153b9722b4b4d9b093c09572d182d189f5b67883`
     exactly; hashing it at HEAD reproduces the new value
     `1fe2a9bf90d2e3a122d6b56247391382bf1c2334ebed43ef2c3cad3dbb807e90`
     exactly. Computed directly, not copied from any prior document.

2. **Live test run, before the re-pin** (this session's own venv,
   provisioned via `make venv-isolate` in this worktree, not the shared
   repo `.venv`): `pytest tests/deterministic/test_deterministic_d6_rust_differential.py`
   — 53/54 passed, only `test_oracle_bodies_match_pinned_digests` failed,
   with the exact digest mismatch described above. The 9 `test_vv_*`
   differential tests (the ones that actually exercise `ViaValidationStage`
   behaviour) all passed unchanged.

3. **Independent determinism reproduction — a fixture I wrote myself**,
   not the prior agent's script (which no longer exists — scratch,
   never committed): 8 disconnected GND-family plane vias at distinct
   positions and net suffixes (`GND`, `GND1`, `GND2`, `GND3`, `AGND`,
   `PGND`, `GND_A`, `GND_B`) — the existing 1-via pinned tests cannot
   exercise a 5-item-truncated sort at all; 8 can. Both arms
   (`_via_validation_run_py_oracle.ViaValidationStage` and the Rust-backed
   `temper_placer.deterministic.stages.ViaValidationStage` shim) run in a
   **fresh interpreter process per seed** (`PYTHONHASHSEED` set only via the
   environment before process start, never mutated in-process), stdout
   captured and sha256'd:

   | PYTHONHASHSEED | Oracle SHA256 | Port SHA256 | Agree |
   |---|---|---|---|
   | 0–9, 42, 987654321, 424242, 13579 (14 seeds) | `e31f61df2dd6...` (identical every seed) | `e31f61df2dd6...` (identical every seed) | yes, all 14 |

   Confirmed `PYTHONHASHSEED` was actually taking effect in each process
   (not a sandbox artifact pinning it to 0 regardless): `hash("GND")` under
   seed 0 is `-4814178535144959660`, under seed 1 is `2467660075842508884`
   — genuinely different per process.

4. **Positive control — proving the fixture is not vacuously insensitive**:
   with the sort temporarily reverted to the pre-fix unsorted slice
   (`plane_vias_removed[:5]`, edited on the real file, tested, then
   reverted with `git checkout --` and the working tree confirmed clean —
   never committed), the SAME 8-via fixture produced **three distinct
   hashes across three seeds** (0, 1, 2: `83f78c42...`, `60a14b49...`,
   `7e3c06c3...`). This demonstrates the fixture genuinely detects the
   defect when present, not just agrees when the fix is present — the null
   result above (14/14 identical, post-fix) is not a fixture blind spot.

## Conclusion

Independent reproduction agrees with
`docs/evidence/2026-08-17-oracle-hash-drift-evidence-and-repin-values.md`'s
Finding 1 in every particular: the correct value is
`1fe2a9bf90d2e3a122d6b56247391382bf1c2334ebed43ef2c3cad3dbb807e90`, the
stale pinned value is exactly the pre-fix digest, `scripts/oracle_hashes.json`
needs no change (already correct), and the divergence is a dropped re-pin
step from a squash/merge, not an "agree with the port" edit — the diff is a
real, symmetric, both-arms-identical determinism fix.

## What was applied

One-line edit to `packages/temper-placer/tests/deterministic/test_deterministic_d6_rust_differential.py`'s
`_PINNED` dict:

```diff
-    "_via_validation_run_py_oracle.py": "7dc872f0c07048db02cc3413153b9722b4b4d9b093c09572d182d189f5b67883",
+    "_via_validation_run_py_oracle.py": "1fe2a9bf90d2e3a122d6b56247391382bf1c2334ebed43ef2c3cad3dbb807e90",
```

(Plus a comment recording this evidence inline, per the existing precedent
at the `_placement_validation_run_py_oracle.py` entry in the same dict.)

Verified post-edit: `pytest tests/deterministic/test_deterministic_d6_rust_differential.py`
— 54/54 pass.

`scripts/oracle_hashes.json` — NOT touched (already correct, verified above).

`pcb/temper.kicad_pcb` — not touched; sha256 reverified unchanged after this
change (`33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`).
