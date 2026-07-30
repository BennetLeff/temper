<!-- provenance: commit=d510f4ede1ce0f3db343776f024c0f8a36085675 dirty=true -->

# Delete U3 (H11L1 mains-ZCD optocoupler) and its dedicated circuitry

Base commit: `d510f4ede1ce0f3db343776f024c0f8a36085675` (`main` tip,
`Merge pull request #481 from BennetLeff/fix/stale-zone-eligibility-tests`).
Work done in a fresh worktree
(`/private/tmp/claude-501/.../scratchpad/wt-zcd-delete`) on branch
`fix/delete-zcd-optocoupler`, per the task's "own worktree, never the
shared checkout" constraint. `dirty=true`: this doc is committed alongside
the uncommitted-at-write-time source/manifest/firmware edits it describes,
same convention as other same-PR evidence docs in this repo.

**Referenced background docs not found.** The task cited
`docs/evidence/2026-07-30-zcd-protective-impedance-viability.md` and
`docs/evidence/2026-07-30-pd3-isolation-mechanism-alternatives.md` as
established justification from "two independent analyses this session."
Neither file exists anywhere in this worktree, `origin/main`, or any other
worktree checked (`find` across all sibling worktrees under
`/private/tmp/claude-501` and `/Users/bennet/Desktop/temper*`). Proceeding
on the justification stated directly in the task (no firmware consumer, no
architectural role, no safety-chain wiring, 8.560mm barrier failing the
12.6mm PD3 target) since it is independently verifiable against this
repo's own source, not on the missing docs' authority. Flagged, not
silently assumed resolved.

## Why U3 has no function in this design

- **No firmware consumer.** `PIN_ZCD_INPUT` (`temper_pins.h`) had exactly
  one occurrence in `firmware/` before this change: its own `#define`.
  Nothing read it (`grep -rn "PIN_ZCD_INPUT" firmware/` returned only the
  definition line).
- **Different signal from `pll_control.c`'s "ZCD".** `pll_control.c`'s ZCD
  is the CURRENT zero-crossing (CT + comparator), delivered via an injected
  MCPWM capture-channel handle (`cap_chan`), never through
  `PIN_ZCD_INPUT`/GPIO13. `hal_timer.h`'s "Capture/compare for ZCD edge
  timing" comment (line 9) refers to this current-ZCD/ZVS-phase path (its
  own module docstring: "Phase measurement for ZVS") -- confirmed NOT
  referring to the mains signal, so left untouched per the task's
  instruction.
