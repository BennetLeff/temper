<!-- provenance: commit=99d0a61aa9b6e72d7fb29b00080262797dfe8726 dirty=false (base commit this PR branches from; this doc's own reconciliation is the PR's diff on top of it) -->

# Reconciling the 31 broken `net_classes` keys (Gate 3)

**Branch:** `fix/netclass-config-keys`
**Gate:** `scripts/check_netclass_map_board_correspondence.py` (#1030, landed advisory)
**Companion defect:** `packages/temper-design-bundle/src/net_class_validation.rs` /
`packages/temper-placer/tests/core/test_apply_net_class_mapping_strict.py`
(a sibling task closing the fail-open `"Unknown"` 0.2mm default in the Rust
DRC bridge). This document is the trigger-removal half: correcting the 31
keys so the fail-open path in the sibling's fix has nothing broken left to
paper over.

## 1. Which board does each config target?

All four files are, or are intended to be, about the same real circuit as
`pcb/temper.kicad_pcb` -- none targets a genuinely different design. But
their fidelity to the *current* compiled netlist varies a lot, and one file
(`gate_driver_constraints.yaml`) targets a different **physical layout**
scope than the other three:

| File | `board:` width x height | Real board (152x234mm) match? | Net-name fidelity before this PR |
|---|---|---|---|
| `configs/temper_production_config.yaml` | 100x150mm | No (stale placement dims; unrelated to net-name correctness -- net names come from the netlist, not board size) | 28/29 correct -- carefully re-synced 2026-07-28 (see its own in-file comments); one straggler missed |
| `packages/temper-placer/configs/temper_constraints.yaml` | 100x150mm | No (same stale-dims issue) | 6/11 correct |
| `configs/temper_deterministic_config.yaml` | 100x150mm | No (same stale-dims issue) | 4/25 correct |
| `packages/temper-placer/configs/gate_driver_constraints.yaml` | 30x30mm | No -- and not meant to: header says "Extracted from temper_constraints.yaml for isolated routing experiment," with its own `nets:` block declaring pin-level connectivity for a 5-component gate-driver subset | 1/5 correct |

None of these mismatched `board:` blocks changes what a *real net name* is
-- net names are a property of the compiled netlist (`elec/build/default.net`
-> `pcb/temper.kicad_pcb`), not of a placement config's declared board
size. So the stale 100x150mm dimensions (already flagged as a related,
separate defect in `docs/evidence/2026-08-11-correspondence-gates.md`'s
Gate 3 section, "a natural follow-on for the same gate's pattern") do not
excuse any of the 31 broken keys -- the gate's finding stands for all four
files. `gate_driver_constraints.yaml`'s components (`U_GATE`, `R_GATE_H`,
`R_GATE_L`, `C_BOOT`) are real board parts too, confirmed via
`packages/temper-placer/configs/temper_constraints.references.yaml`'s
`component_aliases` (`U_GATE: U7 # hb.gate_hs.driver`, etc.) -- it is a
genuine, if orphaned, sub-scope of the real design, not a fictional one.

**Consumer check, done before touching anything:**

- `packages/temper-placer/configs/temper_constraints.yaml` is loaded by
  `load_constraints()` (`cli/__init__.py`, `scripts/run_physics_flow.sh`,
  `scripts/run_clean_flow.sh`, `benchmarks/perf_ab.py`) and its
  `net_classes:` map feeds `constraints_to_design_rules` -> `rules.
  net_class_assignments` (`packages/temper-design-bundle/src/
  config_loader.rs:2202`) -- a real, live consumer.
- `configs/temper_deterministic_config.yaml` is loaded by
  `scripts/run_feedback_loop.py` via the same `constraints_to_design_rules`
  path, and by `scripts/measure_drc_improvement.sh`.
- `configs/temper_production_config.yaml` is, by its own in-file comment,
  "not loaded by any code path today" -- verified: no script, no Rust
  code, and no test references this filename anywhere in the repo outside
  the gate and its test.
- `packages/temper-placer/configs/gate_driver_constraints.yaml` has **zero**
  consumers anywhere in the repo (grep for the filename across `*.py`,
  `*.rs`, `*.sh` turns up only the gate script and its test) -- more
  orphaned than the production config, not less.

## 2. Per-key classification (all 31)

Legend: **rename** (case mismatch or documented stale name, mechanical and
source-confirmed) / **delete** (no real net under any spelling; inventing a
target would be a guess, which the task brief explicitly forbids).

### `packages/temper-placer/configs/temper_constraints.yaml` (5)

