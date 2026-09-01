<!-- provenance: commit=41eaa9a3d54b15bb9342dc42357a4bde3f3663d2 dirty=UNKNOWN -->
# Oracle re-pin 2/2: `_graph_py_oracle.py` — independently validated, applied

2026-08-17. Board sha256 `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
(unchanged by this document/commit — verified before and after). Main at
session start: `775a7a40e`.

Independent validation, not applied on the strength of
`docs/evidence/2026-08-17-oracle-hash-drift-evidence-and-repin-values.md`'s
Finding 2 alone.

## What was independently confirmed

1. **`scripts/check_oracle_hashes.py` live run, before the re-pin**:

   ```
   oracle content-hash gate: 166/167 oracle files OK (registry: 167 entries)
     [DRIFTED] packages/temper-placer/tests/topological/_graph_py_oracle.py -- hash a7c75bed205c... -> 83f54ad2c51a...
   ```

   Reproduced live in this session's own venv (`make venv-isolate`, this
   worktree, not the shared repo `.venv`), not copied from the prior
   document.

2. **Root cause re-derived from git, not trusted from the prior document**:
   `git show e81196c87 --stat -- .../_graph_py_oracle.py scripts/oracle_hashes.json`
   shows only the `.py` file changed in that commit (PR #1280, "replace
   networkx test dependency with graph_fixtures port") —
   `scripts/oracle_hashes.json` was never touched for this file. The
   commit's actual diff to the oracle:

   ```diff
   -import networkx as nx
   +import tests.graph_fixtures as nx
   ```

   One line, forced: PR #1280 removed `networkx` from the environment
   entirely (`pyproject.toml`/`uv.lock`), so this import had to change or
   the oracle would fail to import at all — not an "agree with the port"
   edit forbidden by the pinning discipline. PR #1280's own commit message
   states the replacement was verified behaviour-identical before networkx
   left the environment (900 grid min-cut comparisons + randomized
   container/algorithm parity against networkx 3.6.1, 0 mismatches) — a
   claim outside this document's scope to re-verify (it predates and is
   independent of the oracle-hash question), but the change under review
   here is only the one-line import-path swap, and that swap's own
   correctness (importing a verified-equivalent module) is not in question.

3. **Current file hash matches the gate's reported target exactly**:
   `sha256sum packages/temper-placer/tests/topological/_graph_py_oracle.py`
   → `83f54ad2c51ad772517efad509904db552b6a879afe17056038eb7dc6060a165`.

4. **No `_PINNED`-dict duplicate of this hash exists anywhere** — checked
   `test_topological_rust_differential.py` and this oracle's sibling
   `_*_py_oracle.py` files in the same directory
   (`_force_refinement_py_oracle.py`, `_initial_placement_py_oracle.py`,
   `_propagation_py_oracle.py`). The drift is caught only by
   `scripts/check_oracle_hashes.py`'s whole-file registry, never by a
   pytest assertion.

5. **Live test run, before the re-pin**: `pytest tests/topological/` —
   683 passed, 3 skipped (pre-existing, unrelated) — the drift is invisible
   to pytest, confirming point 4.

## What was applied

Ran the repo's own regeneration tool rather than hand-editing the JSON
(per its own stated purpose — "the human/agent step that records the
pins," output deterministic so the diff shows exactly what moved):

```
$ uv run --no-sync python3 scripts/update_oracle_hashes.py
  [CHANGED] packages/temper-placer/tests/topological/_graph_py_oracle.py
      a7c75bed205c... -> 83f54ad2c51a...
wrote scripts/oracle_hashes.json: 167 oracle files (1 changed/new/removed)
```

Exactly one entry changed — confirming no other oracle had drifted in this
worktree and this re-pin does not silently sweep in anything else. Diff:

```diff
-    "packages/temper-placer/tests/topological/_graph_py_oracle.py": "a7c75bed205c3a05b52bf0f272a5d29a22f43947ee8ad3c541a868d2e3173061",
+    "packages/temper-placer/tests/topological/_graph_py_oracle.py": "83f54ad2c51ad772517efad509904db552b6a879afe17056038eb7dc6060a165",
```

Verified post-edit:
- `scripts/check_oracle_hashes.py`: `167/167 oracle files OK`.
- `pytest tests/topological/`: 683 passed, 3 skipped (same skip set as
  before — unchanged).

`pcb/temper.kicad_pcb` — not touched; sha256 reverified unchanged after this
change (`33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`).