- **No architectural role.** DC-bus resonant converter; soft-start is
  time-delayed (confirmed no `zcd`/`ZCD_ISO` reference anywhere in
  `firmware/main/`'s state-machine or soft-start logic).
- **No safety-chain wiring.** `zcd`/`ZCD_ISO`/`zcd_opto`/`zcd_in` do not
  appear anywhere in `SafetyInterlock`, OCP, OVP, or WDT wiring in
  `elec/src/main.ato` or `modules.ato`.
- **Isolation barrier failure.** U3 (onsemi H11L1TVM, DIP-6_W10.16mm) gave
  8.560mm HV<->SELV pad separation (`domain_manifest.yaml`'s own prior
  isolator entry), against this design's 12.6mm PD3 target -- confirmed via
  the real-board copper-to-copper checker
  (`test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`'s
  sibling `test_the_seven_known_intra_footprint_blockers_are_now_visible`
  names U3 as one of the seven parts with an intra-footprint reinforced-
  creepage violation under the current 12.6mm/300V-row requirement).

## What was identified as ZCD-only before cutting

Traced every net and component touching `power_in.zcd`, `power_in.zcd_out`,
`power_in.zcd_opto`, and `mcu.zcd_in` in `elec/src/modules.ato` /
`elec/src/main.ato` before making any edit.

**Components (all exclusively serving mains ZCD, all removed):**

| Ref (pre-change) | Instance path | Part | Role |
|---|---|---|---|
| R6 | `power_in.r_zcd_top1` | 220k 1206 | HV divider top 1 |
| R7 | `power_in.r_zcd_top2` | 220k 1206 | HV divider top 2 |
| R8 | `power_in.r_zcd_bot` | 10k 0603 | HV divider bottom |
| D2 | `power_in.d_zcd_clamp` | BZT52C3V3 | 3.3V zener clamp |
| R9 | `power_in.r_zcd_opto` | 430R 0603 | Opto LED series resistor |
| U3 | `power_in.zcd_opto` | H11L1TVM | Optocoupler (the isolator) |
| R10 | `power_in.r_zcd_pullup` | 10k 0603, 1% | SELV-side open-collector pull-up |

Plus the `H11L1` component type definition in `components.ato` (used
nowhere else) and the `zcd_in` `ElectricLogic` member of the `MCU` module
(`modules.ato`, wired only to `mcu.IO13`, used nowhere else).

**Nets (all exclusively ZCD, all removed from the compiled design and the
manifest):**

- `zcd` -- HV-side divider tap (`power_in.r_zcd_top2.p2` /
  `power_in.r_zcd_bot.p1` / `power_in.d_zcd_clamp.K` /
  `power_in.r_zcd_opto.p1`).
- `a` (auto-named) -- between `r_zcd_opto.p2` and `zcd_opto.A` (R9-U3).
- `power_in.r_zcd_top1-p2` (auto-named, between R6.p2/R7.p1) -- was never
  separately declared in `domain_manifest.yaml` to begin with (an internal
  HV divider node with no manifest entry is not a gate requirement --
  `check_domain_partition.py` only requires declared nets to resolve, not
  every compiled net to be declared), so no manifest edit was needed for
  it; noted here only so its disappearance in the netlist diff is
  accounted for.
- `ZCD_ISO` -- SELV-side, `power_in.zcd_out.line` / `mcu.zcd_in.line`.

**Freed:** `mcu.IO13` (ESP32-S3), confirmed no longer wired to anything --
the compiled netlist now carries it as its own single-pin placeholder net
`io13`, the same convention every other genuinely-unwired MCU pin already
gets (`usb_dn`, `io40`, `io41`, `io42`, `io45`, `io46`, `io48`, ...).

## What was left untouched because it is shared

- **`power_in.gnd`** (PowerInput's SELV ground signal). Used by
  `zcd_opto.GND`/`zcd_out.reference`, but ALSO by the relay-drive path
  (`q_relay_drv.S`, `power_15v.gnd`, `r_gate_pd.p2`) inside the same
  module. Only the ZCD wires into it were removed; the signal itself and
  all its other connections are untouched.
- **`+3V3`/`vcc_3v3` net at the top level** (`main.ato`'s `vcc_3v3`, the
  MCU's own 3.3V supply net). `power_in.vcc_3v3` (the module-level PORT
  that fed only the ZCD pull-up and opto VCC) was removed, but the net
  itself is unaffected -- it is tapped by many other consumers
  (`power_mgmt.power_3v3.vcc`, `hb.power_3v3.vcc`, `ct_sense.vcc_3v3_ct`,
  `rtd_pan.power.vcc`, `safety.power_3v3.vcc`, `mcu.power.vcc`) that this
  change does not touch.
- **`hal_timer.h`'s "Capture/compare for ZCD edge timing" comment** --
  confirmed (see above) to describe the current-ZCD/ZVS-phase capture path
  used by `pll_control.c`, not the mains signal. Left untouched.
- **The historical "ISOLATOR-BARRIER CASCADE CHECK" comment block**
  (`domain_manifest.yaml`, describing a 2026-07-26/27 investigation that
  once found `power_in.zcd_opto` among components sharing a bridge
  finding). This is a dated record of a past measurement, not a live
  declaration this gate re-evaluates -- left as-is rather than rewritten,
  to avoid altering historical evidence prose outside this change's scope.

## Files changed

- `elec/src/modules.ato`: removed the `H11L1` import; removed
  `PowerInput`'s `vcc_3v3`/`zcd`/`zcd_out` signal declarations; removed the
  entire ZCD divider/clamp/opto/pullup block (7 components, all wiring);
  removed `MCU`'s `zcd_in` member and its `mcu.IO13` wiring.
- `elec/src/components.ato`: removed the `H11L1` component type definition
  (dead after the above; used nowhere else).
- `elec/src/main.ato`: removed `power_in.vcc_3v3 ~ vcc_3v3` and the
  `power_in.zcd_out.line ~ mcu.zcd_in.line` / `override_net_name =
  "ZCD_ISO"` block.
- `firmware/components/hal/include/temper_pins.h`: removed
  `#define PIN_ZCD_INPUT 13`; fixed the now-dangling "IO13 is ZCD"
  parenthetical on the `PIN_SPI_MISO` comment (the mains-ZCD function IO13
  referenced no longer exists; IO13 is simply unused now).
  `hal_timer.h` NOT touched (see above).
- `elec/domain_manifest.yaml`: removed the `zcd` and `a` net declarations
  from the `HV` domain list; removed `ZCD_ISO` from the `SELV` domain
  list; removed the `power_in.zcd_opto` isolator entry (replaced with a
  dated removal note); updated the `PWR_RTN`-net comment listing
  "isolators below (C6, PS1, T1, U3)" to drop U3 with a pointer to this
  doc.

## Netlist diff, fully accounted for

`make netlist` before and after, compared **by declared `instance_path` /
pin, not by ref designator** -- ref designators are NOT stable across a
source-side add/remove in this build (`domain_manifest.yaml`'s own
long-standing comment: "stable across ref-designator reshuffles ... unlike
the absolute path prefix"). A raw `diff` of the two `.net` files is
dominated entirely by every downstream ref-designator renumbering after
the 7 removed components and is not a meaningful "what changed" signal on
its own; the component-identity-aware diff below is.

**Nets removed (4):** `ZCD_ISO`, `a`, `power_in.r_zcd_top1-p2`, `zcd` --
exactly the four ZCD-only nets enumerated above.

**Nets added (1):** `io13` -- the freed MCU pin's placeholder net, in the
same auto-naming convention KiCad/atopile already gives every other
unwired MCU pin (confirmed identical treatment for `usb_dn`, `io40`,
`io41`, `io42`, `io45`, `io46`, `io48`, etc.) -- not a new logical net.

**Nets with reduced membership (4), by exactly the ZCD components' pins,
nothing else added or removed on any of them:**

- `+3V3`: lost `power_in.r_zcd_pullup.1`, `power_in.zcd_opto.6`.
- `PWR_RTN`: lost `power_in.d_zcd_clamp.2`, `power_in.r_zcd_bot.2`,
  `power_in.zcd_opto.2`.
- `ac_l`: lost `power_in.r_zcd_top1.1`.
- `gnd`: lost `power_in.zcd_opto.5`.

**Component instances removed (7):** `power_in.d_zcd_clamp`,
`power_in.r_zcd_bot`, `power_in.r_zcd_opto`, `power_in.r_zcd_pullup`,
`power_in.r_zcd_top1`, `power_in.r_zcd_top2`, `power_in.zcd_opto` --
exactly the seven-component table above. **Component instances added: 0.**

Every other declared net's membership is byte-identical between before and
after (159 nets in common, 0 with any other change). Nothing else moved.

## Gate results, before / after

All run from this worktree with `uv run --no-sync`, against a freshly
rebuilt `elec/build/default.net` (`make netlist`) at each state. "Before"
figures for netlist-driven gates use the pre-edit netlist/manifest
(`before.net` / `origin/main`'s `domain_manifest.yaml`) with
`--skip-freshness-check` where the tool's own mtime guard would otherwise
object to comparing an old snapshot against a newer source tree in the
same worktree.

| Gate | Before | After |
|---|---|---|
| `check_domain_partition.py` | PASSED -- 54 declared nets, 10 isolators, 169 components, 0 violations | PASSED -- 51 declared nets, 9 isolators, 162 components, 0 violations |
| `check_net_classification.py` | (repo-wide source scan; unaffected by this change's category) | PASSED -- exit 0 |
| `check_copper_net_consistency.py` | PASSED -- 0 violations across 2482 copper items / 512 pads | **FAILED -- exit 3, 402 violations** (see below) |
| `check_evidence_provenance.py` | n/a (this doc is new) | see below |

`check_copper_net_consistency.py` regression is expected and is exactly
the consequence the task called out: `pcb/temper.kicad_pcb` was
deliberately left untouched (still has U3's footprint, still has the old
copper for `zcd`/`ZCD_ISO`), while the compiled netlist lost 7 components
and every subsequent ref designator shifted. The board is not stale in the
"forgot to rebuild" sense the gate's freshness check guards against -- it
is stale in the "needs the resync step this task explicitly deferred"
sense, and the gate correctly reports that. It is not evidence of a defect
in the `elec/src/`/manifest edits themselves; `check_domain_partition.py`
(which reasons over the compiled netlist and manifest only, never the
board) stays clean at both 0 violations.

## U3's own creepage violation

**Structurally confirmed gone at the source/manifest level:**
`check_domain_partition.py`'s declared-isolator count dropped 10 -> 9 (U3's
`power_in.zcd_opto` entry gone); the compiled netlist carries zero
`H11L1TVM` parts and zero components at `instance_path ==
"power_in.zcd_opto"`. There is no longer any component in the design for
an intra-footprint HV<->SELV violation to attach to.

**`scripts/measure_cross_domain_creepage.py` WAS found and ported in.**
Correcting an earlier draft of this doc: the branch `feat/pairwise-
creepage-tool` exists locally (`git branch -a`; not pushed to `origin`,
which is why `git ls-remote origin` alone missed it) and was reachable via
`git show feat/pairwise-creepage-tool:scripts/measure_cross_domain_creepage.py`.
Copied into this worktree's `scripts/`. It measures HV-pad<->SELV-pad
**inter-component** creepage from `pcb/temper.kicad_pcb` +
`domain_manifest.yaml` directly (no compiled-netlist dependency) -- it is
NOT the right instrument for U3's violation, which is **intra-component**
(U3's own primary pins vs. its own secondary pins, both on the same
DIP-6 footprint). Run at `--min-creepage-mm 12.6` for completeness: before
99 HV / 221 SELV pads, 21879 pairs, 196 violations; after 93 HV / 218 SELV
pads, 20274 pairs, 189 violations (fewer pads/pairs simply reflects the
manifest no longer declaring `zcd`/`a`/`ZCD_ISO`, so those board pads drop
out of classification -- expected, not a safety improvement in itself,
since it is the un-resynced board's old copper, not new geometry). U3 does
not appear in either pair list, before or after, because this tool never
checked intra-footprint gaps to begin with.

**The intra-component check is `verify_iec60335_compliance` via
`isolators:` groups, and here the resync gap actively produces a MISLEADING
result -- this is the most important finding in this doc.**
`test_clearance_copper.py::test_the_seven_known_intra_footprint_blockers_are_now_visible`
asserts `intra == {"C6", "K1", "K2", "K3", "T1", "U3", "U7"}` and **still
passes after this change** -- but not because it is still correctly
checking U3. Deleting U3 (and D2, R6-R10) shifted every subsequent
`U`-prefix ref designator down by one slot in the freshly compiled
netlist, confirmed directly:

| Ref | Before (this change) | After (this change) |
|---|---|---|
| U3 | H11L1TVM (the ZCD opto, now deleted) | LMR51430XDDCR (`power_mgmt.buck_3v3.buck`) |
| U7 | UCC21550BDWKR (`hb.gate_hs.driver`, the OTHER declared isolator) | SS14 (`hb.gate_hs.boot_diode`, not an isolator) |

The test reads `pcb/temper.kicad_pcb`'s footprint physically labeled "U3"
(still the real DIP-6 H11L1, board untouched) and classifies its pads
using the FRESHLY COMPILED netlist's idea of what ref "U3" and ref "U7"
now mean -- a buck converter and a boot diode, neither the part the test's
own docstring is talking about. That it still produces the identical
7-string set `{"C6","K1","K2","K3","T1","U3","U7"}` post-shift is
coincidental ref-label collision, not a re-verified finding about the
buck converter or boot diode actually having their own intra-footprint
violations (they may or may not; not independently checked here). **This
specific test's "PASS" must not be read as confirmation that U3's
violation persists, disappeared, or anything else about U3 -- it is
currently answering a different question than its name and docstring
claim, purely as a byproduct of the un-resynced board.** This is exactly
the class of failure `docs/METHODOLOGY.md`'s provenance discipline exists
to catch, and it is called out here rather than reported as a clean pass.
This will resolve itself automatically once the board is resynced (ref
designators will then match instance paths 1:1 again by construction of
the resync process).

The honest state of the evidence, therefore: U3's own intra-footprint
violation is **structurally eliminated in the design** (no such component
exists to check any more) but **not independently re-measured against the
real board**, because the real board still physically contains the part
this task was explicitly told not to touch, and the one test that claims
to check it is -- as of this change -- silently checking a different
component instead. Confirming U3's physical removal actually clears the
violation is a board-resync-time verification step, not something
demonstrable from source/manifest changes alone.

## Requirements/safety test suite: before / after

`packages/temper-placer/tests/requirements/safety/` (90 tests):

- **Before** (via a same-fixture-function comparison against the saved
  pre-edit netlist/manifest, since the real-board fixture reads repo-root-
  relative paths at import time and cannot be pointed at a second
  worktree without one): `test_temper_board_clearance_compliance` was
  ALREADY failing -- its own docstring says so explicitly ("This test is
  therefore expected to FAIL until the board is re-placed against copper-
  extent-aware constraints... deliberately left failing"), and independent
  of that, its earlier `non_exempt_proximity` assertion was independently
  already red before this change too (6 pre-existing, ZCD-unrelated
  findings: RTD-pan resistors vs. `power_in.r_bleed2`, a tank-cap/buck-3v3
  boot-cap pair, a thermal-hysteresis resistor vs. `power_in.d2`).
  `test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`
  PASSED (K1's `inter` figure measured exactly 11.530mm, matching the
  hardcoded expectation).
- **After** (actual `pytest` run, this worktree): 88 passed, 2 failed. Of
  the 88 passes, one (`test_the_seven_known_intra_footprint_blockers_are_
  now_visible`) is a coincidental pass, not a meaningful confirmation --
  see "U3's own creepage violation" above for the ref-collision that makes
  it silently check a buck converter and a boot diode instead of U3 and
  U7. Not counted as a genuine regression or a genuine confirmation
  either way; flagged on its own.
  - `test_temper_board_clearance_compliance`: still FAILED (as expected,
    unchanged verdict) -- `non_exempt_proximity` findings rose from 6 to
    14 and `coverage_ratio` dropped from 94.1% to 89.9% (still above the
    85% floor, so that specific assertion still passes). The 8 new
    findings are a mechanical consequence of the SAME board/netlist
    ref-designator desync as the copper-net-consistency gate above: the
    7 deleted ZCD components' old PCB positions and every subsequently-
    renumbered ref no longer resolve to their old net classification, so
    the fixture's ref-to-domain-net lookup (keyed through the freshly
    recompiled netlist) treats a batch of physically-real, still-placed
    components as newly "unclassified" and checks their raw proximity to
    the nearest HV part. Not a real new hazard -- an artifact of the
    deferred resync, same root cause as the copper-net gate regression.
  - `test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`:
    newly FAILED -- K1's `inter` figure moved from 11.530mm to
    11.756mm. Same root cause: K1's "nearest classified HV neighbor"
    pairing is recomputed from the same desynced ref/domain mapping, and
    picks a different candidate/measurement post-shift. `K1`'s own
    `intra` figure (8.000mm, the part's own footprint limitation,
    independent of any other component's classification) is UNCHANGED.

Both regressions are traced to the identical, single root cause (real
board vs. freshly recompiled netlist ref-designator desync, expected and
called out by the task itself) and are expected to clear once
`pcb/temper.kicad_pcb` is resynced to remove U3, R6-R10, D2 and their
copper.

## What remains: board-level resync (explicitly NOT done here)

`pcb/temper.kicad_pcb` still carries U3's DIP-6 footprint, R6/R7/R8/R9/R10,
D2, and their copper (traces/zones on `zcd`/`a`/`ZCD_ISO`), per the task's
explicit instruction to leave it alone (other sessions are actively
changing the board on `main`). Concretely still outstanding:

- Remove U3, R6, R7, R8, R9, R10, D2 footprints and their copper from
  `pcb/temper.kicad_pcb`.
- Re-run `scripts/resync_pcb_netlist.py` (or the placer's normal
  resync/re-place path) against the post-deletion netlist.
- Re-run `check_copper_net_consistency.py` and confirm it returns to 0
  violations.
- Re-run `packages/temper-placer/tests/requirements/safety/` and confirm
  `test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`
  returns to its pre-change PASS state, and that
  `test_temper_board_clearance_compliance`'s `non_exempt_proximity`
  finding count drops back toward its pre-change baseline (6, itself a
  separate pre-existing issue this change does not attempt to fix).
- Per `AGENTS.md`'s "Board Change -> DRC Ceiling Re-measurement" section,
  whichever session performs that resync must re-measure and update
  `power_pcb_dataset/drc_ceiling.json` in the SAME change, not as a
  follow-up.
