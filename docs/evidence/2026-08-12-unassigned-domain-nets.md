<!-- provenance: commit=756968706b4025b6910ec33c20a0c63fd7bb6b5b dirty=true (base commit is origin/main's tip at session start, fix(sat-encoding): delete dead aux-var-name allocation + pack CnfFormula.clauses (R1+R2), #1075; "dirty=true" is honest -- the measurements below are BEFORE/AFTER pairs across this PR's own diff to pcb/temper.kicad_pro, scripts/check_hv_netclass_coverage.py and its test file). pcb/temper.kicad_pcb was never modified at any point (confirmed: `git status` shows no changes to it throughout this work; every board-net fact below comes from a read-only structural parse). Sweep counts (domain manifest vs kicad_pro vs real board) computed by a standalone Python s-expression tokenizer over pcb/temper.kicad_pcb (not grep -- see Sec 2), cross-checked against elec/domain_manifest.yaml via PyYAML and pcb/temper.kicad_pro via json, then re-derived independently by the shipped gate (scripts/check_hv_netclass_coverage.py) itself, both results agreeing exactly. DRC measured with kicad-cli 10.0.5 (/home/bennet/.local/opt/kicad-10.0.5), via temper_placer.validation._drc_api.run_drc / scripts/ci_check_drc.py --backend kicad-cli (--all-track-errors, single-thread KICAD_CONFIG_HOME pin, pcb/temper.kicad_dru freshly regenerated from scripts/generate_kicad_dru.py before each measurement -- the repo's own protocol). "Before" = pcb/temper.kicad_pcb (real, committed, sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, byte-identical to power_pcb_dataset/drc_ceiling.json's recorded provenance input) paired with pcb/temper.kicad_pro as of origin/main (git show HEAD:pcb/temper.kicad_pro); "after" = the same board paired with this PR's pcb/temper.kicad_pro. Both variants measured from read-only scratch copies outside the repo; pcb/temper.kicad_pcb itself was never written. 20 samples per variant. -->

# `PWR_RTN` had no netclass, and it is one of 58 places `pcb/temper.kicad_pro`'s netclass_assignments disagrees with reality. The fix breaches the DRC ceiling on purpose.

**Verdict up front.** `PWR_RTN` — the doubler midpoint, declared HV-domain at `elec/domain_manifest.yaml:95`, a separate net from `gnd`, measured up to 753.7 V peak against `tank.c_tank1-p2` — had **no entry** in `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments`, so it fell to `Default` (0.2mm clearance) and was invisible to every HV↔SELV clearance and creepage rule. The correct class is **`HighVoltage`**, matching its direct circuit siblings (`+170V_BUS`, `DC_BUS_RTN`, `SW_NODE`) that are already classed that way, and adequate at the measured worst-case voltage per `docs/evidence/2026-08-12-hv-clearance-adequacy.md`'s own table (753.7 V → 1.58–2.00mm required, 2.0mm provided → OK). **Fixed**, one line, no netclass *value* touched.

The sweep this task asked for found the same defect shape **58 more times**, of three distinct kinds: **21** domain-declared nets absent from `kicad_pro`'s real assignments (1 HV, 20 SELV — `PWR_RTN` plus 20 lower-severity SELV nets, including `gnd`, the board's largest net), **37** `kicad_pro` assignments naming a net that does not exist on the real board (pre-existing, deliberately-kept dead aliases from an earlier schematic revision), and **0** cases of a domain net assigned a class whose safety category contradicts its domain. A gate now exists (`scripts/check_hv_netclass_coverage.py` PROPERTY 3, extending the existing gate rather than adding a new one) that blocks on the first shape for the `HV` domain specifically — shown failing on the real, unfixed defect (exit 3, naming `PWR_RTN`) and passing clean (exit 0) after the fix, in this document's own Sec 5.

**The fix breaches the DRC ceiling.** Assigning `PWR_RTN` its correct class newly enforces HV↔SELV clearance/creepage against every net that crosses it, revealing real, pre-existing violations that were invisible only because the net had no class: `clearance` 386→396 (+10, ceiling 386, **breach**), `creepage` ~183→~197 (+11 to +14, ceiling 186, **breach**), aggregate errors ~1264→~1288 (+22 to +24, ceiling 1266, **breach**). Per this task's explicit instruction, the ceiling is **not** raised and the class is **not** weakened to avoid it — see Sec 6.

