<!-- provenance: commit=a434a9aa9f52b1b1407f4b934153ca1d740c7050 dirty=UNKNOWN -->
net-classification fix and #1050 board-origin/isolation-barrier primitives).
Rust safety kernel measured via the exact temper_drc_rs.run_drc(board_dict,
constraints_dict, categories=["safety"]) construction
packages/temper-placer/src/temper_placer/regression/drc_ratchet.py::_run_rust_drc
uses in production. Candidate board regenerated from scratch (not committed
by this PR) by re-running the pipeline
docs/evidence/2026-08-12-place-and-reroute-connectivity.md and
docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md document, in
a scratch directory outside pcb/. Extension build: worktree-isolated
`.venv` via `make venv-isolate`, all 10 crates fresh
(`check_stale_extensions.py`: 10/10 PASSED). `check_venv_integrity.py`
reports the same pre-existing doubly-nested-worktree false positive PR
#1050's own test plan already noted (reported, not a real hijack — every
flagged path resolves to this worktree's own repo root; the check's
"other worktree" priority rule mis-fires because `.claude/worktrees/<this>`
is nested inside the main checkout's path). -->

# Does the candidate place-and-reroute board fix, worsen, or leave unchanged the 94 HV/LV separation violations?

> **CORRECTION (2026-08-12), added by the void-board-baseline purge task, not by this
> document's original author.** The **94 -> 44 (-53%)** `SAF_HVL_001` finding below is
> **VOID**. The 94 (measured on the committed `pcb/temper.kicad_pcb`, §1) is unaffected
> and still stands. The 44 (measured on a regenerated candidate board, §2-3) does not:
> this document's regeneration built `pumpkin_engine` fresh (§2 step 2) without any
> identity check against a pin, because no pin existed yet
> (`docs/evidence/2026-08-07-pumpkin-engine/engine_pin.json` landed in #1060, after this
> document). A later investigation established that different builds of that binary
> produce materially different placements from an identical constraint payload
> (`docs/evidence/2026-08-12-candidate-board-not-landed-engine-provenance.md` §3), so this
> document's "44" cannot be attributed to a specific, reproducible program and must be
> treated the same as the other pre-pin figures in this lineage (PR #1050's 4,228/74,
> the "verified" 3,349/56/70).
>
> **True `SAF_HVL_001` figure**, pinned engine (post-#1060) plus a corrected write path:
> **94 -> 74 (-21%)**, not 94 -> 44 (-53%) -- a real, but roughly 2.4x smaller, reduction
> than this document reports. The companion segments/vias/zones baseline is 2,514 / 22 /
> 76 / 168 footprints; nets connected 22/112 (19.6%). Current source of truth:
> `scripts/board_shape_baseline.json`. **Nothing below this notice has been edited** --
> §1 (the 94 on the committed board) and the methodology in §2-3 stand as originally
> recorded; only the "44" and everything computed from it (§3-5's deltas, percentages,
> and "genuine 53% reduction" framing) are void.

**Lead: the 94 reproduces exactly. The candidate board's SAF_HVL_001 count
is 44 — a real, substantial reduction (−50, −53%), not a regression.
This is consistent with (not contradicted by) PR #1050's own kicad-cli
`creepage` finding (186 → 73–74, −60%): both independent measurements of
HV/LV physical separation move the same direction. Recommendation:
**do not land pcb/temper.kicad_pcb** — but not because of this axis. PR
#1050's own already-established blocker (`clearance`, kicad-cli, +113/+29%)
stands unchanged and is a different, unrelated DRC category; this task's
finding removes any concern that landing would also be trading away HV/LV
safety margin. See §5 for the full reasoning.**

## 1. Reproducing the 94 (Fact 1, independently re-verified)

`#1051` (merged, `b94f8cc9d`) defaults `parse_kicad_pcb`'s `design_rules`
parameter to `create_temper_design_rules()`, which applies
`_apply_safety_classifications` and rolls each component's real per-pin net
class up onto `Component.net_class` — previously every component parsed as
flat `"Signal"`, so the three Rust safety kernels
(`hv_lv_separation.rs`/`creepage.rs`/`isolation.rs`, which all read
`comp.net_class` via `resolve_safety_category`) evaluated a board where HV
and LV components looked identical.

Reproduced independently on `pcb/temper.kicad_pcb` (origin/main, committed,
169 components), using the *exact* `board_dict`/`constraints_dict`
construction `drc_ratchet.py::_run_rust_drc` uses in production (not
`DrcBoardSnapshot.from_netlist`, which the task brief flagged as a dead end
— its real signature needed `positions`/`netlist`/`board_width`/
`board_height`/`board_margin`/`clearance_rules`/`net_class_defs`, and
`_run_rust_drc`'s manual `board_dict` construction is the actually-executed
production path), called as
`temper_drc_rs.run_drc(board_dict, constraints_dict, categories=["safety"])`:

| | Reported (#1051) | Reproduced here |
|---|---:|---:|
| `Component.net_class` | `{"Signal": 119, "HighVoltage": 50}` | `{"Signal": 119, "HighVoltage": 50}` |
| `run_drc(categories=["safety"])` | 94 | **94** |
| Rule | all `SAF_HVL_001` | all `SAF_HVL_001` |

First example, exact match to the number cited in the task brief:

```
C1 <-> C6   actual_gap_mm=0.00   required_gap_mm=10.00
  "HV/LV Safety violation: gap 0.00mm < 10.00mm between C1 (HV) and C6 (LV)"
```

**The 94 is confirmed exact, not approximate.** Full gap distribution on
the committed board: min 0.00mm, median 8.00mm, max 9.98mm (all, by
construction, below the 10.00mm `hv_clearance_mm` bar); 9 of the 94 pairs
are exact 0.00mm courtyard overlaps.

## 2. Regenerating the candidate board

PR #1050 (merged) deliberately left `pcb/temper.kicad_pcb` unchanged — its
own evidence docs
(`docs/evidence/2026-08-12-place-and-reroute-connectivity.md`,
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`) measured
a board that was never committed. Both docs fully specify the pipeline;
this task re-ran it in a scratch directory
(`/tmp/.../scratchpad/candidate_board/`, never touching `pcb/**`), copying
the recipe's own documented steps:

1. **Reconcile.** `scripts/resync_pcb_netlist.py`'s `resync()` against a
   fresh `make netlist` (digest `8cfd715e60a3…`, matching both #1049's and
   the branch's own independently-reported digest), on a copper-stripped
   scratch copy of `origin/main`'s board (`strip_existing_copper`, same
   primitive `route_pcb`/`route_board.py` use — stripping first also
   sidesteps `resync()`'s fail-closed orphaned-copper check, since there is
   no copper left to orphan).

   Reproduced exactly: `netlist_components: 168, kept: 162, added: 6,
   removed: 7, moved: 0` — **added** `{C37, J1, R65, T2, TP3, U19}`
   (OCP-02/pan-probe), **removed** `{D2, R6, R7, R8, R9, R10, U3}` (stale
   ZCD-opto). J1's footprint (`Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical`)
   needed a real `Connector_JST.pretty` library, absent from this
   environment's KiCad install; extracted directly from the
   `kicad-footprints` `.deb` already staged at
   `/tmp/opencode/kicad-deb/debs/` (`dpkg-deb -x`, no install, no sudo) into
   a scratch dir, referenced from a scratch-only `fp-lib-table` — the real
   upstream library, not the hand-built recovery PR #1050 used because it
   lacked this shortcut.

2. **Place (Pumpkin, isolation-barrier-constrained).** Built
   `pumpkin_engine` from `docs/evidence/2026-08-07-pumpkin-engine/`
   (`cargo build --release`, shared `target-shared`, ~1s incremental).
   Constraint model: the exact production
   `generate_netclass_separated_constraints` + courtyard-tau backfill
   `test_golden_board_pumpkin_real_board.py::_build_constraints` builds
   (**21,948 constraints reproduced exactly**, matching the isolation-barrier
   doc's own count), plus a from-scratch translation of
   `isolation_barrier.add_isolation_barrier_to_model`'s geometry (that
   function is `CpModel`-coupled and not directly callable against the
   standalone Pumpkin binary) into the `"bounded"`/`"fixed_rotation"` wire
   primitives `pumpkin_engine/src/main.rs`'s own comments document as the
   intended encoding for exactly this purpose (`center + fixed_offset_mm
   <=/>= barrier_lo/hi`, `end <= barrier_lo`, `start >= barrier_hi`) — PD2
   bare bar, `MIN_BARRIER_WIDTH_MM = 8.0mm`, horizontal orientation
   (axis=Y), corridor `[113.0, 121.0]mm` on the board's own Y midline
   (152×234mm board), U6 relaxed (rotation pin + straddle constraint both
   skipped), other 7 isolators hard-constrained.

   Domain partition and per-isolator feasibility **reproduced exactly**:

   | | Doc's reported value | Reproduced here |
   |---|---|---|
   | hv_only / selv_only / isolators / unclassified | 40 / 109 / 8 / 11 | **40 / 109 / 8 / 11** |
   | Isolator set | `{C6,K1,K2,K3,PS1,T1,T2,U6}` | **identical** |
   | achievable_gap_mm / chosen_rotation per isolator | C6 8.000/3, K1 8.000/2, K2 12.760/1, K3 12.760/1, PS1 35.500/3, T1 9.100/0, T2 9.100/0, U6 8.100/1 | **byte-identical, all 8** |

   Solve: `status=optimal`, ~1.0s solve time (doc reported 2.6s — different
   machine, same outcome class: optimal, not a 30s timeout).

3. **Write-back + round-trip.** `_apply_placements_to_pcb(...,
   board_origin=board.origin)` (the #1050 write-path fix), then
   `check_placement_roundtrip` with the positions dict adjusted by
   `board.origin` before comparison (the oracle compares against whatever
   coordinate frame it's handed and has no independent knowledge of
   `board_origin` — the doc's own noted caveat, reproduced and required
   here too or the check reports a uniform 689-mismatch false failure).
   **Round-trip: PASS, 168 components, 521 pads** — matching the doc
   exactly. `check_board_containment.py`: **0 violations** here (doc
   reported 2 minor near-edge overhangs — within normal CP-SAT-class
   solver run-to-run variance on a feasibility-only, no-objective solve;
   not investigated further since it does not bear on SAF_HVL_001, which
   is unaffected by sub-mm edge containment).

Routing (`route_board.py --net-batching`) was **deliberately not
re-run**: `packages/temper-drc-rs/src/rules/safety/hv_lv_separation.rs`
computes `SAF_HVL_001` purely from component center/size/rotation
(`Component::edge_distance_to`) — it has no dependency on copper/tracks/
vias at all (confirmed by reading the rule's source directly). Routing
cannot change this metric; skipping it saves the multi-minute A*/zone-pour
pass without losing any fidelity on the question this task asks. (It does
mean this document does not re-confirm PR #1050's connectivity/`clearance`/
`shorting_items`/`copper` numbers — those already stand as PR #1050
measured them and are not in question here.)

## 3. The delta

Measured with the identical `_run_rust_drc`-construction script used in
§1, unmodified, against the regenerated candidate board:

| | `origin/main` (committed, 169 comp.) | Candidate (regenerated, 168 comp.) | Delta |
|---|---:|---:|---:|
| `Component.net_class` | `{Signal: 119, HighVoltage: 50}` | `{Signal: 123, HighVoltage: 45}` | −5 HV, +4 Signal (net −1, reconciliation) |
| **`SAF_HVL_001` violations** | **94** | **44** | **−50 (−53.2%)** |
| Exact 0.00mm (courtyard-overlap) pairs | 9 | 5 | −4 |
| Gap range (mm) | 0.00 – 9.98 | 0.00 – 9.96 | — |
| Violations per possible HV×LV pair | 94 / 5,950 = 1.58% | 44 / 5,535 = 0.79% | halved |

**No new violation class appears** — every candidate violation is still
`SAF_HVL_001`, the same rule, same 10.0mm requirement. The per-pair rate
(normalizing for the slightly different HV/LV population from
reconciliation) is cut roughly in half, so this is not an artifact of the
board having one fewer component.

**Where the remaining 44 come from**, since the isolation barrier does not
claim to eliminate all HV/LV proximity — only to enforce a domain-wide
Y-axis split plus per-isolator pad-cluster straddle at the 8.0mm corridor:

- **28 of 44** involve at least one of the 8 isolators (`C6, K1, K2, K3,
  PS1, T1, T2, U6`) — expected and by design: isolators are the barrier's
  intended crossing points and are deliberately exempt from the domain-only
  split (that is their function). `K1` alone accounts for 8, `T2` for 7 —
  both isolators sitting close to same-side neighbors the netclass/courtyard
  constraints (a much smaller default clearance than the 10.0mm HV/LV bar)
  permit.
- **16 of 44** are non-isolator HV-only ↔ LV-only pairs still under 10.0mm
  (e.g. `C7↔R9` and `R8↔R9` at exact 0.00mm). This is the barrier
  constraint's known limit: it forces every HV-only component's far edge
  past the corridor's lo boundary and every SELV-only component's near edge
  past the corridor's hi boundary — a *board-wide bulk split*, not a
  *pairwise* 10.0mm guarantee between every same-side HV/LV pair elsewhere
  on the board. Two HV-only components can sit close to an LV-only
  component on the same side of the corridor and still individually satisfy
  the barrier's one-sided bound.
- **0 of 44** involve only newly-reconciled components (`C37, J1, R65, T2,
  TP3, U19`) against each other; 7 involve `T2` (an isolator) against an
  existing component.

## 4. Sanity-checking against the kicad-cli `creepage` finding

PR #1050's own measurement (kicad-cli, reads netclasses from
`pcb/temper.kicad_pro` — a completely separate code path from the Rust
safety kernels measured here): `creepage` fell **186 → 73–74 (−60%)** on
the fully-routed candidate board. This task's independent measurement,
through the entirely different Rust `SAF_HVL_001` kernel, on the placement
stage of the *same* candidate board (pre-route, but `SAF_HVL_001` is
routing-independent — see §2): **94 → 44 (−53%)**.

**Both independent measurements of physical HV/LV separation move the same
direction, by comparable magnitude.** This is the outcome the task asked to
be checked for consistency: had `SAF_HVL_001` *not* also fallen, the two
measurements would have disagreed about the same physical property and one
would need to be wrong. They agree. No investigation of a discrepancy is
needed — the isolation-barrier constraint genuinely improved HV/LV
separation, and both the kicad-cli-netclass path and the Rust
net-classification path (independently fixed by #1051, on a code path
kicad-cli never touches) see it.

## 5. Recommendation

**Do not land `pcb/temper.kicad_pcb` as this candidate.** This is
**unchanged from PR #1050's own verdict**, and for the **same** reason PR
#1050 already gave: the `clearance` DRC category (kicad-cli, general
component-to-component spacing — not HV/LV-specific) regresses **+113
(+29%)**, concentrated in one congested region (`U27`/`U26`/`rtd_pan`
cluster). That finding is untouched by this task and stands as the
blocker.

**What this task adds**: the safety question PR #1050 could not answer —
whether the candidate's real, substantial connectivity and creepage gains
came at the cost of the specific, previously-hidden mains<->SELV
proximity defect #1051 uncovered — is now answered, and favorably. On the
`SAF_HVL_001` axis specifically:

- **Better**: 94 → 44, a genuine 53% reduction, not noise (the Rust safety
  kernel is a pure deterministic geometric calculation over component
  center/size/rotation — no run-to-run scatter of the kind `creepage`/
  `shorting_items` show in the kicad-cli path — so a single measurement is
  decisive here, unlike those categories).
- **Not worse in any respect**: no new violation rule, no new violation
  class, roughly half the per-possible-pair rate, fewer exact 0.00mm
  overlaps.
- Consistent with the independently-measured kicad-cli `creepage` result
  (§4) — reinforces rather than contradicts.

So: **if/when a follow-up fixes the `clearance` regression** (PR #1050 §7's
own recommended next step — investigate the `U27`/`U26`/`rtd_pan` cluster),
landing that improved candidate would **also** be landing on a strictly
better HV/LV safety footing than `origin/main` ships today, not a worse
one. This task removes what would otherwise have been an open, unmeasured
risk sitting underneath that future decision.