| Key | Verdict | Evidence |
|---|---|---|
| `AC_L` | rename -> `ac_l` | case-fold match against the board's own net table |
| `AC_N` | rename -> `ac_n` | case-fold match |
| `GND` | rename -> `gnd` | case-fold match |
| `+340V_BUS` | rename -> `+170V_BUS` | `elec/domain_manifest.yaml`: `"+170V_BUS" # dc_bus_plus. Renamed from "+340V_BUS"` |
| `PE` | **delete** | No PE net exists on the compiled board. `elec/domain_manifest.yaml` documents protective earth as bonded into the SELV `gnd` net through `power_in.y_cap_pe` (a Y1-class EMI/PE bonding capacitor) -- not its own compiled net. Mapping this onto `gnd` would misclassify a SELV ground return as `ACMains`; not invented. |

### `packages/temper-placer/configs/gate_driver_constraints.yaml` (4)

| Key | Verdict | Evidence |
|---|---|---|
| `GATE_H` | rename -> `GATE_HS` | `U_GATE` = `U7` = `hb.gate_hs.driver` (`temper_constraints.references.yaml`); its `OUTA` pin drives the real board net `GATE_HS` |
| `GATE_L` | rename -> `GATE_LS` | Same driver's `OUTB` pin drives `GATE_LS` |
| `CGND` | **delete** | Same net design_rules.py's `TEMPER_NET_ASSIGNMENTS` calls a "dead alias" of `PWR_RTN`. `PWR_RTN`'s own reclassification is explicitly, deliberately reserved elsewhere in this codebase (`scripts/sync_kicad_netclass_assignments.py`'s `PROTECTED_NETS`, `scripts/check_hv_netclass_coverage.py`'s docstring) as an open, larger-blast-radius human decision -- not settled here by picking a mapping. |
| `VCC_BOOT` | **delete** | No net under this name anywhere, including `TEMPER_NET_ASSIGNMENTS` (which keeps several *other* dead aliases around deliberately, e.g. `+5V_ISO`/`VBOOT_H`/`VBOOT_L` -- `VCC_BOOT` isn't even one of those). No established name to rename this to. |

### `configs/temper_production_config.yaml` (1)

| Key | Verdict | Evidence |
|---|---|---|
| `+340V_BUS` | rename -> `+170V_BUS` | Same rename as above; this file's own 2026-07-28 sweep already fixed the sibling `+15V_LS` misclassification with the identical "dead code, fix anyway" rationale in its own comments -- followed here. |

### `configs/temper_deterministic_config.yaml` (21)

| Key | Verdict | Evidence |
|---|---|---|
| `AC_L` | rename -> `ac_l` | case-fold |
| `AC_N` | rename -> `ac_n` | case-fold |
| `GND` | rename -> `gnd` | case-fold |
| `DC_BUS+` | rename -> `+170V_BUS` | `elec/domain_manifest.yaml`: `+170V_BUS` = `dc_bus_plus` |
| `DC_BUS-` | rename -> `DC_BUS_RTN` | `elec/domain_manifest.yaml`: `DC_BUS_RTN` = `dc_bus_minus` |
| `PWM_H` | rename -> `PWM_HS` | `docs/evidence/2026-08-11-netclass-full-sync-inventory.md` sec 2b: confirmed zero-occurrence dead alias, real successor `PWM_HS` |
| `PWM_L` | rename -> `PWM_LS` | same doc, successor `PWM_LS` |
| `GATE_H` | rename -> `GATE_HS` | same reasoning as `gate_driver_constraints.yaml` above |
| `GATE_L` | rename -> `GATE_LS` | same |
| `SHUTDOWN_N` | rename -> `SHUTDOWN` | `elec/src/modules.ato`: "Active-high shutdown output for UCC21550 DIS. This replaces the legacy active-low SHUTDOWN_N net" -- an explicit, in-source succession |
| `USB_D+` | rename -> `usb_dp` | `elec/src/main.ato`: `signal usb_dp # USB D+` |
| `USB_D-` | rename -> `usb_dn` | `elec/src/main.ato`: `signal usb_dn # USB D-` |
| `+5V` | **delete** | No `+5V` net on the board (only `+15V`/`+15V_LS`/`+3V3`/`+170V_BUS`); not even a dead alias in `TEMPER_NET_ASSIGNMENTS`. |
| `VCC_BOOT` | **delete** | Same as `gate_driver_constraints.yaml` above. |
| `PGND` | **delete** | Same `PWR_RTN`-ambiguity reasoning as `CGND` below -- and having both `PGND` and `CGND` resolve to the same net would also collide as a duplicate YAML key. Not settled here. |
| `CGND` | **delete** | Same `PWR_RTN` reasoning as `gate_driver_constraints.yaml`'s `CGND`. |
| `SPI_CLK` | **delete**, flagged | No real net under this name. `docs/evidence/2026-08-11-netclass-full-sync-inventory.md` sec 3 independently calls this a "zero-occurrence dead alias... from an earlier schematic revision." `RTD_SCK` is the likely successor (same FinePitch class already in `TEMPER_NET_ASSIGNMENTS`), but the exact CLK/MOSI/MISO/CS pin-role correspondence to `RTD_SCK`/`RTD_SDI`/`RTD_SDO`/`RTD_CS_N` was not independently verified against a live schematic pinout in this pass -- flagged as a follow-up rather than asserted. |
| `SPI_MOSI` | **delete**, flagged | Likely successor `RTD_SDI` (same caveat) |
| `SPI_MISO` | **delete**, flagged | Likely successor `RTD_SDO` (same caveat) |
| `SPI_CS_TEMP` | **delete**, flagged | Likely successor `RTD_CS_N` -- the "_TEMP" naming and RTD's temperature-sensing role are the strongest signal of the four |
| `TEMP_SENSE` | **delete** | No net under this name anywhere in `elec/src` or the board, not even conceptually referenced. Temperature sensing in the current design is the RTD SPI subsystem (`RTD_*` nets, `MAX31865`), which this name does not match. |

I_SENSE, `+15V`, `+3V3`, `SW_NODE` were already correct and untouched.

## 3. Does an SSOT generator apply here?

**Partially -- and not mechanically transplantable today.**
`scripts/sync_kicad_netclass_assignments.py` (#1025) is the precedent: it
generates `pcb/temper.kicad_pro`'s `netclass_assignments` from
`TEMPER_NET_ASSIGNMENTS` because both sides already share the *same* class
vocabulary (`ACMains`, `HighVoltage`, `GateDriveHV`, ... -- `TEMPER_NET_CLASSES`'
own key set).

None of the four files here share that vocabulary. Each hand-authors its
own `net_class_rules:` block with its own class names and, often, its own
clearance/trace-width numbers that diverge from `TEMPER_NET_CLASSES`
(`Ground`/`GND`/`GateDrive` instead of `GateDriveHV`/`GateDriveSELV`,
plus `PowerTrace`/`Differential`/`FinePitchPower` classes that don't exist
in `TEMPER_NET_CLASSES` at all). A generator would first have to resolve
that vocabulary mismatch -- a real, separate engineering decision (which
class in which file maps to which `TEMPER_NET_CLASSES` entry, and whether
the diverging clearance/trace-width figures are intentional per-context
overrides or drift) -- before it could safely replace any of these four
files' assignment tables the way #1025 replaced `kicad_pro`'s.

That the three live-content files (`temper_production_config.yaml`,
`temper_constraints.yaml`, `temper_deterministic_config.yaml`) had wildly
different correctness rates against the same real board (28/29, 6/11,
4/25) is itself the strongest argument *for* eventually building this
generator: each has drifted independently and by a different amount,
which is exactly the failure shape a generator forecloses. Recommended as
a follow-on, not attempted here -- `gate_driver_constraints.yaml`, being a
self-contained orphaned sub-scope experiment rather than a whole-board
config, would not be a generator target even then.

## 4. Measured consequence

**This does not parallel #1023 (+20) or #1025 (+14 clearance), and no
`power_pcb_dataset/drc_ceiling.json` change is made or needed. This was
checked, not assumed** -- tracing every consumer of the four files:

- `power_pcb_dataset/drc_ceiling.json` is measured by running kicad-cli DRC
  directly on `pcb/temper.kicad_pcb`, driven by DRU rules
  `scripts/generate_kicad_dru.py` generates from `pcb/temper.kicad_pro`'s
  `net_settings.classes`/`netclass_assignments` (already the subject of
  #1023/#1025). None of the four files this PR touches feed
  `pcb/temper.kicad_pro`, `generate_kicad_dru.py`, or `run_drc()`
  (`temper_placer.validation._drc_api`) at all.
- The two CI-gating tests that actually run DRC against
  `pcb/temper.kicad_pcb` -- `test_production_board_drc_regression` and
  `test_production_board_routing_drc_regression`
  (`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`) --
  load, respectively, nothing and `packages/temper-placer/configs/
  netclass_rules.yaml` (a fifth, *different* file, not one of the four
  the gate flagged and not touched by this PR).
- `test_golden_board_drc_regression` and the "production-placement"/
  "golden-routing" variants in that same file DRC a *different* board
  (`power_pcb_dataset/corpus/temper/temper.kicad_pcb`, a CP-SAT-placed
  fixture) and load a *different* config (`temper_induction_cooker.yaml`,
  the PCL config Gate 1 covers) -- also not one of the four here.
- None of `run_physics_flow.sh` / `run_clean_flow.sh` /
  `run_temper_deterministic.sh` / `run_feedback_loop.py` (the actual
  consumers of these four files) are invoked by any `.github/workflows/*`
  job -- confirmed by grep.

So there is no measured, CI-gating DRC baseline these 31 keys silently
starved of correct rules. This is itself the honest "measured consequence"
finding this section exists to report, not a gap in the investigation:
per `AGENTS.md`'s "Board Change -> DRC Ceiling Re-measurement" section, a
ceiling re-measurement is tied to a *board* change, and this PR makes
none (`pcb/temper.kicad_pcb` / `pcb/temper.kicad_pro` are both out of this
task's boundaries, untouched, and their content hash is unaffected).
Manufacturing a 120-sample kicad-cli run against an artifact these files
don't feed would be measuring the wrong thing, not landing the consequence
honestly.

**What *is* measurably fixed** -- the actual, live defect
(`Netlist.apply_net_class_mapping`'s silent no-op on a broken key), checked
directly against the real board and the real config content, before vs.
after this PR (`git show HEAD:<file>` vs. working tree), using the gate's
own board-correspondence check as the oracle for "silently a no-op":

| File | Broken keys before | Broken keys after |
|---|---|---|
| `configs/temper_deterministic_config.yaml` | 21 / 25 | 0 / 16 |
| `configs/temper_production_config.yaml` | 1 / 29 | 0 / 29 |
| `packages/temper-placer/configs/temper_constraints.yaml` | 5 / 11 | 0 / 10 |
| `packages/temper-placer/configs/gate_driver_constraints.yaml` | 4 / 5 | 0 / 3 |
| **Total** | **31** | **0** |

`packages/temper-placer/tests/core/test_apply_net_class_mapping_strict.py::
TestRealRepoIntegration` pins this directly against the real board and the
real (now-fixed) `temper_constraints.yaml`: both the strict method
(`apply_net_class_mapping_strict`, additive, raises on any unresolved key)
and the existing silent method now apply all 10 remaining keys with zero
skips, where before the strict method raised naming `AC_L`, `AC_N`, `PE`,
`GND`, and `+340V_BUS` and the silent method quietly dropped all five.

Secondary, unrelated finding (not fixed here, out of scope): `usb_dp`/
`usb_dn` are present in `pcb/temper.kicad_pcb`'s raw net table (each with
exactly one pad reference) but are *not* present in the `Netlist` object
`temper_placer.io.kicad_parser.parse_kicad_pcb` produces -- a parser-level
exclusion, unrelated to and unaffected by this PR's board-correspondence
fix, worth a separate look if `run_feedback_loop.py`'s USB differential
pair handling is ever exercised for real.

## 5. Gate promoted to blocking

With all 31 keys reconciled, `scripts/check_netclass_map_board_correspondence.py`
exits 0 against the real repo. `continue-on-error: true` is removed from
the "Net-class map <-> board correspondence gate (Gate 3)" step in
`.github/workflows/python-tests.yml`, and
`scripts/tests/test_check_netclass_map_board_correspondence.py`'s
`TestRealRepoIntegration` now pins the clean state (regresses if a future
PR reintroduces a broken key) instead of the original 31-key violation.

## 6. What remains open

- The 4 `SPI_*` deletions in `configs/temper_deterministic_config.yaml`
  are flagged, not resolved, to a likely `RTD_*` successor (Section 2) --
  worth a follow-up once someone can verify the exact pin-role
  correspondence against a live schematic/pinout.
- `PGND`/`CGND` (both files) and `PWR_RTN`'s own classification remain a
  genuinely open, separately-reserved decision (`PROTECTED_NETS`) --
  intentionally not settled by this PR.
- `configs/temper_production_config.yaml` and `packages/temper-placer/
  configs/gate_driver_constraints.yaml` remain unconsumed by any code path
  (dead config); fixed anyway per the production config's own established
  "corrected even though dead, so it cannot silently reactivate" precedent.
- The board-dimension staleness (100x150mm/30x30mm vs. the real
  152x234mm board) noted in Section 1 is a distinct, already-flagged
  defect (`docs/evidence/2026-08-11-correspondence-gates.md`'s Gate 3
  section) -- not addressed here.
