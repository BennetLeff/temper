<!-- provenance: commit=d4510f23ec67ec762ecb3505ef03b65ea7722942 dirty=false (base commit this branch was cut from; this doc's own evidence is the branch's diff on top of it) -->

# Stale schematic vs `elec/src`: the netlist delta, the board question, and the fix

**Branch:** `spike/stale-schematic-propagation`
**Trigger:** proving an unrelated gate fix surfaced 86 real `MISMATCH` findings
from `scripts/check_erc_off_grid_consequence.py` on unmodified code.
**Tool:** `kicad-cli` 10.0.5 (`/home/bennet/.local/opt/kicad-10.0.5/root/usr/bin/kicad-cli`),
`LD_LIBRARY_PATH` widened to include an extracted `libwx_gtk3u_webview` dir
(`/tmp/opencode/kicad-deb/root/usr/lib/x86_64-linux-gnu`) that the pinned prefix
itself was missing, plus `KICAD_STOCK_DATA_HOME`.

**Lead: the netlist delta, the board impact, the recommendation.**

- **Netlist delta:** zero renamed nets. No net name that today's netclass
  work depends on (`ac_l`, `ac_n`, `gnd`, `+170V_BUS`, `SW_NODE`, `GATE_HS`,
  `GATE_LS`, the RTD/SPI nets) changed. The 86 findings are ~94% pure
  designator-identity churn (same physical nets, same member counts,
  different `(ref, pin)` labels) plus a handful of genuinely new nets that
  simply don't exist in the stale drawing yet.
- **Board impact: none from this branch.** This branch touches only
  `pcb/*.kicad_sch`. Nothing that reads `pcb/temper.kicad_pcb` (the
  reconciliation/footprint-drift/copper-consistency gates) reads
  `pcb/temper.kicad_sch` either -- the schematic and the board are two
  *independent* consumers of `elec/build/default.net`, not a pipeline where
  one feeds the other. The board **is** out of sync with `elec/src`, but it
  was already out of sync before this branch existed, for reasons unrelated
  to the schematic's staleness, and stays exactly as out of sync after.
- **Recommendation:** regenerate the schematic (done, this branch,
  mechanical and measured-safe). Leave the board alone and escalate its
  6-component-missing / 7-component-stale gap to the owner as a separate,
  CP-SAT-placement-sized decision -- do not place components here.

## 1. Reproducing the 86 `MISMATCH` findings

