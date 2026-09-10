# P1 U4 — Construct and deliver the routed MCU (run `mcu-20260910-a`)

Parent plan: `docs/plans/2026-09-10-1322-feat-atopile-mcu-flow-plan.md` (U4).
Milestone: `docs/plans/2026-09-10-1322-feat-mcu-harness-milestone-plan.md`.
Run directory: `harness-lab/runs/mcu-20260910-a/` (per dispatch; not `zapote/`).

**Milestone status: OPEN.** The live model transport could not be established
(Zen free-usage limit), so there is no autonomous construction result. An
operator-assisted, apparatus-only construction reaches a block-judge pass and
clean native DRC, but fails plan-required schematic parity. Details below.

## 1. Source identity and candidate regeneration

The candidate was regenerated fresh through the U2 strict bridge
(`run_block.generate_candidate`, `confirm=True`, `TEMPER_BLOCK_GENERATE=1`) —
never copied from the abandoned `zapote/runs/...` tree.

| Artifact | Identity |
|---|---|
| Entry | `mcu.ato:McuCandidate` |
| Atopile | `0.2.69` (pinned, `uv tool run --offline`) |
| KiCad-cli / pcbnew | `10.0.4` |
| Netlist | `90d04ba4af410f765ab3586091385c3aef78b202616268c36653fe6ccab731a5` |
| BOM (CSV) | `09d804ac1ad3c9d98cd37117d57323ef51a001eff40ac5d019339ce1d15f7dff` |
| Resolved export | `551ebb57c0f8029078dcb21831dc7ed76f82ee339f9de5286f646b77e8c5d495` |
| P3 target context | `db3e07b6fcb70ccedc4791a55d32ad37ae3c6177c6a4de82dee0c04206241c79` |

Per-file sha256 census (committed compact index):
`harness-lab/runs/mcu-20260910-a/INDEX.json` (autonomous) and
`INDEX-assisted.json` (assisted). The regenerated `mcu_candidate.kicad_pcb` is
**byte-identical** to the abandoned prior attempt
(`f850c544c9b8224c9474ac8592331e404f9c453cee7ec2ab1b7dfc2355fde2a0`); the only
netlist differences are temporary workspace paths.

## 2. Frozen P2 memory selection (before construction)

Frozen against the MCU task context and the compiled-source identities, then
materialized through `artifacts.Store` and delivered into the live sandboxed
`workspace.Workspace` before the first board call:

| Field | Value |
|---|---|
| Selected IDs | `buck-mem-001` … `buck-mem-005` (all 5 accepted, 0 exclusions) |
| Selection sha256 | `c4c31c10710dd85a96c2e07c6083f818e959a0a7394953d039bac32f24bce1e5` |
| Materialized revision | `cb216b8a210e30bc29cbeb86eac35fb20fa28e1c07d17d3cd13688ecca2c4fb7` |
| Notes / skills sha | `83da8094…586b` / `4283bde9…22e` |
| `model_delivery_proven` | **true** |
| Receipt / capture | `trial-assisted/memory-selection.json`, `trial-assisted/model-input.json` |

Delivery is notes-only (the seed package ships no executable helpers);
`delivery.acknowledged=true` and the retained model-input capture is the
delivery proof.

## 3. Live transport attempt (KTD7/KTD8)

One recorded live attempt: `harness-lab/runs/mcu-20260910-a/live-01/`.

- Model: `opencode/muse-spark-1.3-contributor-free` (single declared model).
- Runtime: OpenCode `1.18.30`, isolated XDG env, local relay retaining full
  wire request/status/response evidence; telemetry disabled.
- Tool catalog over the wire: `pcb_check`, `pcb_execute`, `pcb_inspect`,
  `pcb_place`, `pcb_replace_copper`, `pcb_request_generation`.
- Outcome: **`transport_blocked`** — upstream `opencode.ai/zen/v1/responses`
  returned **HTTP 429 `FreeUsageLimitError`** with `retry-after: 7726` s; the
  relay blocked the retry. Zero model tool calls, zero construction.

Two earlier driver invocations were discarded as apparatus smokes (a
pre-handshake delivery design, then an agent `tools: false` defect); the
recorded attempt above is the corrected driver. No autonomous result is
fabricated.

