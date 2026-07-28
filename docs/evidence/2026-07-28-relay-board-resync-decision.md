<!-- provenance: commit=13807b3a dirty=false -->

# K2/K3 board/netlist inconsistency: reverted, not resynced

Base commit: `982c5a7d` (`merge: RULE 1/1a discriminate dynamically -- plus
a third dead property and a stale .kicad_pro`), branch
`docs/methodology-loop-discipline` as it stood at that commit. Work done
directly in worktree `.claude/worktrees/agent-a9733d1d504ea838d`, on a new
local branch `relay-board-resync-decision` checked out at that commit (per
the task's own instruction to target the named commit rather than the
branch's later tip).

## Decision, up front

**(b): reverted the relay change in `elec/src/`.** `pcb/temper.kicad_pcb`
was never touched (it always still had the Omron G5LE-1 footprint --
confirmed, `git status --short` clean on that file throughout this
session). `elec/src/modules.ato`, `elec/src/components.ato`,
`elec/domain_manifest.yaml`, and `docs/hardware/BOM.md` were reverted to
instantiate `Relay_SPDT`/G5LE-1 for K2/K3 again, restoring the netlist the
board's copper already matches -- **no board resync was needed or run**.
`scripts/resync_pcb_netlist.py` was read (per the task's READ FIRST list)
but not executed: there is nothing to resync once `elec/src/` matches the
board again.

## Why not resync (the falsifier)

> "Resyncing the board to the Finder part leaves the design in a more
> honest state than reverting. If embedding a part measured not to meet
> reinforced creepage is worse than a temporary board/netlist
> inconsistency, then the honest move is to revert or explicitly
> quarantine the change -- and say so."

**The falsifier FIRED (in the direction it warned about) -- resyncing
would NOT have been the more honest move, and reverting was the right
call.** Reasoning:

1. **The part's only real selling point against the incumbent was
   retracted, by this project's own later evidence.**
   `docs/evidence/2026-07-28-relay-replacement-implementation.md` adopted
   Finder `40.52.7.012.0000` on the strength of a claimed **9.2mm**
   edge-to-edge coil<->contact PCB creepage figure ("clears the 8.0mm
   target with 1.2mm margin"). `docs/evidence/
   2026-07-28-pd3-retarget-relay.md` retracts that figure directly: it was
   an **invented footprint layout** ("a DELIBERATE CHOICE by this
   footprint's author," in that document's own words), not a measurement
   of the real part. Pixel-calibrating the manufacturer's own catalog
   drawing gives a real, fixed **7.5mm** coil-to-nearest-contact
   center-to-center pin pitch -- a THT relay's pins are cast into its base
   at the manufacturer's chosen positions, not wherever a footprint author
   finds convenient. At realistic pad sizing this caps achievable
   edge-to-edge creepage at **5.300mm**, which **fails both the 8.0mm
   target (by 2.7mm) and the later-established 12.6mm PD3 target (by
   7.3mm)**. No routed slot helps: the relay's own one-piece 29x12.4mm
   moulded case sits over the entire coil-to-contact pin field (identical
   to the failure mode already on record for the incumbent G5LE-1).
2. **Finder does not clear this project's own three-way bar either.**
   The task's hard rule requires reinforced coil-to-contact isolation
   **AND** a rated DC break at 170-200V **AND** fail-safe NC topology, all
   three. The G5LE-1 fails isolation (3.50mm edge-to-edge, no
   creepage/clearance figure in its own datasheet, 2000VAC coil-to-contact
   dielectric strength below the reinforced figure) and has no DC-break
   rating above 125VDC at all. Finder fails isolation too (5.300mm
   edge-to-edge, same shortfall class, just a smaller one -- 5.3mm > 3.5mm,
   but neither clears 8.0mm or 12.6mm) and its only real improvement is
   disclosure quality on DC break (an explicit manufacturer DC1 graph vs.
   the G5LE-1's total silence above 125VDC -- see "What Finder is still
   good for" below). **Swapping to Finder would not have made this
   circuit safety-compliant** -- it would have swapped one non-compliant
   part for a different non-compliant part, while additionally converting
   the board/netlist inconsistency (itself loudly visible, 146 failing
   assertions) into a quiet, green "PASSED" that embeds the now-known-
   inadequate part as the settled state.
3. **Resyncing would have retired the one mechanically-enforced signal
   this project currently has for this problem.** No gate in this
   project's current suite (as confirmed this session --
   `check_isolation_keepout` fails for an unrelated reason, "no keepout
   zone found," not a creepage measurement; the dedicated creepage-
   measurement infrastructure this task explicitly says is owned by a
   sibling agent and not touched here) would catch a board that embeds a
   part failing its own coil-to-contact creepage requirement. Resyncing
   the board would have made `check_copper_net_consistency` -- the ONE
   gate currently flagging that K2/K3 need attention -- exit 0, and there
   is nothing else standing between that state and someone trusting the
   Finder part because "the board and netlist agree." The hard rule this
   task states directly -- *"do not let a part that fails a safety
   requirement become the settled state by default... the inadequacy must
   remain loudly visible"* -- points squarely at reverting, or at minimum
   an explicit quarantine, over a silent resync.
4. **Reverting does not manufacture false compliance either.** The
   G5LE-1's own isolation gap is exactly as unresolved after this decision
   as it was before the whole Finder excursion started -- this document,
   `elec/src/modules.ato`'s `BusDischarge` docstring, `elec/src/
   components.ato`'s `Relay_DPDT` docstring, and `docs/hardware/BOM.md`'s
   `K_DIS1`/`K_DIS2` note all say so explicitly and prominently, in the
   exact locations a future reader (human or agent) would look. Nothing
   about this decision claims the circuit is now safe; it only avoids
   trading a loud, honest failure signal for a quiet, false one.

**What Finder is still good for, reported plainly rather than dropped
(per option (a)'s own framing in the task):** the Finder catalog's
explicit DC1 breaking-capacity graph at 20-220VDC (single contact and "2
contacts in series") is a genuine, real improvement in *disclosure*
quality over the G5LE-1's silence above 125VDC -- this is not nothing, and
is exactly why it isn't dismissed here as simply "worse." It is not,
however, sufficient on its own to justify adopting a part that fails the
isolation leg of the three-way bar just as hard as the part it would
replace (differently, not less). Whoever picks up the search for a real
replacement should treat Finder's DC1 disclosure as a genuinely useful
data point on what "good" DC-break documentation looks like, separate from
this part's own creepage disqualification.

## Footprint's two physical errors

The task asked to correct, regardless of path chosen, if the footprint
survives: pin order (should be NC-COM-NO, not COM-NC-NO) and pin diameter
(1.5mm pin needs more than a 1.0mm drill). **Both were already corrected**
at this base commit (`982c5a7d`), by the PD3 re-target pass itself
(`docs/evidence/2026-07-28-pd3-retarget-relay.md`, committed as
`445432f9 fix(footprint): correct Relay_DPDT_Finder-40.52 to real
manufacturer pin geometry`) -- confirmed by reading
`pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod` directly this
session: pad "12" (NC) sits at x=-4.5mm (nearest the coil at x=-12.0mm),
pad "11" (COM) at x=+0.5mm (middle), pad "14" (NO) at x=+5.5mm (farthest)
-- NC-COM-NO order, matching the manufacturer's real drawing. All pads use
a 1.7mm drill / 2.2mm pad (0.25mm annular ring), sized for the real 1.5mm
pin. **No further geometry edit was needed or made this session.** This
session's only change to that file was a `descr` status note (see below)
marking it unreferenced.

## Files touched this session

- `elec/src/modules.ato`: `BusDischarge` reverted to `Relay_SPDT`/G5LE-1
  for `k_dis1`/`k_dis2` (import, instantiation, wiring, docstring). The
  docstring's "RELAY REPLACEMENT TRIED AND REVERTED 2026-07-28" block
  records the full investigation-and-retraction trail inline, so this
  isn't rediscovered blind by a future reader.
- `elec/src/components.ato`: `Relay_DPDT`'s docstring gets a "NOT
  CURRENTLY USED, KEPT UNREFERENCED" quarantine block, ahead of its
  original (now-superseded) adoption rationale, which is left intact for
  context.
- `elec/domain_manifest.yaml`: `discharge.k_dis1`/`discharge.k_dis2`
  domain-net entries and isolator groups reverted to the G5LE-1
  single-NC-contact form. **Also fixed**: the `power_in.ntc-no` -> `"no"`
  net-name entry, which the original swap commit claimed was an
  "unrelated pre-existing stale entry" -- that claim was wrong (see "A
  second, coupled bug found while reverting" below) -- reverted alongside
  the relay type, with the coupling now documented inline.
- `docs/hardware/BOM.md`: `K_DIS1`/`K_DIS2` row and corrected-note
  reverted to G5LE-1, with the swap-then-retraction history and the
  still-open isolation gap stated in the note, following this file's own
  existing "corrected" convention.
- `pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod`: `descr`
  prefixed with a `STATUS 2026-07-28: NOT CURRENTLY REFERENCED` note.
  Geometry unchanged (already correct, see above) -- kept as an accurate
  record of the real part in case a different, less isolation-critical
  role ever needs it.
- `pcb/temper.kicad_pcb`: **not touched** (already matched the reverted
  `elec/src/` state -- no resync needed).
- This evidence doc.

Not touched, per the task's file roster: `scripts/generate_kicad_dru.py`,
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (sibling-owned).

## A second, coupled bug found while reverting

Reverting `elec/src/modules.ato`/`components.ato` alone caused
`check_domain_partition.py` to GATE ERROR: `domain manifest declares
net(s) that do not exist in the compiled netlist: ['HV:no']`. Root cause,
confirmed by toggling the relay type back and forth and rebuilding the
netlist each time (not assumed):

- With `Relay_DPDT` (Finder, unconnected pins named `NO1`/`NO2`),
  `bypass_relay.NO` (in `PowerInput`, unrelated to K2/K3) is the **only**
  signal in the whole design literally named `NO`. atopile's net
  auto-namer collapses its net to the bare pin name `no` when there is no
  naming collision.
- With `Relay_SPDT` (G5LE-1, unconnected pins named plain `NO`),
  `k_dis1.NO` and `k_dis2.NO` **collide by name** with `bypass_relay.NO`.
  The auto-namer falls back to the longer, instance-qualified
  `power_in.ntc-no` for all three.

The original swap commit (`91f033c0`) changed `domain_manifest.yaml`'s
entry from `power_in.ntc-no` to bare `"no"`, describing this as "an
unrelated pre-existing stale entry" found in passing. **That
characterization was wrong** -- the net name is directly coupled to K2/K3's
relay type via this naming collision, not independent of it. This is now
documented inline in `domain_manifest.yaml` and reverted alongside the
relay type, restoring `check_domain_partition.py` to a real PASS (not
silently working around the GATE ERROR).

## Verification: copper-to-netlist consistency, before and after, with denominators

**BEFORE** (base commit `982c5a7d`, Finder 40.52 still wired in
`elec/src/`, board unchanged with the old G5LE-1 footprint):

```
Copper: 2482 item(s) total (Segment=2338, Via=48, Zone=96), 2482 checked (net != 0), 0 skipped.
Pads: 500 checked (exact ref+pin match in netlist), 19 skipped (no exact match).

VIOLATIONS: 146
  [orphaned-net]   139 violation(s)
  [pad-mismatch]     7 violation(s)

FAILED -- 146 violation(s)
```

(Reproduced this session by temporarily restoring the base commit's
`elec/src/modules.ato`/`components.ato`/`domain_manifest.yaml` via `git
checkout 982c5a7d -- <paths>`, rebuilding the netlist, running the gate,
then restoring this session's committed revert via `git checkout HEAD --
<paths>` -- not left in that state, confirmed clean afterward.)

**AFTER** (this session's revert, HEAD `13807b3a`):

```
Copper: 2482 item(s) total (Segment=2338, Via=48, Zone=96), 2482 checked (net != 0), 0 skipped.
Pads: 510 checked (exact ref+pin match in netlist), 9 skipped (no exact match).

PASSED -- 0 violations across 2482 copper item(s) and 510 pad(s) checked.
```

Same total copper count (2482, board untouched); pads-checked rose from
500 to 510 and violations dropped from 146 to 0 purely because the
compiled netlist's pin-name/net-name mapping for K2/K3 (and the coupled
`power_in.ntc-no` net) once again matches what the never-touched board
copper already encodes.

## Verification: full gate suite (this session, this worktree, HEAD `13807b3a`)

| Check | Result |
|---|---|
| `make netlist` | build complete, all assertions PASSED |
| `check_copper_net_consistency.py` | **exit 0** -- 0 violations, 2482 copper items, 510 pads checked / 9 skipped |
| `check_domain_partition.py` | exit 0 -- 54 declared nets across 2 domains, 10 isolators, 2 protective-impedance chains, 0 crossings/breaches/defects |
| `capacity_budget_gate.py` | exit 0 -- 0 defects |
| `mpn_fabrication_gate.py` | exit 0 -- 0 new violations (19 unrecognised-prefix MPNs reported, not silently passed) |
| `check_derived_doc_drift.py` | exit 0 -- 3 docs, 47 tables, 136 fields checked |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 -- 9/10 fresh (matches every prior session's local-dev baseline) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 -- 4/4 checks agree |
| `check_isolation_keepout.py` | **exit 3** (expected) -- no keepout zone named `MAINS_SELV_ISOLATION_BARRIER`; HV pad count 97 (matches the pre-Finder baseline exactly, confirming the revert restored this too) |
| `check_measurement_provenance.py` | **exit 5** (expected) -- pre-existing `drc_ceiling.json` provenance-tag defect, untouched by this task |
| `validate_footprints.py pcb/libs/temper.pretty` | 0 errors, 0 warnings, 7 footprints checked |
| `uv run --no-sync python -m pytest elec/validation -q` | 30/30 passed |

All nine gates this project tracks as normally-green are green. The two
designated-exception gates fire exactly as the task anticipated.

## UNVERIFIED (explicit list)

- **No replacement relay part has been found or proposed.** A real fix
  needs a manufacturer-verified relay (reinforced coil-to-contact
  isolation AND a rated DC break at 170-200V AND fail-safe NC topology)
  with a coil-to-nearest-contact pin pitch of roughly double the Finder
  40.52's 7.5mm (~14.4-14.8mm), per `docs/evidence/
  2026-07-28-pd3-retarget-relay.md` Task 4. Per the hard rule against
  unverified MPNs, none is proposed here -- this remains open for whoever
  continues the search, and `scripts/mpn_fabrication_gate.py` was run
  (see above) to confirm this session introduces no new unverified MPN.
- **Whether EN 61810-1's "Reinforced (8mm)" internal rating could
  substitute for the PCB pad-to-pad path** (the "conflation question"
  `docs/evidence/2026-07-28-pd3-retarget-relay.md` raises and explicitly
  leaves open) is not resolved by this document either -- it is a
  standards-interpretation question for a safety engineer, and this
  decision does not depend on how it resolves (both the G5LE-1 and the
  Finder fail the raw PCB measurement regardless).
- **Whether PD2 (8.0mm) or PD3 (12.6mm) ultimately governs** (the
  IEC 60335-2-6 cl. 29.2 enclosure-exception question, tracked separately
  in this project's evidence chain) is not resolved here -- this decision
  is insensitive to it: both the G5LE-1 and the Finder fail the PCB
  measurement under either target.
- **The manufacturer's own recommended PCB pattern / CAD-STEP file** for
  the Finder 40.52 was not independently re-verified this session (the
  PD3 pass's own pixel-calibration is inherited as-is, unchanged, since
  no geometry edit was needed).
- **Whether `Relay_DPDT`/the Finder footprint would be useful for any
  other, less isolation-critical role in this design** is not
  investigated here -- left in the tree unreferenced, per the task's
  instruction, in case it is.

## Hard rules -- compliance checklist

- **The inadequacy remains loudly visible.** Both the G5LE-1's own
  isolation gap and the Finder swap's tried-and-retracted history are
  stated in `elec/src/modules.ato` (`BusDischarge` docstring, the exact
  place a human or agent editing K2/K3 next would look),
  `elec/src/components.ato` (`Relay_DPDT` docstring), and
  `docs/hardware/BOM.md` (`K_DIS1`/`K_DIS2` corrected-note) -- not only in
  this evidence doc.
- **No unverified MPN proposed.** No new relay MPN is proposed anywhere in
  this document; `scripts/mpn_fabrication_gate.py` run this session:
  PASSED, 0 new violations.
- **No `git stash` used anywhere this session.** Temporary inspection of
  the base-commit's pre-revert files used `git checkout 982c5a7d --
  <paths>` / `git checkout HEAD -- <paths>` on named paths, never stash.
- **No `run_in_background`; no waiting on background jobs.** Everything
  foregrounded, including `uv sync --all-packages` (run once, into this
  worktree's own previously-empty `.venv`) and every `ato build` /
  gate-script invocation.
- **No additional worktrees.** Worked entirely in this task's
  already-assigned worktree, on a new local branch checked out at the
  named base commit.
- **`uv run --no-sync` used throughout** for every gate-script invocation
  after the one `uv sync --all-packages` at the start.
- **Commits made after each meaningful step**: relay-type revert
  (`e9f22ee2`), quarantine documentation across the remaining files
  (`35110f04`), and the coupled `power_in.ntc-no` net-name fix
  (`13807b3a`) -- not batched into one commit.
- **Coordination**: stayed within this task's file roster
  (`pcb/temper.kicad_pcb` -- untouched; `elec/src/`; the Finder footprint;
  this evidence doc; plus `elec/domain_manifest.yaml` and
  `docs/hardware/BOM.md`, both directly downstream of the relay-type
  decision and necessary to keep the gates honest). Did not touch
  `scripts/generate_kicad_dru.py` or
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (sibling-owned).
- Not pushed.

## Falsifier verdict, restated

> "Resyncing the board to the Finder part leaves the design in a more
> honest state than reverting. If embedding a part measured not to meet
> reinforced creepage is worse than a temporary board/netlist
> inconsistency, then the honest move is to revert or explicitly
> quarantine the change -- and say so."

**Fired.** Embedding a part this project's own later measurement shows
does not meet reinforced creepage is worse than a temporary, loudly-
failing board/netlist inconsistency -- resyncing would have silenced the
one mechanically-enforced signal currently pointing at this problem
without making the circuit any safer. The honest move was to revert, said
so explicitly and in multiple places a future reader will actually see,
and leave the underlying isolation gap exactly as visible as it already
was.