---

## 1. `PWR_RTN`: verified, and the correct class

### 1.1 The hole, confirmed independently of the brief

```
$ python3 -c "
import json
na = json.load(open('pcb/temper.kicad_pro'))['net_settings']['netclass_assignments']
print('PWR_RTN' in na)"
False
```

`elec/domain_manifest.yaml:95` (`PWR_RTN`, under `domains.HV.nets`):

> `PWR_RTN            # power_return, the doubler midpoint (main.ato override_net_name). Confirmed a SEPARATE net from `gnd` as of this manifest (net 6, 17 pins) -- the star-join short that used to merge them into one net has been removed.`

`PWR_RTN` is net **13** in `pcb/temper.kicad_pcb`'s own top-level net table (`(net 13 "PWR_RTN")`) — it is a real, wired net, not a manifest artifact. With no `kicad_pro` entry it fell to KiCad's `Default` netclass — 0.2mm clearance, the thinnest rule on the board, and no creepage rule at all — for every pair it participates in.

### 1.2 The correct class: `HighVoltage`

Three independent lines of evidence:

1. **Its direct circuit siblings are already classed `HighVoltage`.** `PWR_RTN` is the doubler midpoint the tank return, the bus rails (`+170V_BUS`, `DC_BUS_RTN`) and the switch node (`SW_NODE`) are all built around — every one of those three is already `"HighVoltage"` in `pcb/temper.kicad_pro`. `PWR_RTN` is one Y-cap from `gnd`/`pe` (`elec/domain_manifest.yaml:502-505`) and carries the full tank return current — it is not a lower-potential node than its siblings, it is the same bus's return.
2. **`HighVoltageIsolated` (6.0mm, "floating gate-drive bootstrap supply") does not describe it.** `PWR_RTN` is not a floating secondary-side bias rail behind a gate-driver's reinforced barrier; it is directly wired into the doubler and the tank return path. `ACMains` (325V-rated, the raw line/neutral input) doesn't fit either — the established convention in this file classes everything downstream of the bridge/doubler as `HighVoltage`, not `ACMains`, and `PWR_RTN` is downstream of it.
3. **The measured worst-case voltage is adequately covered by `HighVoltage`'s existing 2.0mm figure.** `docs/evidence/2026-08-12-hv-clearance-adequacy.md` (PR #1080, `analysis/hv-clearance-adequacy`, unmerged) measured `tank.c_tank1-p2` ↔ `PWR_RTN` with ngspice against the committed ZVS deck: **753.7 V peak** at the worst OCP-01-passing point across the legal 44–50 kHz PLL band and L/C tolerance corners. That document's own Sec 4.1 table gives this pair `V_det = 2 084 V → 1.58mm (interpolated) / 2.00mm (step reading) required, 2.0mm provided → OK` — the same margin analysis (and the same caveats: OVC II vs III unresolved, IEC 60664-4 not considered, held by OCP-01 rather than by geometry alone) that already governs every other `HighVoltage` pair on this board. No class other than `HighVoltage` is both circuit-consistent and voltage-adequate.

`GND`/`Default`/`Power`/`FinePitch` were never candidates: all are LV-safe classes (0.2–0.5mm, no creepage), and `PWR_RTN` is a mains-referenced, HV-domain conductor by the manifest's own uncontested classification.

