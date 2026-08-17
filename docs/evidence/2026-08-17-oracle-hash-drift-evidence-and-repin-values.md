# Oracle-hash drift — evidence assembled, NOT re-pinned (owner decision)

2026-08-17. Board sha256 `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`
(unchanged by this document). Main at task start: `aec4bf1f8`.

This document assembles the evidence PR #1304 asked the next agent to gather
for `test_deterministic_d6_rust_differential.py`'s `_via_validation_run_py_oracle.py`
digest drift, goes beyond it with an independent reproduction, and adds a
second, previously-undocumented drift found while investigating (`_graph_py_oracle.py`).

**Per this task's explicit instruction ("assemble that evidence and say
precisely what a re-pin would assert... do not re-pin without that proof")
and PR #1304's own precedent (it had comparable evidence and also declined
to apply the fix, calling it an owner decision) — neither finding below has
been re-pinned. Both are left honestly red.**

---

## Finding 1: `_via_validation_run_py_oracle.py` — a dropped re-pin step

### The failing check

`packages/temper-placer/tests/deterministic/test_deterministic_d6_rust_differential.py::test_oracle_bodies_match_pinned_digests`
fails:

```
assert '1fe2a9bf90d2...cad3dbb807e90' == '7dc872f0c070...2d189f5b67883'
```

The test hashes the oracle file's body (everything after its
`# --- BEGIN PINNED BODY ---` marker) and compares against a `_PINNED` dict
literal inside the test file itself — a SEPARATE registry from
`scripts/oracle_hashes.json` (which hashes the whole file).

### The chain of evidence

