# P1 U4 — MCU candidate with schematic parity and the real switch (run `mcu-20260910-b`)

Parent plan: `docs/plans/2026-09-10-1322-feat-atopile-mcu-flow-plan.md` (U4).
Predecessor: `harness-lab/runs/mcu-20260910-a/` (retained failure evidence).
Run directory: `harness-lab/runs/mcu-20260910-b/`.

**Milestone status: OPEN.** The live model transport remains blocked (Zen
free-usage limit, retained in the predecessor run). This run is an
**apparatus-only / non-live** construction that clears the two blockers found
in run `a`: schematic parity and the placeholder SW1/SW2 footprint. It passes
the block judge and the full native check.

## 1. Blockers fixed

| Blocker | Cause | Fix |
|---|---|---|
| Schematic parity 67 | board `Value "?"` vs schematic MPN; board net `vcc` vs hierarchical `/MCU/vcc` | footprint `Value` from `default.csv`; flat candidate schematic with unscoped global labels |
| SW1/SW2 placeholder | `Resistor_SMD:R_0603_1608Metric` stood in for the switch | working-tree `Button_Switch_SMD:SW_SPST_EVQP7A` (Panasonic EVQ-P7A01P), treated as fixed input |

`build_strict_pin_map` now emits one entry per unique `(reference, pin)`. The
EVQP7A footprint exposes pads `1,1,2,2`; the old one-entry-per-physical-pad
emission failed the design-bundle strict gate as `duplicate_map`. The Rust
gate already supports repeated same-number pads and still rejects a genuine
split pad (`split_pad`); it was not weakened.

## 2. Source identity

| Artifact | Identity |
|---|---|
| Entry | `mcu.ato:McuCandidate` |
| Atopile | `0.2.69` (pinned, `uv tool run --offline`) |
| KiCad-cli / pcbnew | `10.0.4` |
| Candidate board | `1caacb89e69bd6c5259371cb2d63d8c153dca510e8b4f2bfcaaf0e94ca16305b` |
| Routed board | `1e58e2d248d9708d1fc4e8fd26f64bbf5c74b1af07e298c972cc3ec33cab4b35` |
| Source manifest | `6a52b7a1e6f1248137151d3192e46d4677f9c547fade2ede7956c7f3e042e93f` |
| P3 target context | `db3e07b6fcb70ccedc4791a55d32ad37ae3c6177c6a4de82dee0c04206241c79` |

Per-file candidate census: `INDEX-assisted.json`. Full identities:
`handoff.json`.

## 3. Apparatus-only construction (non-live)

`construct.py` places the ten instances and routes copper through the same
admitted `run_block.BlockSession` operations under the 200-mutation /
1200-second budget. Two apparatus corrections were required by the real
switch:

* the switches sit clear of the 0603 parts (SW1 `y=56`, SW2 `y=58`);
* every physical pad of a repeated-number contact is routed to the contact's
  shared via (the old last-wins pad dict dropped one terminal per contact and
  left it open).

Result: **block judge pass, 0 findings, 16 committed actions**, board
`1e58e2d2…`.

## 4. Native check (3×, kicad-cli 10.0.4)

`native_check.py` runs native measurement + `kicad-cli pcb drc
--all-track-errors --schematic-parity --severity-all` + `kicad-cli sch erc
--severity-all` + the block Rust judge.

| Metric | Run a (assisted) | Run b |
|---|---|---|
| DRC violations | 0 | **0** |
| DRC unconnected | 0 | **0** |
| Schematic parity | 67 | **0** |
| Block judge | fail (67) | **pass (0)** |
| ERC | 19 warn | 52 warn (no errors) |

Stable across all three runs (`stable_across_runs: true`), identical board and
protected hashes.

The ERC increase is 33 new `isolated_pin_label` warnings: the candidate
schematic now labels every compiled single-node net so parity can agree. They
are warnings, not DRC errors.

## 5. Handoff

Exact identities: `harness-lab/runs/mcu-20260910-b/handoff.json`.

Accepted package: `pcb/blocks/mcu/`, state
**`assisted-verified-apparatus-only`** (marker
`pcb/blocks/mcu/ASSISTED-PACKAGE.json`). It contains the routed board, the
flat candidate schematic, source manifest, libraries, rules, and build
evidence.

## 6. Outstanding gaps

1. Live model delivery blocked (Zen 429) — milestone cannot close without it.
2. ERC warnings (library table / grid / isolated single-node labels); no errors.
3. The `elec/src/components.ato` switch-footprint fix is an uncommitted,
   concurrent working-tree change authored by another session.
4. `harness-lab/block_native.py::_electrical_census` collapses repeated
   same-number pads for the block judge's per-pin census; the design-bundle
   strict gate was not modified.
