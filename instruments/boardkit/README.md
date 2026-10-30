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
| `jlc.parts` | JLC assembly-library snapshot (price tiers, stock, library class, attrition, minimum) by curl POST, the schema `jlc.order` callers read | curl |
| `jlc.order` | one assembly fee model (Economic, Standard, hand fit), `tier_price`, `buy_qty`, `is_extended`, X-ray tiers | stdlib |
| `jlc.models_3d` | exact-part STEP models from EasyEDA placed in the KiCad footprint frame | OCP (CAD env) |
| `kicad` | lazily imported pcbnew: `load_board`, `clear_silk_circles`, `pad_table`, `footprint_pads`, `edge_clearance`, `via_in_pad(_audit)`, `joint_counts`, `MODEL_SWAP` / `apply_model_swap` | KiCad's Python |
| `fab` | fab-house limits as a separate KiCad DRC pass: profile -> `.kicad_dru` rules, board copy without local clearances, a self-test board on which every rule must fire, findings attributed by rule name (`boardkit-fab-check`) | kicad-cli, KiCad's Python for `run` |
| `jlc/data/fab-profiles` | JLC `jlcpcb-{2,4}layer-{1,2}oz.json` (schema `zapote.fab-profile.v1`): each limit with JLC's own sentence, a verbatim substring of `jlc/data/jlc-capabilities-2026-10-29.txt` (tested) | data |
| `kicad_scripts` | `fab_board_copy.py`, `fab_selftest_board.py`, run under KiCad's Python by `fab.run` | KiCad's Python |
| `cli` | `boardkit-predrc`, `boardkit-gerber-check`, `boardkit-edge-clearance`, `boardkit-fab-check` | as the modules |

`model`, `craft`, `kicad`, `jlc`, `jlc.easyeda`, `jlc.order` and `jlc.placement` are Python 3.9 compatible and
import under KiCad's bundled Python, which has neither shapely nor numpy.  Nothing is imported by the package
`__init__`.

## Calling it

From KiCad's Python (or any script in the repo), put the source directory on the path:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(REPO / "instruments" / "boardkit" / "src"))
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

## From zapote

`zapote/` (the cooker boards' Rust validation workspace) keeps its engineering rules in Rust and was surveyed
for reuse on 2026-10-29.  Taken: the fab profiles (re-read from JLC's page the same day: the 2-layer 1 oz PTH ring
minimum is now 0.18 mm, and there was no 2-layer 1 oz profile) and the fab pass (`zapote-drc` `fab_rules.rs`,
`zapote-harness` `fab_check.rs`, `tools/fab_board_copy.py`, `tools/make_fab_selftest_board.py`), ported to
Python with track width, rings, drill sizes, hole-to-hole and copper-to-edge rules added and self-tested.
The profiles keep zapote's schema, so `zapote-check --profile` can read them.  Not taken: zapote's DRC has
no acute-angle, teardrop, sliver or via-in-pad checks (boardkit's own), its current check is IPC-2221 (boardkit's
`craft` uses IPC-2152), and the prebuilt `zapote-check` binary resolves its extractor through a deleted
worktree path.  `zapote/tools/silk_legend_minimums.py` (raises silk text to a profile's minimums) is a candidate
once a board needs it.

Board results, 2026-10-29: LCR Rev F (`jlcpcb-4layer-1oz`) and RB1 (`jlcpcb-2layer-1oz`), see the boards'
validation records.

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
| `calkit/order_estimate.py` | `jlc.order` (was a copy of the fee constants); `order-estimate-5.json` unchanged |
| `manufacturing/prices/fetch_jlc_parts.py`, `calkit/fetch_jlc_parts.py` | `jlc.parts.snapshot` (calkit with `extra=True`); a live fetch matches the committed snapshots' schema, key order and source string |

Wireless thermometer RB1, `instruments/wireless-thermometer/proto/revisions/rb1-ads-readout` (migrated on branch
`infra/rb1-boardkit`; `checks/dfm.json`, `checks/placement-preview.svg`, `fab/bom-jlc.csv`, `fab/cpl-jlc.csv`,
`fab/placement-audit.json` and both order-estimate texts regenerate byte-identical):

| RB1 file | now |
|---|---|
| `gerber_read.py`, `sources/jlc-capabilities-excerpts.txt` | deleted: `temper_boardkit.gerber`, `jlc/data/` (the excerpt was identical) |
| `dfm_checks.py` sections 1-3 | `gerber.GerberSet`, `Copper`, `connectivity`, `outline`, `drill_check`, `paste_check`, `mask_check`, `silk_texts`, `silk_check`; `jlc.easyeda.pads_about_head`, `jlc.placement`. RB1 keeps its inputs (drill sets from `pcb/layout.json`, THT pad names, pin-map inversion) and its `dfm.json` key names |
| `dfm_checks.py` sections 4-6 | unchanged: land patterns, I2C rise time, mux settling are RB1 physics |
| `fab.py` | `jlc.easyeda.record` / `easyeda_pads` / `fit_cpl_offset` |
| `order_estimate.py` | `jlc.order` constants, `buy_qty`, `tier_price`, `is_extended`; `--fetch` is `jlc.parts.snapshot`. RB1's total stays setup + stencil + extended fees + joints (no placement confirmation; no leadless part, so no X-ray) |

Not migrated: frozen snapshots under `r18/` and the order folders, and R24 (live in another session; its
`jlc_stock` tool is a candidate for `jlc.parts`).

## Tests

`tests/`: the 28 ported craft cases, the model helpers, and a passing and a failing case for each pre-DRC,
Gerber and JLC check on tiny synthetic boards and Gerbers (`fixtures.py`, built in the tests).