## 4. Development attempt (apparatus-only, non-live)

Because live transport was unavailable, a bounded scripted construction ran
through the same `run_block.BlockSession` admitted operations and the same
200-mutation / 1200-second budget, labelled **apparatus-only / non-live** in
every artifact. The script is run-local (`construct.py`), not a harness
capability; it is an explicit operator placement plus an MST + grid-A\* graph
route, not a placer/router added to the harness.

- **Autonomous (unassisted candidate):** FAIL — 33 `silk_overlap` findings.
  The U2 generator emitted bare `(property "Reference" …)` entries; kiutils
  1.4.8 drops the field geometry, so KiCad places every reference field over
  its own pads/silk. Those 34 (staging) violations are intrinsic and cannot be
  removed by any admitted `place`/`replace_copper` operation. Routing itself
  succeeded (0 unconnected, 0 clearance).
  Board `08df1890f205d462a902b8708b640dc4380dbc6e6d7d2f10339d2fd4ff8e7289`.
- **Assisted (operator generator fix):** the reference/value geometry was
  restored on `F.Fab` (hidden) in the candidate path of
  `scripts/gen_pcb_skeleton.py`. Construction then reached
  **block-judge pass**, 0 findings, 16 committed actions.
  Board `f9087f4c4500415f897b3057c5ac0c6beb8828d177be469342199d99baa25dd2`.

Two P1 U3 adapter defects were surfaced and fixed (recorded as interventions):

1. `block_native.copper_layer_id` treated KiCad **file ordinals** as pcbnew
   layer ids (`GetLayerName(3)` is `B.Mask`, not `In3.Cu`). Fixed to resolve by
   name via `board.GetLayerID()`.
2. Adding a zone makes the headless `measure` adapter segfault on teardown
   (exit 139 with a complete JSON body). Ground is therefore routed with
   explicit F.Cu copper instead of a zone; the adapter was not weakened.

## 5. Independent final native checks (3× each)

`native_check.py` runs, three times, native measurement + `kicad-cli pcb drc
--all-track-errors --schematic-parity --severity-all` + `kicad-cli sch erc
--severity-all` + the block Rust judge.

| Board | DRC viol. | Unconnected | Schematic parity | ERC | Judge (with parity) |
|---|---|---|---|---|---|
| Autonomous | 33 (silk) | 0 | 67 | 19 warn | fail (100) |
| Assisted | 0 | 0 | 67 | 19 warn | fail (67) |

Stable across all three runs (`stable_across_runs: true`), identical board and
protected hashes. Protected state `1dba55c80a13703d3e1a5fcba8d236576b3adc2bf082e1a62434625a9822b941`
matches the sealed contract (no `protected_state_changed`).

**Parity gap:** the block host does not pass `--schematic-parity`; the host
judge (incremental/feedback path) therefore reports the assisted board as
`pass`, but the plan's verification contract requires parity, and the
parity-inclusive judge fails with 67 findings (board `Value "?"` vs schematic
value; board net `vcc` vs schematic `/MCU/vcc`). ERC: 19 warnings
(10 `lib_symbol_issues`, 9 `endpoint_off_grid`), no errors.

MCU layout constraints: within outline, outside the antenna keepout, all ten
instances inside the reserved `mcu_block` region, `vcc`/`gnd` obligations
satisfied by measured native clusters; protected state unchanged.

## 6. Handoff

Exact identities for P3/P2: `harness-lab/runs/mcu-20260910-a/handoff.json`.

Accepted package path (P3 contract): `pcb/blocks/mcu/`, state
**`assisted-pending-schematic-parity`** (marker
`pcb/blocks/mcu/ASSISTED-PACKAGE.json`). It contains the assisted routed board,
source manifest, schematics, libraries, rules, and build evidence; it passes
the block judge and native DRC but is not fully verified under the parity
requirement and is not an autonomous model result.

## 7. Outstanding gaps

1. Live model delivery blocked (Zen 429) — milestone cannot close without it.
2. U2 generator reference/value property geometry (silk) — fixed assisted, not
   in the autonomous path.
3. Schematic parity 67 findings — unaddressed.
4. ERC warnings (library table / grid) — unaddressed.
5. Zone on the headless measure path segfaults (ground routed explicitly).
