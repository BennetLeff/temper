<!-- provenance: commit=187e2c7d6d7f13034f2364cb6ad09ff5c22a0973 dirty=false
     branch=verify/u1-cnf-composition (tracks feat/constraint-model-rust-repr,
     which is origin/feat/constraint-model-rust-repr merged with origin/main --
     i.e. #1088's packed ConstraintModel composed with #1075's packed
     CnfFormula, both present on this commit)
     worktree=/home/bennet/Desktop/temper-worktrees/u1-cnf-composition
     date=2026-08-12
     method=isolated venv (make venv-isolate, 10/10 extensions fresh via
       check_stale_extensions.py before any measurement); pinned
       pumpkin_engine verified (exit 0) before routing; three independent
       full scripts/route_board.py --net-batching routes on the committed
       pcb/temper.kicad_pcb (no placement stage), sha256 compared;
       ConstraintModel memory probes re-run verbatim from
       docs/evidence/2026-08-12-router-model-memory-probe{,-distinct-keys}.py;
       CnfFormula clause-representation probe re-run verbatim from
       docs/evidence/scripts/2026-08-12-cnf-repr-probe-isolated.rs (compiled directly
       with rustc -O -- the probe has no external deps and does not need the
       crate on the compile path, since it reproduces the CSR layout
       structurally rather than importing CnfFormula itself); rustc 1.97.1
       (8bab26f4f 2026-07-14), cargo 1.97.1 (c980f4866 2026-06-30); no
       pcb/** file touched, no drc_ceiling.json touched. -->

# U1 composition verification: PR #1075's packed `CnfFormula` and PR #1088's packed `ConstraintModel`, together, still byte-identical

## Verdict

**Yes, the board is byte-identical with both changes composed.** Three
independent `route_board.py --net-batching` routes on the merged tree (#1088
merged with `origin/main`, which carries #1075) all hash
`845c144de2b87fd948f19458986ad1f65dac4d7fe9dcfbca6c760d2224a5fd0f` --
the exact hash #1088 recorded on a tree that did not yet carry #1075. This
closes both PRs' outstanding claims:

| question | answer |
|---|---|
| Composed-tree board byte-identical to `845c144d…`? | **Yes**, 3/3 runs |
| #1088's own re-verification (flagged as a landing prerequisite by its author) | **Done here** -- see "Which claim each run supports" below |
| #1075's outstanding byte-identity check | **Closed** -- same three runs are also the first byte-identity evidence #1075 ever produced, on any tree |
| `ConstraintModel` bytes/var (pinned probe) | **25.1** -- unchanged from #1088's isolated measurement |
| `ConstraintModel` bytes/var (distinct-key probe) | **33.0** -- unchanged from #1088's isolated measurement |
| `CnfFormula` bytes/clause | **13.81** (from 56.00, 4.06x) -- unchanged from #1075's isolated measurement |
| Engine pin | VERIFIED, exit 0, same sha256 or pin as both PRs |

No interaction between the two representation changes was found. A packed
`ConstraintModel` feeding a packed `CnfFormula` produces the same routed
board and the same per-representation memory figures as either change did
alone.

## Which claim each run supports

Both #1075 and #1088 are representation-only changes to different, adjacent
layers (`ConstraintModel` storage vs. `CnfFormula` storage), and this task's
runs are on a tree carrying **both**. A single passing byte-identity result
here is evidence for both claims simultaneously -- there is no way to
attribute a match to one change and not the other, only a *mismatch* can be
isolated (see "If the board differs" in the task, and the not-needed
per-change isolation section below). Framed precisely:

- **#1088's claim** ("packing `ConstraintModel` does not change the routed
  board") was already independently verified on a tree *without* #1075. This
  task adds the composed-tree re-verification #1088's author explicitly
  flagged as a landing prerequisite ("the merge needs its own board
  re-verification before landing, and doing it on a tree carrying both
  changes would conflate them" -- true of attributing a *difference*, not of
  confirming a match).
- **#1075's claim** ("packing `CnfFormula.clauses` does not change the routed
  board") was never verified on any tree -- its own PR explicitly reported
  this as outstanding, because the route did not complete on a loaded
  machine. This task's three runs are the first time that byte-identity has
  been measured for #1075 at all, on a tree that also carries #1088.

Because the composed tree matches the same hash #1088 recorded pre-#1075,
and because #1075 changes nothing #1088 touches (`CnfFormula` lives in
`temper-rust-router-core/src/encoding.rs`, downstream of
`ConstraintModel`'s pyo3 boundary in `temper-design-bundle`), the natural
reading is that both changes are independently representation-only and
compose cleanly. No per-change isolation run (composed-tree vs.
#1088-alone vs. #1075-alone) was needed because there was no mismatch to
attribute -- the task's "If the board differs" isolation procedure was not
triggered.

## 1. Engine pin

```
$ uv run --no-sync python3 scripts/verify_pumpkin_engine.py
pumpkin_engine identity gate: VERIFIED -- pumpkin_engine sha256=7ff153f478f8022f8f8659a514ab7067220812ef82b002fd17955fe0f2083b5e source_commit=5bbf650d47d3a07fffd10a44e7c06c43a0a800bd path=/home/bennet/Desktop/temper/target-shared/release/pumpkin_engine
EXIT=0
```

Exit 0, and the same `sha256`/`source_commit` #1088's own evidence doc
recorded. The binary lives in the shared `target-shared/release/` (per
`.cargo/config.toml`'s shared `CARGO_TARGET_DIR`), so this gate is
worktree-independent by construction -- verified explicitly rather than
assumed from that fact.

## 2. Composed tree confirmed to carry both changes

```
$ git merge-base --is-ancestor 756968706b4025b6910ec33c20a0c63fd7bb6b5b HEAD && echo yes
yes
```

`756968706` is PR #1075's squash-merge commit (`fix(sat-encoding): delete
dead aux-var-name allocation + pack CnfFormula.clauses (R1+R2)`). Structural
confirmation, not just the ancestry check:
`packages/temper-rust-router-core/src/encoding.rs` on this tree defines

```rust
pub struct CnfFormula {
    pub num_vars: usize,
    pub literals: Vec<i32>,
    pub clause_offsets: Vec<u32>,
    pub var_to_net: Vec<usize>,
}
```

(the CSR shape #1075 introduced), and
`packages/temper-design-bundle/src/model_builder.rs` defines `PackedVar`,
`Interner`, `PackedConstraint`, `VarIndex` (the shapes #1088 introduced).
Both present, on the same commit, in the same crate graph.

## 3. Board routing -- three independent runs

Same recipe #1088 used: `route_board.py --net-batching --output <path>` on
`pcb/temper.kicad_pcb` as committed, no placement stage. Isolated venv
(`make venv-isolate`), all 10 pyo3 extensions rebuilt and confirmed fresh
(`check_stale_extensions.py`: `fresh=10 stale=0 missing=0 tool-errors=0`)
before the first run.

**The `board_origin` hazard does not apply here -- confirmed, not assumed.**
`route_once()` calls `route_pcb(parsed_stub, {}, ...)`: the second positional
argument is `placements`, and `{}` is falsy, so
`_adapter_convert.py`'s `if placements:` guard (line 414) never fires and
`_apply_placements_to_pcb` is never called. Every run's log opens with
`Empty placements provided; routing with existing board positions.`,
confirming this at runtime, not just by reading the source.

No other `route_board.py`/`pumpkin_engine` process was competing for this
worktree's routes at launch time (checked via `ps aux` before each run); an
unrelated heatsink-board route in a different worktree ran concurrently with
run 1 and did not affect memory headroom (peak system usage stayed under
20 GB of 62 GB total across all three runs).

| run | result | pad connectivity | wall | sha256 |
|---|---|---|---:|---|
| composed_run1 | 62/102 nets (60.8%), segments=3193 vias=24 zones=84 | 48/139 fully pad-connected, fake-completion=45, honest-gap=46 | 507.6 s | `845c144d…` |
| composed_run2 | 62/102 nets (60.8%), segments=3193 vias=24 zones=84 | 48/139 fully pad-connected, fake-completion=45, honest-gap=46 | 480.6 s | `845c144d…` |
| composed_run3 | 62/102 nets (60.8%), segments=3193 vias=24 zones=84 | 48/139 fully pad-connected, fake-completion=45, honest-gap=46 | 570.8 s | `845c144d…` |

All three: `sha256=845c144de2b87fd948f19458986ad1f65dac4d7fe9dcfbca6c760d2224a5fd0f`,
identical to #1088's own six-run figure and to #1088's raw
routed/attempted count. `[net-batching] 11 batch(es), 11 solved at batch
level, 0 crashed` on every run. `diff` empty across all three routed
`.kicad_pcb` files (confirmed directly, not inferred from matching hashes
alone).

**Pad connectivity is reported here because the recipe emits it, and it is
named as what it is (PRIMARY metric per `pad_connectivity_audit.py`'s own
docstring) -- 48/139 fully pad-connected is a different denominator (139,
the pads-audited count, not the 102-net Stage-4-attempted count) from the
62/102 topology-solved figure above it, and the two are not
interchangeable.**

Wall times are reported, no claim made from them (507.6 s / 480.6 s / 570.8 s,
all inside a machine shared with other agents' concurrent builds/tests --
see §5 for the load context). This sits inside, not beyond, #1088's own
six-run spread of 380.2-647.2 s.

## 4. Memory probes re-run on the composed tree

### `ConstraintModel` (packed by #1088)

```
$ uv run --no-sync python3 docs/evidence/scripts/2026-08-12-router-model-memory-probe.py 2000000
N=2000000  RSS delta=0.047 GB  bytes/var=25.1

$ uv run --no-sync python3 docs/evidence/scripts/2026-08-12-router-model-memory-probe-distinct-keys.py
N=2044900  distinct net_channel_vars keys=2044900
model RSS delta=0.063 GB  bytes/var=33.0
```

Both exactly match #1088's isolated-tree figures (25.1 / 33.0 B/var). The
packed `ConstraintModel`'s storage cost is unaffected by `CnfFormula` also
being packed downstream -- expected, since the two never share a struct or
allocator arena, but measured rather than assumed.

### `CnfFormula` (packed by #1075)

`docs/evidence/scripts/2026-08-12-cnf-repr-probe-isolated.rs`, vendored onto this
branch by #1075's own preliminary docs commit, compiled directly with
`rustc -O` (no external crate dependencies -- it reproduces the `Vec<Vec<i32>>`
vs. flat-`Vec<i32>`-plus-`Vec<u32>`-offsets layouts structurally rather than
linking `temper-rust-router-core`, so this is a clean, cold-start-per-arm
measurement, same methodology as #1075's own PR description):

```
ARM A  Vec<Vec<i32>>  num_channels=2000  num_clauses=7564000  literal_count=18552000
ARM A  cold-start RSS delta = 0.394 GB  bytes/clause = 56.00
ARM A  Vec<Vec<i32>>  num_channels=6000  num_clauses=22692000  literal_count=55656000
ARM A  cold-start RSS delta = 1.183 GB  bytes/clause = 56.00
ARM C  flat Vec<i32> + Vec<u32> offsets  num_channels=2000  num_clauses=7564000  literal_count=18552000
ARM C  cold-start RSS delta = 0.097 GB  bytes/clause = 13.81
ARM C  flat Vec<i32> + Vec<u32> offsets  num_channels=6000  num_clauses=22692000  literal_count=55656000
ARM C  cold-start RSS delta = 0.292 GB  bytes/clause = 13.81
```

56.00 -> 13.81 B/clause (4.06x), exact at both scales, matching #1075's PR
description precisely. This is the first time this probe has been run
*from a tree that also carries #1088* -- previously it was only ever run on
`spike/cnf-representation` / the #1075 branch alone. Structural
cross-check: the composed tree's real `CnfFormula` (quoted in full in §2)
is exactly the "ARM C" shape the probe measures -- `literals: Vec<i32>` +
`clause_offsets: Vec<u32>`, no per-clause heap allocation -- so the probe's
number is not just reproducible in isolation, it describes the type that is
actually compiled into this tree.

## 5. Machine load

Checked for competing `route_board.py`/`pumpkin_engine` processes before
starting (none in this worktree; one unrelated heatsink-board route was
active in a different worktree during run 1, not the production board this
task routes). System memory stayed under 20 GB of 62 GB total at every
checkpoint across all three runs -- well clear of the 54-59 GB OOM range
other agents hit today. No run was relaunched; none died. Disk was tight
throughout this task (dropped to 5.7 GB free of 938 GB at one checkpoint,
driven by concurrent fleet-wide worktree/build activity, not by anything
this task wrote -- the three routed boards and the compiled probe binary
together are a few MB) and swap sat near-full for stretches; neither
affected a route (each writes a single ~1 MB `.kicad_pcb`), but it is worth
a future task checking `df -h` before assuming headroom.

## Scope held

- No `pcb/**` file touched (`git status --short pcb/` empty throughout).
- `docs/evidence/drc_ceiling.json` not touched.
- Three probe scripts and one evidence doc added/read; no source files
  under `packages/` modified by this task.
