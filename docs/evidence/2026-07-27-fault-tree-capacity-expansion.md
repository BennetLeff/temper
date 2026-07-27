# Fault-tree capacity expansion: third OR package, UVL-02 wired

**Date:** 2026-07-27
**Scope:** `elec/src/modules.ato::SafetyInterlock` (new `fault_or3` instance
and wiring), `LogicUVLOComparator` docstring.

## Falsifier (stated before implementing)

**"Adding a third `SN74HC4075` package as a single merge point ahead of
`latch.A1` does not actually create reachable SET-path capacity, because
`capacity_budget_gate.py`'s reachability model requires a gate's own
output to lead to the SET pin, not just an unoccupied input pin."**

**Did not fire.** `capacity_budget_gate.py` confirms 3 genuinely
`AVAILABLE` SET-path inputs after the change (0 before), each verified by
the gate's own BFS reachability check, not a naive pin-occupancy count.

## What was added

`docs/hardware/UVL02_DESIGN.md` SS7.1: both `SN74HC4075` fan-in packages
(`fault_or`, `fault_any_or`) were fully occupied on their SET-aggregation
paths -- `fault_or` gate 3 and `fault_any_or` gate 3 are dead ends (their
`Y3` outputs drive nothing), and `fault_any_or`'s gate 2 only reaches the
RESET qualifier, not the SET input. Two fully-designed circuits (OCP-02,
UVL-02) had no SET-path input to wire into.

Per the design doc's remediation option 2 (chosen over reworking the
existing packages' dead gate3s into a wider cascade, which "adds a gate
delay to EVERY fault path" the same way this does, while additionally
requiring re-verification of all existing connections):

**Added `fault_or3`, a third `SN74HC4075DR`** (same real, already-used MPN
-- no new part number). Wired as two gates:

- **gate1** (new-source aggregator): `A1 = uvlo_logic.fault.line` (UVL-02,
  wired), `B1` = GND (reserved for OCP-02, NOT wired -- see below), `C1` =
  GND (spare).
- **gate2** (merge with existing bus): `A2 = fault_any_or.Y1` (the
  existing 7-source SET bus), `B2 = fault_or3.Y1` (gate1's output), `C2` =
  GND (spare). `Y2` now drives `latch.A1`, replacing the previous direct
  `fault_any_or.Y1 ~ latch.A1` connection.
- **gate3**: entirely unused, inputs tied GND (genuine headroom beyond
  the slots above, same convention as the existing packages' dead
  gate3s).

`fault_any_or.Y1`'s OTHER consumer (`fault_any_or.Y1 ~ fault_any_or.A2`,
the RESET-qualifier feed) is untouched -- only the SET-path consumer was
redirected.

## OCP-02: still NOT wired (deliberate)

`fault_or3.B1` is a real, reachable SET-path input reserved for OCP-02,
but OCP-02's fault is **not connected to it**. `SecondaryOCPComparator`
remains un-instantiated in `main.ato`. Its sensing domain is unresolved:
the design places an INA240 shunt in `DC_BUS_RTN`, which sits at ~170V
common mode in this doubler topology (per the SELV redesign) against the
INA240's -4V to +80V input range -- an INA240 wired there would see a
common-mode voltage roughly double its rated maximum. Wiring a fault
source into working aggregation logic while the upstream sensing circuit
cannot actually work would look connected on inspection while never being
able to assert correctly, which is worse than leaving it unwired. The
reserved input is capacity held ready for whenever that topology decision
is made, not a promise that it currently works.

## Capacity: before / after (`scripts/capacity_budget_gate.py`)

| | Before (HEAD before this change) | After |
|---|---|---|
| Packages inspected | 2 | 3 |
| Nets inspected | 162 | 165 |
| Pins inspected | 24 | 36 |
| SET-path inputs evaluated | 18 | 27 |
| **AVAILABLE** | **0** | **3** |
| UNUSABLE | 18 | 24 |
| OCCUPIED (groups) | 11 | 14 |
| Gate exit code | 0 (PASSED -- 0 defects) | 0 (PASSED -- 0 defects) |