1. **The oracle file has not changed since commit `a5da999cb`** (2026-08-15,
   PR #1148, "fix(determinism): correct frozenset_write's false cross-run
   claim + sort ViaValidationStage's plane-via log"):

   ```
   $ git diff a5da999cb HEAD -- packages/temper-placer/tests/deterministic/_via_validation_run_py_oracle.py
   (empty)
   ```

2. **`a5da999cb`'s own diff to the oracle file is a real, symmetric fix**,
   not a "make the oracle agree with the port" edit forbidden by the
   pinning discipline: it sorts `plane_vias_removed` by its VALUE tuple
   (net, position, layers, connected-count — never repr/hash) before
   truncating to the first 5, in BOTH arms:
   - `via_validation_stage.rs` (Rust): `plane_vias_removed.sort()?` added.
   - `_via_validation_run_py_oracle.py` (Python oracle): `sorted(plane_vias_removed)[:5]`
     replaces the unsorted `plane_vias_removed[:5]`.

   This is the correct fix for a real defect: printing an unsorted
   frozenset-derived list makes a diagnostic vary across `PYTHONHASHSEED`
   values with no behavior difference in the board — cosmetic but a
   determinism-hygiene bug the file's own docstring says the gate exists to
   catch elsewhere.

3. **`scripts/oracle_hashes.json`'s entry for this file WAS correctly
   updated** in the same commit (part of a squashed sub-commit titled
   "chore(oracle): re-pin via_validation_run oracle to merged content"):

   ```
   -    ".../_via_validation_run_py_oracle.py": "cf135fae816c6d015f5bd1cc4af3170a19385686cd6cff592bca4c0eae9f1cf5",
   +    ".../_via_validation_run_py_oracle.py": "5f892fa3d0daf9b640c2d392870f5b01053bb232ed9fa1f73bf61d9a83b39dde",
   ```

   Confirmed still current: `sha256sum` of the file today is exactly
   `5f892fa3d0daf9b640c2d392870f5b01053bb232ed9fa1f73bf61d9a83b39dde`, and
   `scripts/check_oracle_hashes.py` reports this file clean (166/167 OK;
   the one drift it reports is Finding 2, below — unrelated).

4. **But the SAME commit's diff never touches
   `test_deterministic_d6_rust_differential.py`** — `git show a5da999cb --stat`
   lists 6 files changed; the test file carrying `_PINNED` is not among them,
   despite the commit message explicitly claiming "Re-pinned the oracle's
   digest in `test_deterministic_d6_rust_differential.py` accordingly."

5. **The stale `_PINNED` value is exactly the PRE-fix digest.** Hashing the
   oracle file's body as it existed at `a5da999cb`'s PARENT commit
   (`2c1f112a6`, i.e. immediately before the fix) with the test's own
   marker-based algorithm:

   ```python
   body = text.rsplit("# --- BEGIN PINNED BODY ---\n", 1)[1]
   hashlib.sha256(body.encode()).hexdigest()
   # => 7dc872f0c07048db02cc3413153b9722b4b4d9b093c09572d182d189f5b67883
   ```

   — matches the `_PINNED` dict's current (stale) value exactly. This is
   airtight: the pin was never advanced past the pre-fix state.

6. **The commit message also claims two new tests were added**
   (`test_vv_plane_vias_removed_multi_entry_order_is_pinned` and
   `test_vv_plane_vias_removed_order_is_hash_seed_independent[_random]`,
   "14 fresh-interpreter runs... all byte-identical post-fix") — **neither
   test exists anywhere in the tree** (`grep -rn
   "multi_entry_order_is_pinned\|hash_seed_independent"` across
   `packages/temper-placer/` and `scripts/` returns nothing). The same merge
   that dropped the `_PINNED` dict edit also dropped these two tests
   entirely. This is a stronger instance of the same failure mode PR #1304
   diagnosed, not a separate one — evidently the merge/squash lost more of
   the commit's stated diff than just the one dict line.

### Independent re-verification (this session — the dropped tests replaced)

Because the tests that would have proven the fix's determinism no longer
exist, I did not rely on the commit message's claim alone. I wrote a
standalone repro (`/tmp/.../verify_vv_sort_determinism.py`, not committed —
scratch) using **8 disconnected GND plane vias at distinct
positions/net-suffixes** (the existing pinned tests only use 1 via, which
cannot exercise a sort's ordering at all) and ran it as a **fresh
interpreter process per seed**, comparing the Rust arm's stdout against the
Python oracle's stdout:

| PYTHONHASHSEED | Oracle SHA256 (of stdout) | Port SHA256 (of stdout) | Arms agree |
|---|---|---|---|
| 0–9 (10 fixed seeds) | `eb4a3294...` (identical every seed) | `eb4a3294...` (identical every seed) | yes, all 10 |
| 987654321 | `eb4a3294...` | `eb4a3294...` | yes |
| 424242 | `eb4a3294...` | `eb4a3294...` | yes |
| 13 | `eb4a3294...` | `eb4a3294...` | yes |
| 99 | `eb4a3294...` | `eb4a3294...` | yes |

**14/14 fresh-interpreter runs, byte-identical stdout, both within a run
(arm-to-arm) and across every seed** — independently reproducing the
commit message's claim with a fixture that actually exercises the sort
(8 vias > the 5-item truncation), not merely trusting it.

Additionally: **53 of the 54 tests in
`test_deterministic_d6_rust_differential.py` currently pass** — only
`test_oracle_bodies_match_pinned_digests` fails, and only on this one entry
of six. The via_validation-specific differential tests already in the
suite (`test_vv_*`, 9 tests) all pass unchanged.

### What a re-pin would assert

A one-line edit to `test_deterministic_d6_rust_differential.py`'s `_PINNED`
dict:

```diff
-    "_via_validation_run_py_oracle.py": "7dc872f0c07048db02cc3413153b9722b4b4d9b093c09572d182d189f5b67883",
+    "_via_validation_run_py_oracle.py": "1fe2a9bf90d2e3a122d6b56247391382bf1c2334ebed43ef2c3cad3dbb807e90",
```

Nothing else. `scripts/oracle_hashes.json` already carries the correct
value and needs no change.

**Not applied.** Left red per this task's explicit oracle-re-pin caution
and PR #1304's own precedent of treating this as an owner decision despite
comparable evidence.

---

## Finding 2: `_graph_py_oracle.py` — new, undocumented drift (networkx removal, #1280)

Found while investigating Finding 1: `scripts/check_oracle_hashes.py`
(the whole-file content-hash gate, separate from the `_PINNED`-dict
mechanism above) currently reports:

```
oracle content-hash gate: 166/167 oracle files OK (registry: 167 entries)
  [DRIFTED] packages/temper-placer/tests/topological/_graph_py_oracle.py -- hash a7c75bed205c... -> 83f54ad2c51a...
```

This is **not mentioned in the handoff or PR #1304's triage** — a fresh
finding.

### The chain of evidence

1. **Root cause: PR #1280** ("feat(tests): replace networkx test dependency
   with graph_fixtures port", merged as `e81196c87`, top of main's log at
   task start) removed `networkx` from the environment entirely and had to
   change every oracle file that imported it. `_graph_py_oracle.py`'s
   only change in that commit:

   ```diff
   -import networkx as nx
   +import tests.graph_fixtures as nx
   ```

   One line. `git show e81196c87 --stat -- .../_graph_py_oracle.py
   scripts/oracle_hashes.json` shows only the `.py` file changed —
   `scripts/oracle_hashes.json` was **not** updated for this file in that
   commit (unlike Finding 1, where the JSON registry WAS correctly
   advanced and only the redundant test-local dict was dropped — this is a
   different failure shape: the JSON registry itself was simply never
   touched).

2. **This is a forced, verified, behavior-preserving edit, not an
   "agree with the port" edit.** `networkx` was deleted from
   `pyproject.toml`/`uv.lock` in the same PR — the import line had to
   change or the oracle would not import at all. PR #1280's own commit
   message states the replacement (`tests/graph_fixtures.py`) was verified
   "behavior-identical before networkx left the environment: 900 grid
   min-cut comparisons + randomized container/algorithm parity against
   networkx 3.6.1 (0 mismatches)."

3. **`sha256sum` of the file today is exactly the gate's reported "drifted
   to" value**: `83f54ad2c51ad772517efad509904db552b6a879afe17056038eb7dc6060a165`.

4. **No `_PINNED`-style dict duplicates this hash** anywhere (checked
   `test_topological_rust_differential.py` and the file's other
   `_*_py_oracle.py` siblings in the same directory) — this drift is caught
   ONLY by `scripts/check_oracle_hashes.py`, not by any pytest assertion.
   Confirmed: `packages/temper-placer/tests/topological/test_topological_rust_differential.py`
   currently passes 443/443 — the drift is invisible to pytest, visible
   only to the standalone hygiene gate.

### What a re-pin would assert

A one-line edit to `scripts/oracle_hashes.json`:

```diff
-    "packages/temper-placer/tests/topological/_graph_py_oracle.py": "a7c75bed205c...",
+    "packages/temper-placer/tests/topological/_graph_py_oracle.py": "83f54ad2c51ad772517efad509904db552b6a879afe17056038eb7dc6060a165",
```

(`scripts/update_oracle_hashes.py` is the repo's own tool for producing
this edit mechanically, rather than hand-editing the JSON.)

**Not applied**, for the same reason as Finding 1: this task's instructions
single out oracle re-pinning as requiring owner-level deliberateness even
when evidence is strong, and I have no standing to unilaterally decide a
lower bar applies just because this instance is a smaller, one-line,
clearly-forced diff.

---

## Summary for the owner

| File | Registry | Current (correct) value | Currently pinned (stale) value | Evidence strength |
|---|---|---|---|---|
| `_via_validation_run_py_oracle.py` | `_PINNED` dict in `test_deterministic_d6_rust_differential.py` | `1fe2a9bf90d2e3a122d6b56247391382bf1c2334ebed43ef2c3cad3dbb807e90` | `7dc872f0c07048db02cc3413153b9722b4b4d9b093c09572d182d189f5b67883` | Dropped re-pin step (JSON registry side already correct); independently reproduced 14/14-seed determinism + arm agreement with a proper multi-via fixture (the fixture the dropped tests would have used no longer exists) |
| `_graph_py_oracle.py` | `scripts/oracle_hashes.json` | `83f54ad2c51ad772517efad509904db552b6a879afe17056038eb7dc6060a165` | `a7c75bed205c...` (truncated in gate output; full value in `scripts/oracle_hashes.json`) | Forced one-line import-path fix from networkx's removal (#1280), verified behavior-identical by that PR's own 900-comparison parity check; never re-pinned in `scripts/oracle_hashes.json` at all |

Both are single-line, mechanical, well-evidenced fixes. Neither has been
applied. If the owner authorizes either, the exact diffs are given above.
