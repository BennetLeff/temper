# PCB Netlist Resync — `pcb/temper.kicad_pcb` reconciled against the current netlist

<!-- provenance: commit=3c9bb1dee4803b90be6958ce30328451d1c73574 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** `pcb/temper.kicad_pcb`, `pcb/fp-lib-table`, `tools/setup_kicad_env.py`,
`.gitignore`, new `scripts/resync_pcb_netlist.py`.
**Trigger:** `docs/hardware/SELV_ISOLATION_REDESIGN.md` and the "Correction: the
committed board is UNROUTED" / "The board has 18 real clearance violations"
sections of `docs/STRATEGY.md` — the committed board still carried
`+340V_BUS`, had no `gnd`/`ZCD_ISO`/`pe` net, and the safety validators had to
join positions to voltage domains by reference designator instead of by net.

---

## 1. Falsifier, stated before implementing

**Falsifier:** *The resync is wrong if any component's position moved, or if
any designator now refers to a different part than it did before (checked by
sheetpath identity, not by trusting the label).*

**Result: the falsifier did NOT fire, for the resync process itself.**
Zero of the 148 pre-existing components that persist in the current netlist
changed position/orientation/layer (§4). Every designator that now refers to
a different part is enumerated explicitly, not silently reassigned (§5) —
77 of 148 persisting components did get a new reference-designator label
(because the resync keys identity on the atopile module-instance
`Sheetpath`, not on the number, exactly per
`docs/solutions/logic-errors/fixed-positions-ref-fragility-across-renumbering.md`),
but every one of those relabelings is accounted for below, and none of them
represents a component moving to serve a different circuit role — the role
(sheetpath) is what defines "the same component," and it never changed
mid-flight.

A second, related falsifier surfaced mid-task and is reported honestly
rather than hidden: **naive reference-designator joining — the mechanism the
safety-validator test fixture already uses to bridge the stale board to the
current netlist — silently pairs the wrong physical component for 77 of 149
shared designators.** This is not a defect in this resync; it is the exact
defect this resync exists to close, and it is why the post-resync clearance
count (§7) differs from both the previously-documented figure and this
session's own pre-resync measurement.

---

## 2. Mechanism used, and why

**Survey performed first**, per instruction. `scripts/gen_pcb_skeleton.py`
already builds a from-scratch `.kicad_pcb` from the atopile netlist
(`elec/build/default.net`): it parses the netlist, resolves footprints via
`pcb/fp-lib-table`, assigns pad nets (exact pad-number match, falling back to
positional pad-order matching for parts like relays whose pad numbers don't
match netlist pin numbers), and — critically — writes a `Sheetpath` property
onto every footprint (the atopile module-instance path, e.g.
`hb.power_loop.q_high`), which is the project's own answer to "how do you
identify a component across a designator renumbering"
(`docs/solutions/logic-errors/fixed-positions-ref-fragility-across-renumbering.md`).
The committed board already had this property on all 149 footprints —
confirming it actually was produced by this tool at some point and then
hand/optimizer-placed.

`gen_pcb_skeleton.py`'s own placement, however, is a fresh flow layout (rows
sized off courtyard geometry) — using it directly would satisfy "resync the
nets" but violate "do not move components." KiCad's own answer to this exact
problem is "Update PCB from Schematic": match existing footprints to the new
netlist by stable identity, keep positions for matches, drop footprints that
no longer exist, and stage genuinely new components separately rather than
inventing a placement for them. `scripts/resync_pcb_netlist.py` (new,
~280 lines) is that operation for this project: it **imports**
`gen_pcb_skeleton.parse_netlist` and `resolve_footprint` rather than
reimplementing the S-expression parser or footprint resolution, and adds only
the reconciliation logic:

