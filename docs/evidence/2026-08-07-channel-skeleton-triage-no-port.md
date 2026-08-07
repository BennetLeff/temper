<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- backfilled: predates the evidence-provenance gate and no self-declared commit exists in this file's own content. See .evidence-provenance-allowlist. -->

# Wave 4 triage: `router_v6/channel_skeleton.py` (temper-geometry pull) — NO PORT

<!-- provenance: worktree branched from origin/main 0cd6a3a39 (2026-08-07); no production file modified -->

**Assignment:** migrate the compute in
`packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py` (464
LOC) into Rust in `packages/temper-geometry`.

**Verdict: NO PORT.** Confirms the existing recorded verdict — this module is
**BLOCKED**, not merely "spike-gated" — and the block is a Python-side
contract problem in a *different* file, not anything the Rust side can fix.
Nothing in this repo was changed except this document.

## This is not a fresh finding — it re-confirms three prior documents

| Document | Date | Verdict on `channel_skeleton.py` |
|---|---|---|
| `docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md` | 2026-08-04 | The GEOS Voronoi boundary is *not* the obstacle — an independent Voronoi (Qhull) reproduces the skeleton to <1e-9 mm on 12/12 boards. The real blocker is downstream: `constraint_model.py` builds SAT variable identity from unrounded float `repr()` plus networkx edge-insertion order, which is unsatisfiable by *any* reimplementation, bit-exact or not, until normalized in Python. |
| `docs/evidence/2026-08-04-router-v6-migration-survey.md` | 2026-08-04 | bucket: **BLOCKED** |
| `docs/evidence/2026-08-06-router-v6-status-reconciliation.md` §6–7 | 2026-08-06 | Reconciles a same-day triage doc's conflicting "PORT" call against the survey and rules **the survey is right in all 19 disagreement cases it checked, including `channel_skeleton.py`** — the triage's PORT call for this file is a documented over-call, not evidence for porting it. |

I independently re-read `channel_skeleton.py` at the current worktree HEAD
(`origin/main` 0cd6a3a39) rather than trusting the citations, to check the
diagnosis still holds:

- `channel_skeleton.py:104`: `G.add_node(p1, pos=p1)` — the node key is the
  raw `(float, float)` tuple straight off `line.coords`, no quantization
  anywhere in the file.
- `channel_skeleton.py:96-115`: edges are added to `nx.Graph` in the order
  skeleton lines/coords are iterated — insertion order, which is GEOS's
  Voronoi emission order filtered by `prepped_buffered.contains(midpoint)`
  (`channel_skeleton.py:311-322`). Nothing in this file canonicalizes that
  order.
- Confirmed by grep that `constraint_model.py:325-337` (`_create_per_net_channel_vars`,
  duplicated at 358/377) is still the consumer that turns `(node_a, node_b)`
  into `f"...{n1}_{n2}"` via `sorted([u, v])` over the raw float tuples, with
  `i` (positional index in `skeleton.graph.edges`) baked into the variable
  name — i.e. the exact contract the spike measured is still in place today.

So the diagnosis is current, not stale evidence from three days ago.

## Triage of the file's actual content (this pull's own read)

Everything in the 464 lines is one of three things:

1. **The shapely/GEOS Voronoi kernel** (`_extract_medial_axis`,
   `_extract_medial_axis_single`, lines 181–349): `voronoi_diagram()`,
   `shapely.prepared.prep(...).contains(...)`, `geom.simplify(...)`. Per the
   spike, the geometry itself is *not* the blocking boundary — Qhull
   reproduces it to sub-nanometer agreement — but it is still a call through
   GEOS via shapely, the same class of "third-party geometry library" call
   this repo already treats as a library boundary elsewhere (`edt` crate
   KTD8 rejection; scipy EDT/spsolve KTD8/KTD9 keeps). Porting it would not
   even help: the consumer contract in `constraint_model.py` fails identically
   against a Rust Voronoi as it does against GEOS, because the failure mode is
   float-`repr()`-plus-emission-order identity, not numerical disagreement.
2. **`networkx.Graph` bookkeeping** (`extract_channel_skeleton`'s node/edge
   loop, `_ensure_skeleton_connectivity`, lines 352–414): `nx.Graph`,
   `nx.connected_components`, `nx.is_connected`. The one piece of arithmetic
   inside it — Euclidean distance, `((ax-bx)**2+(ay-by)**2)**0.5` — is a
   one-line expression embedded in an O(n²) nearest-pair search over `nx.Graph`
   node objects; there is no way to extract it to Rust without marshalling the
   whole component/node structure across the FFI boundary per call, which is
   the "per-call marshalling boundary can be net-negative" trap this repo's
   own Wave 4 dispatch-readiness notes measured elsewhere (1.9x slower at
   n≈256).
3. **Orchestration / dataclass assembly**: `ChannelSkeletonStage.run` (a
   pipeline `Stage`), `validate_channel_skeleton` (a `@register_validator`
   dict/list builder), and the pad-anchoring block in
   `extract_channel_skeleton` (lines 120–172, dict/list bookkeeping over
   `ParsedPCB.components`/`pins` plus two dead expressions at lines 133–136
   already flagged by the 2026-08-04 spike as incidental findings, not
   touched here).

There is no separable numeric/geometric kernel left over once (1)-(3) are
excluded — matching the file-level verdict already on record.

## Dead-code check

Not dead code. `ChannelSkeleton`/`extract_channel_skeleton` have live
importers outside this file: `channel_widths.py`, `stage2_orchestrator.py`
(wires `ChannelSkeletonStage` into the Stage 2 pipeline), `constraint_model.py`,
`_pipeline_types.py`, `stage_ledger.py`, `channel_mapping.py`,
`deterministic/state.py`, `pcl/constraints.py`, `pcl/sat_bridge.py`. The
`@register_validator("ChannelSkeleton")` decorator registers into
`stage_validators.py`'s `run_validators()`, which is live wiring, not an
inert decorator.

## What would actually need to happen before this can be reopened

Per the 2026-08-04 spike §6/§9 (not applied, this pull didn't touch it
either): the skeleton's node coordinates need quantization at graph-build
time and edges need canonical (not insertion-order) ordering, in
`channel_skeleton.py`/`constraint_model.py`, proven behavior-neutral via the
repo's `TEMPER_*_BACKEND` A/B dispatch precedent, **before** any Rust Voronoi
question is worth reopening. That work is Python-side and out of scope for a
`temper-geometry` pull — and `constraint_model.py`, the file that owns the
actual blocking contract, is itself a separately recorded JUSTIFIED-KEEP
(`docs/evidence/2026-08-06-constraint-model-triage-keep.md`), so the
normalization work has no current owner. Flagging that gap rather than
picking it up unassigned.

Also flagging, not fixing (forbidden to edit
`docs/wave4-verdicts.yaml` per this task's constraints): the ledger entry at
`docs/wave4-verdicts.yaml:404-407` still reads "channel_skeleton is Phase 4
and spike-gated on the shapely Voronoi boundary" — language the 2026-08-04
spike (§9) already recommended correcting to "gated on the skeleton contract
normalization, which is Python work," and that correction still hasn't
landed as of this pull.

## Build/test state

No Rust code, no Python code, and no `temper-geometry` build were touched.
`cargo build --release` for `temper-geometry` was not run because nothing in
that crate changed. Disk headroom checked before and after
(`df -g /Users/bennet`): 21 GB available throughout, well above the 8 GB
floor.