The 3 `AVAILABLE` inputs are `fault_or3.B1` (reserved for OCP-02),
`fault_or3.C1` (spare), and `fault_or3.C2` (spare) -- all confirmed by the
gate's BFS as reaching `SN74HC00DR.A1`, the SET pin. `fault_or3.A1` is
now `OCCUPIED` by `uvlo_logic` (UVL-02), no longer available -- it did
the job it was added for. `fault_or3` gate 3's three inputs are
`UNUSABLE` (`gate3 output Y3 drives nothing (dead gate)`), matching the
existing dead-gate3 pattern on the other two packages -- genuine extra
headroom, not immediately usable without a further OR stage, exactly the
same situation `fault_or`/`fault_any_or` gate 3 were already in.

**The gate's own exit code was 0 both before and after** -- it only ever
fails on a `capacity_defect` (a fault wired to a dead gate), which never
existed here. The meaningful number for this task is the `AVAILABLE`
count, not the exit code: 0 -> 3.

## Propagation-delay recheck against OCP-01's <1us budget

`SAFETY_INTERLOCK_DESIGN.md` SS9 models the fault path as a single lumped
"logic" stage (OR gate 10ns + latch 20ns + output buffer 20ns = 50ns),
giving OCP-01 a documented total of 131ns (33ns detection + 50ns logic +
48ns UCC21550). **This lumped model does not reflect the actual gate
count already in `modules.ato` before this change** -- OCP-01's real path
already cascades 3 OR gates (`fault_or` gate1 -> gate2 -> `fault_any_or`
gate1) plus 2 NAND gates (`latch` gate1 as inverter, gate2 as the
bistable) = 5 logic gates, not the ~2 the lumped model assumes. This is a
pre-existing documentation gap, not introduced by this change; it is
reported here because this task specifically asks for the delay margin.

Rigorous worst-case bound, using real datasheet propagation delays
(TI SN74HC4075 and SN74HC00, commercial temperature range -40 to 85C).
Neither part is characterized at exactly VCC=3.3V; the 2V column is used
as a conservative (safe, upper-bound) stand-in since propagation delay
decreases monotonically with VCC from 2V to 4.5V and no 3.3V datapoint
exists in either datasheet:

| Part | VCC=2V max tPD (-40 to 85C) |
|---|---|
| SN74HC4075 (OR gate) | 125 ns |
| SN74HC00 (NAND gate) | 115 ns |

| | Gate count (OR / NAND) | Logic delay (worst case) | + detection (33ns) + UCC21550 (48ns) | Margin to 1us |
|---|---|---|---|---|
| **Before** (2 packages) | 3 OR + 2 NAND | 3(125)+2(115) = 605 ns | **686 ns** | **314 ns (31.4%)** |
| **After** (3 packages, this change) | 4 OR + 2 NAND | 4(125)+2(115) = 730 ns | **811 ns** | **189 ns (18.9%)** |

**OCP-01 still clears its <1us budget with 189ns (18.9%) of margin under
this conservative, full-worst-case, commercial-temperature-range bound**
-- the new gate costs 125ns of budget, taking the margin from 31.4% to
18.9%. This is a real, reported reduction in margin, not zero, matching
the rationale already given in `docs/hardware/UVL02_DESIGN.md` SS7.1 for
preferring a fresh package over reworking the existing cascade (which
would add the same one gate of delay to the same path, with more
re-verification risk).

Using the project's own existing lumped model instead (50ns logic,
before this change's more rigorous recount): 131ns before, and adding one
conservative worst-case OR-gate estimate (125ns) on top gives ~256ns
after -- both trivially inside the 1us budget. The two models disagree in
absolute terms (the lumped lumped-model total looks nowhere near as
tight as the gate-accurate one) because the lumped model was never
updated when the fault tree grew from a hypothetical single-OR-gate
design to the actual multi-package cascade; that discrepancy predates
this change and is noted here rather than silently carried forward.

## UNVERIFIED

- Neither SN74HC4075 nor SN74HC00 is characterized at exactly VCC=3.3V in
  the TI datasheet; the 2V column is used as a conservative bound rather
  than an interpolated 3.3V estimate, so the "before/after" delay figures
  above are a safe upper bound, not a measured or interpolated value.
- TLV3201's own propagation delay remains unmeasured (no timing model in
  `TLV3201_ngspice.lib`), unchanged from the pre-existing state and
  outside this task's scope.
- The lumped 50ns logic budget in `SAFETY_INTERLOCK_DESIGN.md` SS9 was
  found to undercount the real gate depth during this task; it was not
  corrected here (out of scope for an elec/src/*.ato-only task) but is
  flagged as stale.