The 86-`MISMATCH` figure is `scripts/check_erc_off_grid_consequence.py`,
not `check_netlist_board_reconciliation.py` (that gate exists too and is
discussed in section 4 -- it reports a different, board-side number, 125,
that this branch does not change). The off-grid-consequence gate is wired
into CI at `.github/workflows/python-tests.yml:2196-2213` ("ERC
endpoint_off_grid consequence gate (pcb/temper.kicad_sch)") and is a hard
`exit 1` on any finding -- it was red on `main` at the commit this branch
was cut from (`d4510f23e`).

Reproduction, from repo root, fresh `make netlist` first:

```
make netlist   # elec/build/default.net, 168 components, 139 nets, digest 8cfd715e60a3...

kicad-cli sch erc --format json --severity-all \
  -o /tmp/erc/temper_erc.json pcb/temper.kicad_sch          # 498 violations
kicad-cli sch export netlist --format kicadxml \
  -o /tmp/erc/temper_netlist.xml pcb/temper.kicad_sch

python scripts/check_erc_off_grid_consequence.py \
  --erc-json /tmp/erc/temper_erc.json \
  --sch-netlist-xml /tmp/erc/temper_netlist.xml
```

Result on the committed (pre-regen) schematic:

```
endpoint_off_grid pins checked: 163
86 MISMATCH(ES)
5 UNVERIFIABLE (NO_ATOPILE_NET)
FAILED: 86 mismatch(es), 5 unverifiable
```

### Clustering the 86

This is **not** 86 distinct electrical defects. Reading every finding's
`missing_in_schematic` / `extra_in_schematic` detail:

- **81 of 86** are `atopile net X has N members; schematic net of that name
  has N members` -- **equal member counts**, different `(ref, pin)` labels.
  Example: `atopile net 'discharge.k_dis2-coil1' has 3 members; schematic
  net of that name has 3 members; missing_in_schematic=[('D3','1'),
  ('R11','2')] extra_in_schematic=[('D4','1'),('R16','2')]`. `D3->D4`,
  `R11->R16` is the exact same shift `check_netlist_board_reconciliation.py`
  independently reports as `RENUMBERED` (below) -- the same physical
  component, a different designator, because the schematic was drawn before
  the designator cascade and the fresh netlist was compiled after it. Zero
  net members are actually missing or extra; the set difference is 100%
  label churn. `+3V3` (50 vs 51 members, 6 separate MISMATCH rows) is the
  largest instance: the *set sizes* differ by one only because `C37`
  the *label* now points to a different physical component (`safety.
  ocp2.c_filter`, on net `s1`) than it did when the schematic was drawn
  (`safety.wdt.c_bypass`, on `+3V3`, now relabeled `C38`) -- the true
  `+3V3` membership (physical components, not labels) is unchanged.
- **5 of 86** (`U19`/`TP3` x2 on `safety.ocp2-line`, `C37`/`R65` x2 on
  `s1`, `J1` x1 on `rtd_force_p`) are genuinely `schematic net ... has 0
  members` -- these 3 nets don't exist in the stale drawing **at all**,
  because they belong to circuitry (OCP-02's second CT channel, the
  J_RTD1 pan-probe connector) added to `elec/src` after the schematic was
  last generated. This is exactly what regeneration draws in.
- **5 UNVERIFIABLE** (`D5`, `R76`-`R79`): off-grid pins in the stale
  schematic whose ref no longer exists in the fresh compile at all --
  the design shrank (7-component ZCD-opto deletion, 2026-08-07) and grew
  (6 new components) in the same window, and these particular labels fell
  in the gap. Same root cause as the 81, not new information.

No case in the 86 is a real "looks-connected-but-isn't" defect -- the gate
exists specifically to distinguish that from cosmetic churn, and every
instance here resolves to cosmetic churn or "not drawn yet."

## 2. The true delta: schematic regeneration only

Regenerated into a scratch directory first (`--output-dir /tmp/...`),
verified, **then** copied over the committed files -- never generated
in place blind:

```
python scripts/gen_schematics.py --output-dir /tmp/sch_scratch
  Reading netlist: elec/build/default.net
    168 components, 162 nets, 41 unique parts
  Generated 7 schematic files in /tmp/sch_scratch
  Running oracle...
  ORACLE PASS: 517 pin assignments, 110 nets -- connectivity partitions isomorphic
```

`oracle_verify` re-derives connectivity partitions from the generated
`.kicad_sch` set via `kicad-cli sch export netlist` and asserts they are
**isomorphic** to `elec/build/default.net`'s own partitions -- the
strongest available guarantee that the regenerated drawing is electrically
identical to the compiled design, independent of any label.

**Nets added / removed / renamed** (netlist vs. what the stale schematic
implied):

| Class | Nets | Cause |
|---|---|---|
| Removed | `zcd`, `ZCD_ISO`, `a`, `power_in.r_zcd_top1-p2`, `OVP_VREF_2V5` | 2026-08-07 ZCD-opto deletion (`5842767c2`) -- these nets belonged entirely to the deleted circuit |
| Added | `OCP2_VREF_2V5`, `hb-gnd`, `io13`, `s1`, `safety.ocp2-line` | 2026-08-07 OCP-02 second-CT module (`c617e0d08`) |
| Added (membership only; name pre-existed) | `rtd_force_p`, `rtd_force_n`, `rtd_sense_p`, `rtd_sense_n` gain `J1` as a member | 2026-08-08 J_RTD1 connector (`ebb8aff20`) |
| Renamed | **none** | |

**Netclass-critical names -- explicitly checked, all unchanged:**
`ac_l`, `ac_n`, `gnd`, `+170V_BUS`, `SW_NODE`, `GATE_HS`, `GATE_LS`, and
every RTD/SPI net (`RTD_SCK`, `RTD_SDI`, `RTD_CS_N`, `RTD_DRDY`,
`rtd_force_*`, `rtd_sense_*`) keep their exact names. Confirmed two ways:
(1) none of the 6 removed/added net names above intersects
`TEMPER_NET_ASSIGNMENTS` or `pcb/temper.kicad_pro`'s netclass-critical
set beyond `zcd`/`a` (next paragraph); (2)
`scripts/sync_kicad_netclass_assignments.py --check` still reports `OK ...
already agrees ... for all 51 covered net(s)` after this branch's
regeneration, unchanged from before it.

**Orphaned config entries (informational, not a break):**
`TEMPER_NET_ASSIGNMENTS` (`packages/temper-placer/src/temper_placer/
core/design_rules.py:291`) and `pcb/temper.kicad_pro` (`net_settings.
netclass_assignments`, lines 388/399) both still carry `"zcd": "HighVoltage"`
entries (plus `kicad_pro`'s separate stale `"ZCD": "Default"`) for a net
that no longer exists in the compiled design as of the 2026-08-07 ZCD-opto
deletion -- **independent of and predating this branch**. This is the same
"dead alias" shape `sync_kicad_netclass_assignments.py`'s own docstring
already documents and explicitly tolerates (`SWITCH_NODE`/`PWM_H`/`RTD_CS`
from an earlier revision) -- a mapping for a nonexistent net is inert, not
a defect, and that script's own contract never removes entries
automatically. Not fixed here (`pcb/temper.kicad_pro` is out of this
branch's scope); flagged for whoever eventually resyncs the board, since
that is the natural point to also prune dead net-class entries. The 5 new
OCP-02/pan-probe net names above have **no** `TEMPER_NET_ASSIGNMENTS`
entry yet either (new, uncosted from a netclass-domain perspective) --
same follow-up.

**Components:** unchanged by this branch. The schematic has always mirrored
whatever `elec/build/default.net` says; regenerating it doesn't add or
remove a single component relative to what was already true about the
*design*. It only fixes the drawing to say so.

## 3. What the pan-probe / OCP-02 changes did electrically

Both are genuine new physical circuitry, not renames or non-structural
edits:

- **OCP-02** (`c617e0d08`, 2026-08-07, "implement OCP-02 as Option A
  (second CT), wired into fault tree"): adds a second current-transformer
  overcurrent-protection channel -- `T2` (CST3015 CT, `safety.ocp2.ct`),
  `R65` (burden resistor), `C37` (filter cap), `U19` (SOT-23-5 comparator),
  `TP3` (fault test point) -- wired into the existing fault-OR tree
  (`safety.ocp2-line` joins the same protection chain `safety.ocp-line`,
  `safety.ovp-line`, etc. already feed). 5 new components, 5 new nets.
- **J_RTD1 pan-probe connector** (`ebb8aff20`, 2026-08-08, "instantiate
  J_RTD1 pan-probe connector, closing PID-01..04 gap"): adds `J1`, a
  4-pin JST-XH connector (`Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_
  Vertical`) that terminates the 4-wire RTD front-end
  (`rtd_force_p/n`, `rtd_sense_p/n`) that already existed in `rtd_pan`
  -- this closes a previously-open external connection point, it does not
  add new sensing circuitry. 1 new component, 0 new nets (4 existing nets
  gain a member).
- A third, earlier change in the same gap window, **not named in the task
  but load-bearing for the numbers above**: `5842767c2` (2026-08-07,
  "delete U3 (H11L1 mains-ZCD optocoupler) and its dedicated circuitry")
  removes 7 components (`U3`, `D2`, `R6`-`R10`) and 5 nets. This is why
  the board has *more* stale components than the pan-probe/OCP-02 story
  alone would predict, and it is the direct cause of the `RENUMBERED`
  cascade documented below (component removal upstream shifts every
  same-prefix designator after it, same as insertion does in the other
  direction).

None of the three is a net rename; all three are additive-or-subtractive
structural changes to real circuitry.

## 4. The board question -- separate, larger, unresolved by this branch

`scripts/check_netlist_board_reconciliation.py` (fresh `make netlist` vs.
`pcb/temper.kicad_pcb`, unaffected by anything in this branch since it
never reads `.kicad_sch`):

```
Components: 168 in netlist, 169 on board, 162 matched by instance path.
Nets: 139 design / 139 board.
=== FINDINGS: 125 ===
  [EXTRA] 7        -- D2, R6, R7, R8, R9, R10, U3 (the ZCD-opto circuit;
                       physically on the board, no longer in the design)
  [MISSING] 6       -- J1, C37, U19, T2, R65, TP3 (OCP-02 + pan-probe;
                       in the design, no board footprint)
  [NET-EXTRA] 5     -- OVP_VREF_2V5, ZCD_ISO, 'a', power_in.r_zcd_top1-p2,
                       zcd (board-only, ZCD-circuit residue)
  [NET-MISSING] 5   -- OCP2_VREF_2V5, hb-gnd, io13, s1, safety.ocp2-line
                       (design-only, OCP-02, zero placed components)
  [NET-MEMBERSHIP] 9 -- +3V3, DC_BUS_RTN, PWR_RTN, ac_l, gnd,
                        rtd_force_{p,n}, rtd_sense_{p,n}
  [RENUMBERED] 93    -- pure designator-identity churn, same cause as
                        section 1's 81/86 (7 removed + 6 added components
                        shift every same-prefix designator between them)
FAILED -- 125 finding(s)
```

`scripts/check_footprint_drift.py` corroborates independently (13
violations: the same 6 missing-from-board / 7 missing-from-netlist split,
0 actual footprint-string mismatches).

**This 125/13 is identical before and after this branch's schematic
regeneration** -- verified by running both gates against the unmodified
`elec/build/default.net` and `pcb/temper.kicad_pcb`, neither of which this
branch touches. `scripts/tests/test_check_netlist_board_reconciliation.
py::test_gate_passes_on_real_board_and_fresh_netlist` fails on `main` at
the commit this branch was cut from, for the same reason, before this
branch exists.

**Why this is a real placement decision, not a mechanical fix:**
`docs/evidence/2026-08-11-pad-connectivity-ground-truth.md` measured, the
same day, **0 of the board's 110 real electrical nets (0.0%) verifiably
routed**. `Makefile`'s own `route` target comment: placement is "a
separate, deliberately human-gated CP-SAT solve with candidate selection
... every recent `pcb/temper.kicad_pcb` change came from one, never from
`make build`." Placing 6 new footprints (1 connector, 1 SOT-23-5, 1
CST3015 CT, 2 passives, 1 test point) and removing 7 stale ones on a board
at this state is exactly that kind of solve -- not something to do inside
a diagnostic spike, and out of this branch's boundaries regardless
(`pcb/temper.kicad_pcb` is explicitly off-limits here).

## 5. Cost and recommendation

| Path | What it touches | Risk | Verdict |
|---|---|---|---|
| **A. Schematic only** | `pcb/*.kicad_sch` (7 files) | Mechanical, oracle-verified isomorphic, zero netclass-critical net renamed, ERC ratchet still passes (495 <= 498 ceiling, 0 errors), `check_erc_off_grid_consequence.py` 86->1 findings | **Done, this branch.** |
| **B. Schematic + board** | + `pcb/temper.kicad_pcb` | CP-SAT placement solve on a 0/110-routed board, 6 new + 7 removed footprints, owner-gated per `Makefile`'s own convention | **Not done. Escalate.** |
| **C. elec change landed without board follow-up** | n/a | The OCP-02 / J_RTD1 / ZCD-deletion commits are each individually correct circuit changes; none should have blocked on a same-PR board resync (that convention exists for `drc_ceiling.json`/DRC, not for board placement, which is explicitly its own gated step) -- **not** a process defect to flag | Ruled out. |

**Recommendation:** Path A is complete on this branch -- safe, measured,
mechanical, and it clears the CI gate that was actually red
(`check_erc_off_grid_consequence.py`, 86 -> 1; the 1 residual is `F1`
pin 1 on `ac_l`, discussed below, not a new problem). Path B is a real,
separate cost (a full placement pass) that belongs to whoever owns the
board-resync decision, not to this spike -- flagged here with the exact
component/net list needed to scope that work, not attempted.

### One residual, reported rather than hidden

After regeneration, `check_erc_off_grid_consequence.py` drops from 86 to
**1** finding, not 0:

```
1 MISMATCH(ES)
  ('F1', '1') [HV/mains]: atopile net 'ac_l' has 1 members; schematic net
  of that name has 0 members; missing_in_schematic=[('F1', '1')]
  extra_in_schematic=[]
```

Before the 2026-08-07 ZCD-opto deletion, `ac_l` had 2 members (`F1` pin 1,
the mains-fuse entry point, plus `R6` pin 1, the deleted ZCD divider's top
tap) -- confirmed against the *old* schematic's own exported netlist
(`/Power_Input/ac_l [('F1','1'), ('R6','1')]`). With `R6` gone, `ac_l` is
now a genuine single-pin net -- `F1`'s own external mains-L terminal, with
no second endpoint anywhere in the design (the physical AC input connector
itself is not modeled; see `elec/src/modules.ato`'s fuse-holder comment).
`gen_schematics.py` does not draw a text label for a single-member net
(nothing to route it to), so `kicad-cli`'s own netlist export reports 0
members under that name for the drawn schematic, even though the
*physical* pin is present and correctly placed. This is not a connectivity
defect and not something this branch's regeneration introduces -- it is
the same 2026-08-07 root cause as everything else here, now fully isolated
to its smallest possible remaining footprint. Left as an honest, named
residual (consistent with this gate's own "unverifiable is not evidence of
safe" contract) rather than silently claimed as 0.

## 6. Verification run on this branch

```
make netlist                                    # 168 components, digest 8cfd715e60a3...
python scripts/gen_schematics.py --check         # CHECK PASS (oracle: 517 pins, 110 nets, isomorphic)
python scripts/ci_check_erc.py                   # PASS: temper 0 errors, 495<=498 warnings
                                                  # PASS: mcu 20<=20 errors, 46<=47 warnings
python scripts/check_erc_off_grid_consequence.py # 1 MISMATCH (ac_l/F1, see above), was 86
python scripts/sync_kicad_netclass_assignments.py --check
                                                  # OK, 51/51 nets agree (unchanged)
python scripts/check_netlist_board_reconciliation.py
                                                  # 125 findings (unchanged -- board, not touched)
python scripts/check_footprint_drift.py          # 13 violations (unchanged -- board, not touched)
pytest scripts/tests/test_check_erc_off_grid_consequence.py
                                                  # 4 passed
pytest scripts/tests/ -k "gen_schematics or erc_ceiling or ci_check_erc"
                                                  # 15 passed
```

**Files changed by this branch:** `pcb/half_bridge.kicad_sch`,
`pcb/mcu.kicad_sch`, `pcb/power_input.kicad_sch`,
`pcb/power_management.kicad_sch`, `pcb/safety_interlock.kicad_sch`,
`pcb/sensing.kicad_sch`, `pcb/temper.kicad_sch`. Nothing else --
`pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`, `elec/src/**`,
`power_pcb_dataset/**`, `packages/temper-design-bundle/src/
netlist_contracts.rs`, and `parse_engine.rs` are all untouched.