1. Parse the current netlist and the committed board.
2. Match old and new footprints by `Sheetpath` (not by reference designator).
3. For every match: **deep-copy the old footprint verbatim** (preserving
   position, orientation, layer, locked state, and — for footprints whose
   KiCad footprint identifier is unchanged — all embedded pad/graphic
   geometry), then only overwrite `Reference`/`Value`/`Footprint` properties
   and re-run pad-net assignment against the current netlist.
4. Footprints with no `Sheetpath` match in the old board are genuinely new
   components — resolved via `pcb/fp-lib-table` and appended in a staging
   row well below the existing `Edge.Cuts` outline (y ≥ old max-Y + 20 mm),
   never placed into the routed layout.
5. Old footprints with no match in the new netlist are dropped, and reported.
6. The board-level net table is rebuilt from the current netlist (sorted by
   name, matching `gen_pcb_skeleton.py`'s own convention); `board.layers`,
   `Edge.Cuts`, `setup`, and all zones/tracks/vias are left untouched.

Reusing the project's own parser/resolver, plus the project's own
already-established `Sheetpath` identity mechanism, was preferred over a
bespoke rewrite per the task instruction; the only new code is the
match/keep/add/remove/reassign-nets loop itself.

**A real gap found and fixed along the way:** `resolve_footprint()` failed on
the new H11L1 optocoupler (`Package_DIP:DIP-6_W7.62mm`) because
`Package_DIP` was never in `pcb/fp-lib-table` or
`tools/setup_kicad_env.py`'s `REQUIRED_LIBS` — H11L1 is the design's first
DIP-6 part (also independently noted in
`docs/hardware/SELV_ISOLATION_REDESIGN.md` §7). Fixed by running
`tools/setup_kicad_env.py` (network sparse-clone of the official
kicad-footprints repo, already the project's own mechanism for this),
extending its sparse-checkout to include `Package_DIP.pretty`, and adding the
corresponding `fp-lib-table` entry and `REQUIRED_LIBS` entry so future runs
fetch it too. `pcb/libs/kicad-footprints/` is itself a nested `.git` sparse
checkout and was **not** committed — it is gitignored (new `.gitignore`
entry), matching the precedent in `11f859e5` ("untrack 73 phantom gitlinks,
close the submodule-foreach hole").

---

## 3. Net-name evidence (measured directly on the committed file)

```
$ grep -c '+340V_BUS' pcb/temper.kicad_pcb
0
$ grep -c '+170V_BUS' pcb/temper.kicad_pcb
12
$ grep -n '(net [0-9]* "gnd")' pcb/temper.kicad_pcb
85:  (net 49 "gnd")
$ grep -c '(net 49 "gnd"))' pcb/temper.kicad_pcb     # per-pad assignments
80
$ grep -n '(net [0-9]* "ZCD_ISO")' pcb/temper.kicad_pcb
61:  (net 25 "ZCD_ISO")
$ grep -c '(net [0-9]* "pe")' pcb/temper.kicad_pcb
0
```

`+340V_BUS` is gone; `+170V_BUS` and `gnd` (80 pins — matches
`SELV_ISOLATION_REDESIGN.md` §6's netlist-level count exactly) and
`ZCD_ISO` (3 pins — `U23`/MCU, `U3`/opto Vo, `R10`/pull-up, matching
that document's §4 row 2 evidence) are present. `pe` does **not** appear as
its own net record — this is correct, not a gap: `main.ato` connects
`gnd ~ pe` with a plain tie (no `override_net_name` on `pe`), so the two
signals compile to a single electrical net, and atopile names it `gnd`
(confirmed directly in `elec/build/default.net`, and independently already
documented as the expected behavior by the `_real_board_fixture.py` module
docstring, which the resync did not touch).

Board contents otherwise unchanged (unrouted, as expected — resyncing nets
is not routing):

```
$ grep -c '(segment ' pcb/temper.kicad_pcb   ->  0
$ grep -c '(via ' pcb/temper.kicad_pcb       ->  0
$ grep -c '(zone ' pcb/temper.kicad_pcb      ->  0
```

---

## 4. Zero-components-moved proof

Independent check (not the resync script's own self-report): both the
pre-resync board (backed up before any write) and the post-resync committed
board were parsed directly with `kiutils`, footprints matched by
`Sheetpath`, and `(X, Y, angle, layer, locked)` compared per match.

```
148 pre-existing components checked (Sheetpath present in both files)
moved: 0
```

148, not 149, because one old component
(`safety.ovp.r_adc_top`, old ref `R55`) has no match in the current netlist
— it was split into three creepage-distributed resistors
(`safety.ovp.r_adc_top1/2/3`, §5), which is a real topology change, not a
component that silently vanished. Cross-checked a second, independent way:
running `scripts/resync_pcb_netlist.py --dry-run` against the now-committed
board reports `moved_count: 0`, and re-running it (idempotency check) reports
`kept_count: 169, added_count: 0, removed_count: 0` — the committed board is
now a fixed point of the resync operation.

---

## 5. Footprint count: 149 → 169, fully accounted for

```
old board footprints:  149
new board footprints:  169
netlist components:    169
kept (Sheetpath in both):        148
removed (Sheetpath only in old): 1
added (Sheetpath only in new):   21
```

149 − 1 + 21 = 169. The fuse holder (`F1`, `power_in.fuse`) was
**already present** in the committed board and is in the "kept" set,
unchanged — today's BOM fix (`6d8fad62`) corrected its part number, not its
schematic presence, so it does not appear as an addition here. Likewise the
"obsolete decoupling cap" and "the fictional X2" fixes changed MPNs, not
footprint identifiers (`footprint_swapped_count: 0` — every kept component's
KiCad footprint string is unchanged), so those show up as ordinary "kept"
entries, not additions.

**1 removed:**

| Sheetpath | Old ref | Reason |
|---|---|---|
| `safety.ovp.r_adc_top` | R55 | Split into three series resistors for creepage (below), per the same pattern as the main OVP divider's `r_div_top1/2/3`. |

**21 added** (all real, all traceable to today's electrical work):

| Sheetpath | New ref | Footprint | Belongs to |
|---|---|---|---|
| `power_in.r_zcd_opto` | R9 | R_0603 | ZCD opto LED-drive resistor |
| `power_in.r_zcd_pullup` | R10 | R_0603 | ZCD opto output pull-up |
| `power_in.zcd_opto` | U3 | Package_DIP DIP-6 | **H11L1 optocoupler** (new isolator, ZCD crossing fix) |
| `safety.ovp.r_hyst` | R57 | R_0603 | OVP hysteresis resistor |
| `safety.ovp.r_adc_top1/2/3` | R58, R59, R60 | R_1206 ×3 | Split ADC-sense divider (replaces removed R55) |
| `safety.coil_thermal.ntc` | R67 | R_Axial THT | **THM-02** coil-NTC |
| `safety.coil_thermal.r_ntc_fixed` | R68 | R_0603 | THM-02 divider |
| `safety.coil_thermal.r_ref_top` | R69 | R_0603 | THM-02 divider |
| `safety.coil_thermal.r_ref_bot` | R70 | R_0603 | THM-02 divider |
| `safety.coil_thermal.r_hyst` | R71 | R_0603 | THM-02 hysteresis |
| `safety.coil_thermal.comp` | U19 | SOT-23-5 | **THM-02** comparator |
| `safety.uvlo_logic.r_div_top` | R72 | R_0603 | **UVL-02** divider |
| `safety.uvlo_logic.r_div_bot` | R73 | R_0603 | UVL-02 divider |
| `safety.uvlo_logic.r_hyst` | R74 | R_0603 | UVL-02 hysteresis |
| `safety.uvlo_logic.r_outa_pullup` | R75 | R_0603 | UVL-02 pull-up |
| `safety.uvlo_logic.r_fault_pullup` | R76 | R_0603 | UVL-02 pull-up |
| `safety.uvlo_logic.mon` | U21 | SOT-23-6 | **UVL-02** TPS3700 monitor |
| `safety.uvlo_logic.inv` | U22 | SOT-23-5 | UVL-02 SN74LVC1G38 inverter |
| `safety.tp_uvlo2_fault` | TP3 | TestPoint | UVL-02 test point (deliberately not in the fault-OR tree, per `SELV_ISOLATION_REDESIGN.md` §4 row 13) |

Every added sheetpath maps to a module named in the task brief (THM-02,
UVL-02, the H11L1 opto, the split OVP-ADC divider). No unexplained addition.
All 21 were staged in a row starting at y = board-max-Y + 20 mm (below
`Edge.Cuts`), not placed into the existing layout.

---

## 6. Every designator whose meaning changed

77 of the 148 persisting components (52%) received a new reference
designator, because inserting new parts earlier in `elec/src`'s object walk
shifts every later designator of the same prefix
(`docs/solutions/logic-errors/fixed-positions-ref-fragility-across-renumbering.md`
describes exactly this mechanism). Full table (`old → new`, keyed by the
stable `Sheetpath`, so this is a verified 1:1 identity mapping, not a
guess):

```
R31 -> R33   ct_sense.r_bias_bot            R30 -> R32   ct_sense.r_bias_top
R29 -> R31   ct_sense.r_burden              R13 -> R15   discharge.r_coil1
R14 -> R16   discharge.r_coil2               R9 -> R11   discharge.r_dis1a
R10 -> R12   discharge.r_dis1b              R11 -> R13   discharge.r_dis2a
R12 -> R14   discharge.r_dis2b              R15 -> R17   discharge.r_gate
R16 -> R18   discharge.r_gate_pd            R17 -> R19   discharge.r_snub1
R18 -> R20   discharge.r_snub2              R27 -> R29   hb.dt_res
 U7 -> U8    hb.gate_hs.boot_diode           U6 -> U7    hb.gate_hs.driver
R23 -> R25   hb.gate_hs.r_filt_a            R24 -> R26   hb.gate_hs.r_filt_b
R21 -> R23   hb.gate_hs.rg_on               R22 -> R24   hb.gate_hs.rgs
R25 -> R27   hb.gate_ls.rg_on               R26 -> R28   hb.gate_ls.rgs
 U4 -> U5    hb.power_loop.q_high            U5 -> U6    hb.power_loop.q_low
U22 -> U26   mcu.mcu                        R63 -> R78   mcu.r_boot
R62 -> R77   mcu.r_en                       R65 -> R80   mcu.r_scl_pullup
R64 -> R79   mcu.r_sda_pullup                U3 -> U4    power_mgmt.buck_3v3.buck
R20 -> R22   power_mgmt.buck_3v3.r_fb_bot   R19 -> R21   power_mgmt.buck_3v3.r_fb_top
 U8 -> U9    rtd_pan.adc                    U14 -> U15   rtd_pan.fault_nand
R37 -> R39   rtd_pan.fb_power               U11 -> U12   rtd_pan.high_window
U10 -> U11   rtd_pan.low_window             R44 -> R46   rtd_pan.r_avdd_bottom
R43 -> R45   rtd_pan.r_avdd_top             R35 -> R37   rtd_pan.r_cs
R46 -> R48   rtd_pan.r_fault_pullup         R41 -> R43   rtd_pan.r_high_bottom
R40 -> R42   rtd_pan.r_high_top             R39 -> R41   rtd_pan.r_low_bottom
R38 -> R40   rtd_pan.r_low_top              R36 -> R38   rtd_pan.r_miso
R34 -> R36   rtd_pan.r_mosi                 R45 -> R47   rtd_pan.r_rail_ok_pullup
R32 -> R34   rtd_pan.r_ref                  R33 -> R35   rtd_pan.r_sclk
R42 -> R44   rtd_pan.r_window_ok_pulldown   U13 -> U14   rtd_pan.rail_monitor
 U9 -> U10   rtd_pan.reference              U12 -> U13   rtd_pan.window_and
U20 -> U24   safety.fault_any_or            U19 -> U23   safety.fault_or
U21 -> U25   safety.latch                   U15 -> U16   safety.ocp.comp
R48 -> R50   safety.ocp.r_ref_bot           R47 -> R49   safety.ocp.r_ref_top
U16 -> U17   safety.ovp.comp                R56 -> R61   safety.ovp.r_adc_bot
R52 -> R54   safety.ovp.r_div_bot           R49 -> R51   safety.ovp.r_div_top1
R50 -> R52   safety.ovp.r_div_top2          R51 -> R53   safety.ovp.r_div_top3
R54 -> R56   safety.ovp.r_ref_bot           R53 -> R55   safety.ovp.r_ref_top
U17 -> U18   safety.thermal.comp            R57 -> R62   safety.thermal.ntc
R61 -> R66   safety.thermal.r_hyst          R58 -> R63   safety.thermal.r_ntc_fixed
R60 -> R65   safety.thermal.r_ref_bot       R59 -> R64   safety.thermal.r_ref_top
U18 -> U20   safety.wdt.wdt                 R28 -> R30   tank.inductor_conn
R66 -> R81   thermal.r_fan_drop
```

**Why this table exists, and why it is the load-bearing part of this
deliverable:** cross-checking the *reverse* direction — for every reference
designator string that exists in both the old board and the current
netlist, does it mean the same component? — finds **78 of 149 shared
designators now point at a physically different component** if you join
naively by label (e.g., old board's `U3` = the buck-converter IC
`power_mgmt.buck_3v3.buck`; the current netlist's `U3` = the new H11L1
optocoupler `power_in.zcd_opto` — completely different parts, same label).
This is exactly the "silently reassigned designator on a mains board" defect
class the task warned about, and it is precisely why `_real_board_fixture.py`
(the safety-validator test fixture) joining the stale board to the current
netlist **by reference designator** was already a live risk before this
resync, not just a theoretical one — see §7.

---

## 7. Safety validators re-run — the count is 22, not 18, and here is why

Ran directly (`verify_iec60335_compliance` from
`packages/temper-placer/tests/requirements/validators/clearance.py`, via
`packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`),
not just via the pytest xfail wrapper (which only asserts non-zero
violations, not a specific count, so a passing/xfailing test run alone does
not prove the count is unchanged — checked and rejected as insufficient
evidence).

| | Board | `matched_components_in_placement` | `error_count` |
|---|---|---|---|
| Pre-resync (measured directly, this session, same netlist) | stale (149 fp) | 109 / 126 classifiable | **16** |
| Post-resync | resynced (169 fp) | **126 / 126** classifiable | **22** |

`classified_nets_present` is byte-identical in both runs (`+15V, +170V_BUS,
+3V3, DC_BUS_RTN, PWR_RTN, ZCD_ISO, ac_l, ac_n, gnd, zcd`) — **domain
classification did not change.** What changed is the reference-designator
join between position and classification, which was broken for 77–78 of the
persisting components (§6) and is now exact (0 mismatches, checked directly)
— 126/126 classifiable netlist components now find their real placed
position, up from 109/126 before.

**Neither number is the previously-documented "18"** (`docs/STRATEGY.md`,
`docs/evidence/2026-07-26-safety-validators-implemented.md`). Measuring the
untouched, still-stale committed board against *this session's* freshly
built netlist (`make netlist`, 76/76 assertions passed, exit 0) gives **16**,
not 18, before any resync activity. This is not a resync artifact — it is
measured against a file this task had not yet touched — and is most likely
explained by further upstream drift on `docs/methodology-loop-discipline`
between when "18" was recorded and this session's tip (the SELV redesign doc
itself documents being re-derived across at least one such rebase already).
**Flagged as UNVERIFIED regarding the exact prior commit that changed it**;
not investigated further here as out of this task's scope, but the discrepancy
is reported rather than papered over, per the standing instruction to prefer
a real, checked number over a comfortable one.

**Worked examples distinguishing "relabeled" from "newly detectable" among
the pair-level diff** (full before/after violation lists captured in
`/tmp` logs during this session; a regex-based pair/kind/required-mm/boundary
extraction was used for this comparison, not a hand recount of all 22):

- **`F1`↔`J1` (mains fuse ↔ fan connector), all four rows, unchanged
  in both runs.** `F1` and `J1` are both in the "kept, ref unchanged" set —
  proof the resync did not disturb an already-correct measurement.
- **`U18`↔`U5` (before) is the same physical pair as `U20`↔`U6` (after).**
  `U5`(before)=`hb.power_loop.q_low`→now `U6`; `U18`(before)=`safety.wdt.wdt`→now
  `U20`. Both clearance and creepage rows carry over unchanged — a pure
  relabeling, not a new finding.
- **`R43`↔`R58` / `R44`↔`R58` (before) do not reappear in any form after
  resync.** Tracing through Sheetpath: pre-resync board label `R58` was
  physically `safety.thermal.r_ntc_fixed` (now correctly labeled `R63`);
  pre-resync labels `R43`/`R44` were physically `rtd_pan.r_avdd_top`/
  `_bottom` (now `R45`/`R46`). Under their correct current identity, this
  physical trio does not violate — **the pre-resync "16" contained at least
  one false positive**, produced by binding the *current netlist's*
  domain-classification for label `R58` (which today means
  `safety.ovp.r_adc_top1`, a brand-new component) to the *old board's*
  physical position of a different, unrelated part that happened to carry
  the same label.
- **`R50`↔`R51`, `R51`↔`R77`, `R51`↔`R78` (after) involve components that
  did not exist in the old board at all** (`R77`/`R78` are the renamed
  `mcu.r_en`/`mcu.r_boot`, and `R51` post-resync is
  `safety.ovp.r_div_top1`) — these could not have been found before the
  identity was correct, by construction, not because a rule changed.

**Net effect, stated plainly:** the resync did not change what "MAINS",
"DC_BUS", or "LV_CONTROL" mean, and it did not move a single component. It
corrected which physical component sits under which label, which is exactly
what makes 22 — not 16, and not the previously-documented 18 — the first
trustworthy real-board clearance count. The board still has real,
uncorrected IEC 60335 clearance/creepage violations either way; this resync
changes the count's trustworthiness, not the underlying hardware.

`pytest packages/temper-placer/tests/requirements/safety/test_clearance.py`:
**22 passed, 1 xfailed**, identically before and after (the xfail only
asserts non-zero violations, so this alone does not distinguish 16 from 22 —
recorded for completeness, not as the count proof; §7's direct measurement
above is the count proof).

---

## 8. Commands run (foreground, for reproducibility)

```
scripts/assert-base.sh docs/methodology-loop-discipline   # OK after rebase
make netlist                                              # exit 0, 76/76 PASSED
python3 tools/setup_kicad_env.py                           # + Package_DIP added
uv run --package temper-placer python3 scripts/resync_pcb_netlist.py --dry-run
uv run --package temper-placer python3 scripts/resync_pcb_netlist.py
uv run --package temper-placer python3 -m pytest packages/temper-placer/tests/requirements/safety/test_clearance.py -q
```

## 9. What this does not claim

- Routing, clearance remediation, and the OVP-01 fail-open tuning issue are
  untouched — this is a nets/designators/footprints resync only, per scope.
- The 21 newly staged components are in a holding row, not a real placement;
  whoever places them next should key any `fixed_positions`-style config
  entries by `Sheetpath`, not by these reference designators, per
  `docs/solutions/logic-errors/fixed-positions-ref-fragility-across-renumbering.md`.
- The discrepancy between this session's directly-measured pre-resync count
  (16) and the previously-documented figure (18) is reported, not resolved;
  it predates this task's changes.