**Fix applied** (`pcb/temper.kicad_pro`, one line, no netclass *value* touched — PR #1061 reconciled those and they are settled):

```diff
       "hb.power_loop.q_high-g": "HighVoltage",
       "DC_BUS_RTN": "HighVoltage",
+      "PWR_RTN": "HighVoltage",
```

### 1.3 A related, out-of-scope finding

`packages/temper-placer/src/temper_placer/core/design_rules.py:397` — the *Python placer's own* net-class model, a completely separate file from `pcb/temper.kicad_pro` — maps `PWR_RTN` to `"GND"` (an LV-safe class). This is the *same* shape of defect in a different file, already known and deliberately left alone: `scripts/check_hv_netclass_coverage.py`'s docstring and `scripts/sync_kicad_netclass_assignments.py`'s `PROTECTED_NETS` both flag `PWR_RTN`→`GND` as "reserved for a human decision" because of its larger blast radius on the Python-side placer/router, not the KiCad DRC. This document does not touch it — the task's scope is `pcb/temper.kicad_pro`'s netclass *assignments*, the file that actually drives `kicad-cli`'s DRC, and that is now fixed. `design_rules.py`'s own `PWR_RTN → GND` mapping remains a legitimate follow-up, orthogonal to this fix.

---

## 2. The sweep — cross-referencing all three sources

Three sources, cross-referenced structurally:

1. **`elec/domain_manifest.yaml`** — every net declared `HV` or `SELV` domain (19 + 32 = **51** nets).
2. **`pcb/temper.kicad_pro`**'s `net_settings.netclass_assignments` — what actually carries a class (**78** entries before this fix, **79** after).
3. **`pcb/temper.kicad_pcb`**'s own net table — the real, compiled board (**162** nets).

Source 3 was walked with a hand-written S-expression tokenizer that tracks paren depth and matches only `(net N "name")` forms that are **direct children of the file's outermost `(kicad_pcb ...)` form** — not a grep for the substring `(net`, which also matches every pad's own nested per-pad net reference (`(pad ... (net N "name"))`) many levels deeper. This is the exact failure the brief warned about: *"a prior agent's grep-based pad count was wrong because of this."* A naive `text.count("(net ")` over a two-net, one-pad synthetic fixture returns 3 (two top-level declarations plus the pad's own nested reference); the structural walk correctly returns 2. See `scripts/check_hv_netclass_coverage.py::parse_board_net_names` and `scripts/tests/test_check_hv_netclass_coverage.py::TestBoardNetParsing::test_grep_would_overcount_vs_structural_parse` for the falsifier, and `docs/evidence` methodology note above for the independent full-tree parse used to cross-check every count in this document.

### 2.1 Type 1 — domain-declared net, no `kicad_pro` assignment: **21**

| Net | Domain | Notes |
|---|---|---|
| `PWR_RTN` | **HV** | The specific hole (Sec 1). Fixed in this PR. |
| `gnd` | SELV | The board's own largest net (86 pads, `design_rules.py`'s own comment) — falls to `Default` (0.2mm / no `plane_preferred` routing hint from `kicad_pro`'s perspective) rather than any purpose-built class. |
| `DISCHARGE_CTRL` | SELV | |
| `RELAY_CTRL` | SELV | |
| `SHUTDOWN` | SELV | |
| `WDT_RESET_N` | SELV | |
| `i2c_scl_ui` | SELV | |
| `i2c_sda_ui` | SELV | |
| `usb_dn` | SELV | |
| `usb_dp` | SELV | |
| `rtd_force_p` / `rtd_force_n` | SELV | |
| `rtd_sense_p` / `rtd_sense_n` | SELV | |
| `discharge.k_dis1-coil1` / `-coil2` | SELV | Relay coil-drive pins |
| `discharge.k_dis2-coil1` | SELV | Shares `-coil2` with `k_dis1` (one physical net, per the manifest's own comment) |
| `power_in.bypass_relay-coil1` / `-coil2` | SELV | |
| `safety.ovp.comp-inp` | SELV | |
| `safety.uvlo_logic-line` | SELV | |

**Severity is not uniform across this list, and that matters for what the gate below enforces.** `PWR_RTN` (HV) is the acute hazard: KiCad DRC takes the **maximum** of the two nets' netclass figures for any pair, so an unassigned net on the **HV** side of a mains crossing drops the enforced separation to the generic 0.2mm floor on *both* sides at once. An unassigned net on the **SELV** side does not have that effect — every HV↔SELV pair is still protected as long as the HV side carries a real class, which (after this fix) every `HV`-domain net now does. The 20 SELV gaps are the same defect *shape* — worth fixing as routing/plane-strategy hygiene, `gnd` especially — but they are not silently disabling a mains-crossing rule the way `PWR_RTN`'s gap was. This is why the gate in Sec 5 blocks on the `HV` list and reports the `SELV` list informationally; see that section for the full reasoning.

### 2.2 Type 2 — `kicad_pro` assignment naming a net absent from the board: **37**

Every one of these is a differently-spelled or differently-cased leftover from an earlier schematic revision, sitting alongside the real, correctly-classed net it was superseded by: `AC_L`/`AC_N`/`PE` (real: `ac_l`/`ac_n`, both already `ACMains`; `pe` does not exist as a separate net post-`SELV_ISOLATION_REDESIGN.md`), `DC_BUS+`/`DC_BUS-` (real: `DC_BUS_RTN`, `+170V_BUS`), `SWITCH_NODE` (real: `SW_NODE`), `GATE_H`/`GATE_L`/`PWM_H`/`PWM_L` (real: `GATE_HS`/`GATE_LS`/`PWM_HS`/`PWM_LS`), `GND` (real: `gnd`), `RTD_CS` (real: `RTD_CS_N`), `+3.3V` (real: `+3V3`), `USB_D+`/`USB_D-` (real: `usb_dp`/`usb_dn`), `VBOOT_H`/`VBOOT_L`/`+5V_ISO` (no live counterpart at all — the isolated bootstrap nets on this board are `hb.gate_hs.driver-p1-1`/`-p2`, already correctly classed `HighVoltageIsolated`), plus 16 UI/debug names (`BTN_UP`/`BTN_DOWN`/`BTN_SELECT`, `ENCODER_A`/`ENCODER_B`, `I2C_SCL`/`I2C_SDA`, `SPI_CLK`/`SPI_CS_TEMP`/`SPI_MISO`/`SPI_MOSI`/`SPI_SCK`, `FAULT_STATUS`/`MCU_ENABLE`/`PGOOD`/`SHUTDOWN_N`/`TEMP_FAULT`/`V_SENSE`/`ZCD`) with no compiled counterpart under those exact spellings.

**None of these 37 collides with a domain-declared net's exact name** — every `HV`/`SELV` net that needs a real assignment already has one keyed under its own exact, correct spelling (confirmed programmatically: the intersection of the 37 ghost keys and the 51 domain-declared names is empty). This is why the historical AC_L/AC_N/PE defect (safety classes assigned to names the board never carried, described in the task brief) reads as *already fixed* today: `ac_l`/`ac_n` carry the real assignments now, and the wrong-case ghosts are harmless residue, not a live gap. `scripts/sync_kicad_netclass_assignments.py`'s own docstring documents this as a deliberate, permanent choice — "It never removes an existing kicad_pro entry, even one that names a net no longer present on the board" — so this count is reported, not remediated, in this PR.

### 2.3 Type 3 — domain net's assigned class contradicts its declared domain: **0**

Checked against `packages/temper-placer/configs/netclass_rules.yaml`'s own `safety_category` field (the netclass parameter SSOT, `HV`/`AC`/`LV`/`iso` vocabulary) for every domain-declared net that **does** have a `kicad_pro` assignment (30 before this fix, 31 after): every `HV`-domain net assigned a class resolves to `safety_category` `HV` or `AC` (`ACMains`, `HighVoltage`, `GateDriveHV`, `HighVoltageIsolated`); every `SELV`-domain net assigned a class resolves to `LV` (`Power`, `GateDriveSELV`, `FinePitch`, `Default`). Zero contradictions in either direction. **A count of zero here is itself informative**, not a non-finding: it means the historical "safety class assigned to the wrong-cased ghost name" failure mode (Type 2, already resolved for domain nets per Sec 2.2) is the one this board actually suffered from, not a live class/domain mismatch — the two are different failure shapes and this sweep checked both independently rather than assuming one implies the other.

---

## 3. The gate

### 3.1 What existed, and why it didn't catch this

`scripts/check_hv_netclass_coverage.py` (PROPERTY 1) already checks "every `HV`-domain net has an entry in `TEMPER_NET_ASSIGNMENTS`" — but `TEMPER_NET_ASSIGNMENTS` is `design_rules.py`'s **Python placer model**, not `pcb/temper.kicad_pro`. `PWR_RTN` **is** present there (mapped to `"GND"`, Sec 1.3's separate finding) — so PROPERTY 1 passed on `origin/main` the entire time `PWR_RTN` had zero real protection, because it was checking a rule *exists* in the wrong file, not what the file that actually drives `kicad-cli`'s DRC says. This matches the brief's suspicion exactly.

`scripts/sync_kicad_netclass_assignments.py`'s `manifest.yaml` entry (`scripts/manifest.yaml:2125`) claims *"`--check` mode is the CI tripwire against future drift"* — `.github/workflows/python-tests.yml` was searched for any invocation of this script (`grep -n sync_kicad_netclass_assignments .github/workflows/python-tests.yml`): the name appears exactly once, inside a comment about a *different* gate (`check_netclass_class_param_correspondence.py`, added 2026-08-12). The script is never actually run as a CI step. The claim is false on `origin/main` as of this commit.

### 3.2 What was added — extending the real gate, not a new one

`scripts/check_hv_netclass_coverage.py` gained **PROPERTY 3** (blocking) and **PROPERTY 4** (informational), reading `pcb/temper.kicad_pro`'s real `net_settings.netclass_assignments` and a structural walk of `pcb/temper.kicad_pcb` directly — the two inputs PROPERTIES 1/2 never touch:

- **PROPERTY 3 (blocking, `HV` domain only):** every `HV`-domain net must (a) exist as a real net on the board, (b) have an entry in `kicad_pro`'s real `netclass_assignments`, and (c) resolve to a `safety_category` of `HV`/`AC` via `netclass_rules.yaml`. Scoped to `HV` specifically, matching the brief's own framing ("a net declared HV/mains-domain has no netclass assignment") and the severity argument in Sec 2.1: an unassigned `HV` net is the acute, both-sides-of-a-crossing hazard; fixing exactly the one that exists today (`PWR_RTN`) is sufficient to bring this property to a clean pass.
- **PROPERTY 4 (informational, never blocks):** the same three checks for `SELV`, plus every `kicad_pro` assignment (either domain) naming an off-board net. Not gated, for the reasons in Sec 2.1 (severity) and Sec 2.2 (the 37 ghosts are permanent, accepted debris by this repo's own documented convention) — gating on either would make the property permanently red for defects nobody introduced and this task was not asked to remediate, defeating the "shown failing before, passing after" requirement below.

`PROPERTY 3` activates only when `kicad_pro`'s JSON literally declares the `netclass_assignments` key — every real KiCad project file does; this keeps all 32 pre-existing PROPERTY 1/2 tests, which use minimal synthetic fixtures without that key, behaving identically. 20 new tests were added (`TestPropertyThreeAndFour`, `TestBoardNetParsing`), covering: the `PWR_RTN` shape itself (an HV net present in `TEMPER_NET_ASSIGNMENTS` but absent from `kicad_pro`'s real table — proving PROPERTY 1 alone does *not* catch it), an off-board HV net (the `+340V_BUS`→`+170V_BUS` rename shape), a wrong-safety-category HV assignment, that SELV/ghost findings never flip the gate, and that the structural board parser disagrees with a naive grep on a fixture engineered to prove it (`test_grep_would_overcount_vs_structural_parse`).

### 3.3 Shown failing before, passing after

```
$ git show HEAD:pcb/temper.kicad_pro > pcb/temper.kicad_pro   # ONLY kicad_pro reverted to
                                                                # origin/main (no PWR_RTN entry);
                                                                # the gate script itself (this PR's
                                                                # PROPERTY 3/4) stays in place, so
                                                                # this genuinely exercises the new
                                                                # gate against the unfixed defect.
$ uv run python scripts/check_hv_netclass_coverage.py; echo "exit: $?"
...
=== PROPERTY 3 (BLOCKING): HV-domain nets vs pcb/temper.kicad_pro's REAL netclass_assignments (78 assignment(s) on file) ===
  off-board HV-domain nets: 0
  unassigned in kicad_pro: 1
    VIOLATION net 'PWR_RTN' is declared under elec/domain_manifest.yaml's HV domain but has NO
    entry in pcb/temper.kicad_pro's net_settings.netclass_assignments -- falls to Default (0.2mm),
    invisible to every HV<->SELV clearance/creepage rule
  wrong-safety-category assignments: 0
...
FAILED -- 0 unclassified HV net(s) (PROPERTY 1), 0 netclass(es) with no rules (PROPERTY 2),
0 off-board HV-domain net(s), 1 HV-domain net(s) unassigned in kicad_pro, 0 HV-domain class
safety-category mismatch(es) (PROPERTY 3)
exit: 3

$ git checkout -- pcb/temper.kicad_pro   # PWR_RTN -> HighVoltage restored (this PR's committed fix)
$ uv run python scripts/check_hv_netclass_coverage.py; echo "exit: $?"
...
=== PROPERTY 3 (BLOCKING): HV-domain nets vs pcb/temper.kicad_pro's REAL netclass_assignments (79 assignment(s) on file) ===
  off-board HV-domain nets: 0
  unassigned in kicad_pro: 0
  wrong-safety-category assignments: 0
...
HV netclass coverage gate passed
exit: 0
```

All 52 tests in `scripts/tests/test_check_hv_netclass_coverage.py` pass (`uv run pytest scripts/tests/test_check_hv_netclass_coverage.py -v` — 32 pre-existing + 20 new), `ruff check` is clean on both changed files.

---

## 4. Other pre-existing gates checked, for context

Not part of this PR's changes, run to confirm no collateral breakage: `scripts/check_netclass_class_param_correspondence.py` (clean, 0 field mismatches — PWR_RTN's addition doesn't touch any class *value*), `scripts/check_netclass_map_board_correspondence.py` (clean, 58 keys checked). `scripts/check_domain_partition.py` requires a locally-built `elec/build/default.net` (gitignored, not built in this session — pre-existing environment gap, unrelated). `scripts/check_pcl_config_board_correspondence.py` and `scripts/check_layer_plane_emission_coverage.py` both fail on `origin/main` already, for reasons entirely unrelated to netclasses (stale component-reference legacy configs; a Rust parser dropping a layer-role token) — confirmed pre-existing by inspection, not touched by this PR's diff.

---

## 5. Blast radius — measured, and it breaches the ceiling

kicad-cli 10.0.5, `--all-track-errors`, single-thread `KICAD_CONFIG_HOME` pin, `pcb/temper.kicad_dru` freshly regenerated from `scripts/generate_kicad_dru.py` before every run (`scripts/ci_check_drc.py`'s own protocol). Both variants measured against the real, byte-identical, committed `pcb/temper.kicad_pcb` (sha256 `6928b7c8…`, matching `drc_ceiling.json`'s recorded provenance) from read-only scratch copies; the board file itself was never written. 20 samples per variant.

**"Before" reproduces the committed ceiling record exactly**, confirming methodology fidelity before trusting the delta: `clearance` 386/386 (20/20 samples, fully deterministic, matches the ceiling's own `violations_by_type.clearance: 386`), `creepage` in `{183, 184}` (within the ceiling's own recorded 182–184 nondeterministic band), aggregate errors `{1263, 1264}` (within `error_ceiling: 1266`), warnings `624/20` (matches "before" exactly — see the note on this figure below).

| Category | Before (20 samples) | After (20 samples) | Δ | Ceiling | Breach? |
|---|---:|---:|---:|---:|---|
| `clearance` | **386** (386–386, deterministic) | **396** (396–396, deterministic) | **+10** | 386 | **YES, +10** |
| `creepage` | 183–184 | 196–198 | **+11 to +14** | 186 | **YES, +10 to +12** |
| aggregate errors | 1263–1264 | 1286–1288 | **+22 to +24** | 1266 | **YES, +20 to +22** |
| every other error category (11 categories: `annular_width`, `copper_edge_clearance`, `courtyards_overlap`, `drill_out_of_range`, `hole_clearance`, `hole_to_hole`, `shorting_items`, `solder_mask_bridge`, `track_width`, `tracks_crossing`, `via_diameter`) | unchanged | unchanged | **0** | — | no |
| all warning categories | 624 total, unchanged | 624 total, unchanged | **0** | 489 | pre-existing, see below |

`scripts/ci_check_drc.py --backend kicad-cli` run directly against this PR's real, committed changes (not a scratch copy) confirms the same result and the same exit code CI would produce:

```
FAIL: temper: DRC FAIL
  aggregate errors 1288 exceeds ceiling 1266 (+22)
  per-type errors (source: kicad-cli): 2 categories over ceiling (0 new, 2 regressed):
    [   ] clearance 396 > 386 (+10)
    [   ] creepage 198 > 186 (+12)
PASS: noise-headroom guard (single-sample DRC is safe for every recorded category)
$ echo $?
1
```

**The warning-count figure (624, vs. `warning_ceiling: 489`) is unrelated to this fix and is not a new breach.** It is identical between "before" and "after" (624 in both, 20/20 samples each) — the "before" measurement, on `origin/main`'s own `pcb/temper.kicad_pro`, already reads 624 in this environment, purely because this measurement environment's kicad-cli 10.0.5 prefix lacks the `kicad-footprints` package (`power_pcb_dataset/drc_ceiling.json`'s own provenance note on its most recent entry: *"This install lacks the kicad-footprints package... which inflates lib_footprint_issues... for BOTH the old and new board content identically -- an environment artifact, not a measured delta"*). Zero delta attributable to `PWR_RTN`'s reclassification; not reported as this PR's blast radius.

**`clearance` and `creepage` are real, attributable regressions against the ceiling, not noise.** Both are exactly the categories the newly-enforced HV↔SELV rules touch, both move in the direction the fix predicts (more separation now required around a net that previously required none), and `clearance` is fully deterministic (386→396, 20/20 samples each side) while `creepage`'s spread (a KiCad-internal pointer-dedup nondeterminism, `docs/evidence/2026-08-04-drc-measurement-determinism.md`, issue #20048) shifts as a whole band (182–184 → 196–198) rather than overlapping it.

### 5.1 Per the task's explicit instruction: not engineered around

**The ceiling is not raised in this PR, and `HighVoltage` was not swapped for a weaker class to stay under it.** `PWR_RTN` assigned its correct class newly enforces real HV↔SELV clearance/creepage rules against every net that crosses it on the real, physical board — the ~10–14 new violations are real copper that is, right now, closer to a mains-referenced conductor than the newly-enforced rule requires. Making the netclass assignment correct is this task's job; making the copper satisfy the newly-correct rule is a routing/layout change to `pcb/temper.kicad_pcb`, which is explicitly out of scope here ("Do not modify `pcb/temper.kicad_pcb`") and is reported as a finding for the board owner, not resolved in this PR.

---

## 6. Summary of what changed and what didn't

| File | Change |
|---|---|
| `pcb/temper.kicad_pro` | +1 line: `"PWR_RTN": "HighVoltage"` in `net_settings.netclass_assignments`. No netclass *value* touched. |
| `scripts/check_hv_netclass_coverage.py` | +PROPERTY 3 (blocking, HV) / PROPERTY 4 (informational, SELV + ghosts), reading `kicad_pro`'s real assignments and a structural `kicad_pcb` net-table parse. PROPERTIES 1/2 unchanged. |
| `scripts/tests/test_check_hv_netclass_coverage.py` | +20 tests (`TestPropertyThreeAndFour`, `TestBoardNetParsing`). All 32 pre-existing tests pass unchanged. |
| `pcb/temper.kicad_pcb` | **Not touched.** |
| `power_pcb_dataset/drc_ceiling.json` | **Not touched** — see Sec 5.1. |
| Netclass parameter *values* (`pcb/temper.kicad_pro`'s `net_settings.classes[]`, `netclass_rules.yaml`, `design_rules.py`'s `TEMPER_NET_CLASSES`) | **Not touched** — PR #1061 reconciled these and they are settled, per the task's explicit instruction. |
