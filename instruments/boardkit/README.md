# temper-boardkit

KiCad-free PCB craft and checks shared by Temper's hand-routed boards: the craft passes and pre-DRC that grew
in the LCR meter (instruments/lcr-meter, Rev F), the Gerber re-read and JLC checks that grew in the wireless
thermometer's RB1 (instruments/wireless-thermometer/proto/revisions/rb1-ads-readout), and the pcbnew helpers
both used.  Hand routing only: nothing here searches for paths or calls an autorouter.

It lives in `instruments/boardkit/`, beside the instrument boards that use it.  The top-level `packages/`
tree was removed from main in the legacy cleanup (#1673, #1676), and zapote's policy (`zapote/AGENTS.md`)
keeps engineering rules for the cooker boards in Rust under `zapote/packages/`.  This package is the
shared Python tooling for the instrument boards (pcbnew scripts, KiCad's Python 3.9).  It is not a
zapote rule owner.

## Contents

| module | what | needs |
|---|---|---|
| `model` | plain-dict board model (parts, pad library, tracks, vias, keepouts); `Layout` with the pad-addressed routing helpers `P`, `B`, `T`, `T45`, `V`, `DROP`, `WIDEN`, `KO`; `rot`, `unrot`, `r3`, `norm_rot`, `fp_name` | stdlib |
| `craft` | deterministic craft passes (T-junction split, straight land entry, merge, 45-degree chamfer, via growth, stitching vias, reference placement) and their checks (incl. IPC-2152 current, teardrops) | shapely for the passes; the pure checks run without it |
| `predrc` | `PreDRC`: clearance, edge, holes, keepouts, via-on-land, width, courtyard, angle, craft, connectivity, dangling; `summary`, `compare` (tally against a kicad-cli DRC json), `render` | shapely (matplotlib for `render`) |
| `gerber` | RS-274X / Excellon reader (arcs as chords, regions, X2 attributes); `GerberSet`, `Copper` (connectivity rebuilt from geometry, joined through plated holes), `connectivity`, `outline`, `drill_check`, `paste_check`, `mask_check`, `silk_texts`, `silk_check` | shapely, numpy |
| `jlc` | `RULES` (legend, mask, edge limits) quoting `jlc/data/jlc-capabilities-excerpts.txt` | stdlib |
| `jlc.easyeda` | EasyEDA/LCSC record fetch and cache (lceda.cn mirror), PAD parsing, `renumber`, `fit_cpl_offset` (CPL rotation), `fit_rigid` (3D model placement) | stdlib |
| `jlc.placement` | JLC placement-preview simulation from the CPL against the Gerber pads; SVG overlay | stdlib |
| `jlc.order` | one assembly fee model (Economic, Standard, hand fit), `tier_price`, `buy_qty`, `is_extended`, X-ray tiers | stdlib |
| `jlc.models_3d` | exact-part STEP models from EasyEDA placed in the KiCad footprint frame | OCP (CAD env) |
| `kicad` | lazily imported pcbnew: `load_board`, `pad_table`, `footprint_pads`, `edge_clearance`, `via_in_pad(_audit)`, `joint_counts`, `MODEL_SWAP` / `apply_model_swap` | KiCad's Python |
| `cli` | `boardkit-predrc`, `boardkit-gerber-check`, `boardkit-edge-clearance` | as the modules |

`model`, `craft`, `kicad`, `jlc`, `jlc.easyeda`, `jlc.order` and `jlc.placement` are Python 3.9 compatible and
import under KiCad's bundled Python, which has neither shapely nor numpy.  Nothing is imported by the package
`__init__`.

## Calling it

From KiCad's Python (or any script in the repo), put the source directory on the path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(REPO / 'instruments' / 'boardkit' / 'src'))
from temper_boardkit import craft, kicad
```

The LCR meter does this once in `instruments/lcr-meter/cad/tools/boardkit_path.py`; its scripts `import
boardkit_path` first.

Sparse worktrees that check out `/instruments/` already have the package.

From uv, without building the workspace (the root workspace holds a maturin crate):

```sh
cd instruments/boardkit
PYTHONPATH=src uv run --no-project --with shapely --with numpy --with pytest python -m pytest
PYTHONPATH=src uv run --no-project --with shapely --with numpy python -m temper_boardkit.cli predrc --help
```

The package is not a member of the root uv workspace yet: adding it needs `uv lock` online (shapely and numpy
are not in the root lock), which has not been run.

## Per-board migration

LCR meter, `instruments/lcr-meter` (migrated; outputs byte-identical, see the migration commit):

| LCR file | now |
|---|---|
| `cad/tools/craft.py`, `cad/tools/test_craft.py` | deleted: `temper_boardkit.craft`, `tests/test_craft.py` (the 28 cases) |
| `cad/tools/predrc.py` | the LCR configuration (pad library, five exposed pads, GND plane on In1.Cu, BNC/USB `J` edge exemption, cache file) over `predrc.PreDRC`, and the CLI with `--kicad` calibration |
| `cad/tools/rev_f.py` | `rot`, `unrot`, `r3`, `fp`, `pad_local`, `pad_at`, `B`, `P`, `T`, `T45`, `V`, `DROP`, `WIDEN`, `KO`, `norm_rot`: `model.Layout` |
| `cad/tools/placement_offsets.py` | `jlc.easyeda.record` / `easyeda_pads` / `renumber` / `fit_cpl_offset`, `kicad.footprint_pads`; keeps the LCR pad renumbering (C2286) and the audit file |
| `cad/tools/edge_clearance.py` | `kicad.edge_clearance` |
| `cad/audit_dfm.py` | `kicad.via_in_pad_audit`; keeps the expected exposed-pad set and the receipt |
| `cad/tools/models_3d.py` | `jlc.models_3d.build`; keeps the footprint -> LCSC list |
| `manufacturing/order_estimate.py` | `jlc.order.fees` / `tier_price` / `buy_qty` / `is_extended`, `kicad.joint_counts` |
| `cad/build_cad.py` | `kicad.apply_model_swap` (`MODEL_SWAP`) |
| `cad/tools/pour.py`, `pour_report.py`, `validation/power-spurs/current_check.py` | import `temper_boardkit.craft` |

`calkit/order_estimate.py` still carries its own copy of the fee constants (it says so); move it to
`jlc.order` when it is next touched.

Wireless thermometer RB1: not migrated (its worktree is live).  Mapping:

| RB1 (`rb1-ads-readout/`) | boardkit |
|---|---|
| `gerber_read.py`: `read_gerber`, `read_drill`, `aperture_shape` | `gerber.read_gerber`, `read_drill`, `aperture_shape` (same parser; `parse_gerber` / `parse_drill` take text) |
| `dfm_checks.py` `JLC`, `TOL` | `jlc.RULES` (same values, plus `edge_copper_vcut`), `gerber.TOL` |
| `dfm_checks.py` `gxy`, `key`, `ap_geom`, `flash_geoms`, `draw_geoms`, `region_geoms` | `gerber.gxy(org)`, `gerber.key`, `GerberSet` methods |
| section 1 copper union, hole union-find, `pads`, `pads_on`, `pad_comp`, shorts / opens / missing / extra | `gerber.Copper`, `gerber.connectivity(copper, expected_pad_nets, net_ties)` |
| section 1 outline, drill sets, paste | `gerber.outline`, `gerber.drill_check(expected_pth, expected_npth)`, `gerber.paste_check(assembled_refs, bare_also)` |
| section 2 EasyEDA pads about the head, CPL placement, pad error, SVG | `jlc.easyeda.pads_about_head`, `jlc.placement.read_cpl` / `simulate` / `overlay_svg` |
| section 3 kicad_pcb s-expression texts, silk, mask | `gerber.sexpr`, `silk_texts`, `silk_check`, `mask_check(via_d=0.3)` |
| `order_estimate.py` `EXT_FEE`, `SETUP_STENCIL`, `JOINT`, tier price, buy quantity, extended rule | `jlc.order.ECONOMIC['extended_line']`, `ECONOMIC['setup'] + ECONOMIC['stencil']`, `SMT_JOINT`, `tier_price`, `buy_qty`, `is_extended` |
| `sources/jlc-capabilities-excerpts.txt` | `jlc/data/jlc-capabilities-excerpts.txt` (copied verbatim) |

RB1 behaviour not reproduced here (stays in RB1 when it migrates):

* sections 4-6 of `dfm_checks.py` (land patterns against datasheets, I2C rise time, mux settling): board
  physics, not tooling;
* the expected drill sets: RB1 derives them from `pcb/layout.json` vias, the THT pads of `J1`/`J2`/`J3`/`TP*`
  and four corner holes; `drill_check` takes them as arguments, and `paste_check(bare_also=...)` takes the THT
  pad names;
* `pin-map.json` is stored KiCad -> EasyEDA; `simulate(pin_map=...)` wants EasyEDA -> KiCad (invert it);
* silk result keys are renamed (`below_1.0mm_height` -> `below_text_height`, `below_0.15mm_stroke` ->
  `below_line_width`, `warn_ratio_below_1to6` -> `warn_ratio`), so `checks/dfm.json` would change shape;
* `order_estimate.py`'s JLC parts-API snapshot fetch (curl POST), `PCB_RANGE`, and joints from
  `fab/placement-audit.json`; and RB1's total, which is setup + stencil + extended fees + joints only, while
  `jlc.order.fees` also adds X-ray, placement confirmation and the fab quote;
* no RB1 output has been regenerated through boardkit, so there is no identical-output proof for RB1 yet.

## Tests

`tests/`: the 28 ported craft cases, the model helpers, and a passing and a failing case for each pre-DRC,
Gerber and JLC check on tiny synthetic boards and Gerbers (`fixtures.py`, built in the tests).
