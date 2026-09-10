# MCU harness milestone report (Coordinator U2)

Plan: `docs/plans/2026-09-10-1322-feat-mcu-harness-milestone-plan.md`
Child plans: `2026-09-10-1322-feat-atopile-mcu-flow-plan.md` (P1),
`2026-09-10-1322-feat-engineering-agent-memory-plan.md` (P2),
`2026-09-10-1322-feat-buck-mcu-composition-plan.md` (P3).
Run: `harness-lab/runs/mcu-20260910-a` (`mcu-20260910-a`).

**Milestone status: INCOMPLETE.** The coordinator accepts the owner contracts
(U1) and joins the delivered evidence (this report), but two plan-required
child deliverables are blocked or unverified and the milestone cannot be
closed: **(a) live model delivery/construction** never ran (transport blocked,
HTTP 429 `FreeUsageLimitError`), and **(b) schematic parity** fails on both the
MCU package (67 findings) and the assembly (98 findings). The delivered
candidate is labelled **`apparatus-only-assisted`** in every artifact: a
scripted, non-live construction plus an operator generator fix. It is **not** a
qualified cooker, not an autonomous model result, and not evidence of
electrical performance or hardware validation.

Every number and identity below was re-verified against the working tree on
2026-09-10; sha256 values are full digests unless a truncated label is marked
`…`. The production board `pcb/temper.kicad_pcb` was never written (digest
`00a27419…ac4d9`, exact).

---

## 1. Contract acceptance (U1)

Four contracts were accepted and checked for cross-references naming one
current source and one board context.

### 1.1 Typed source identity contract (P1) — ACCEPTED

| Artifact | Identity |
|---|---|
| Wrapper entry | `mcu.ato:McuCandidate` (Atopile `0.2.69` pinned, `--offline`) |
| Wrapper source | `harness-lab/blocks/mcu/mcu.ato` `a3844663a915ab7f4120b223536b70393e78c9eb7b61101b1f22490c935acd83` |
| Identity inventory | `harness-lab/blocks/mcu/identity-inventory.json` (schema `temper.mcu-identity.v1`) `c7b539541fca8a7a754ed7e5be5f6b7ccd3926370e777cbc9f0d5d29ef30df54` |
| Candidate manifest | `pcb/blocks/mcu/source-manifest.json` (schema `temper.mcu-candidate.v1`) `10cbe6db7d234e263fa6399c57cc1f8dac3ae59937abcbad20dc3505f093d7a6` |
| Compact index (assisted) | `harness-lab/runs/mcu-20260910-a/INDEX-assisted.json` (schema `temper.mcu-run-index.v1`) |
| Build evidence | netlist `90d04ba4af410f765ab3586091385c3aef78b202616268c36653fe6ccab731a5`, BOM `09d804ac1ad3c9d98cd37117d57323ef51a001eff40ac5d019339ce1d15f7dff`, resolved export `38916ebd45bfb1244432809ff145eb2ea0e2195d317286350c7ffe2f1039cd6c` |

Accepted enforcement: identity is the **canonical instance path**
(`mcu.*`), never refdes; `pin == pad` is exact via
`block_source.build_strict_pin_map` gated by the Rust bridge
`candidate_validate_pin_map`; no positional fallback; explicitly unconnected
pads are recorded (accepted package: 57 strict entries, 0 unconnected);
`candidate_convert_bridge` owns part identity (MPN from resolved-attr + CSV,
never netlist `value` `?`/`libsource` aliases); `candidate_check_freshness`
rejects a stale build and `candidate_check_net_admission` rejects empty nets.
Producer: `harness-lab/block_source.py::assemble_mcu_candidate`; Rust kernels
in `packages/temper-design-bundle` (`lib.rs`, `validation.rs`, `identity.rs`,
`atopile.rs`).

### 1.2 Target-board context contract (P3) — ACCEPTED

| Artifact | Identity |
|---|---|
| `pcb/blocks/control-assembly/target-context.json` (schema `control-assembly.target-context.v1`) | `db3e07b6fcb70ccedc4791a55d32ad37ae3c6177c6a4de82dee0c04206241c79` |
| `pcb/blocks/control-assembly/interfaces.json` (schema `control-assembly.interfaces.v1`) | `5376544525aade8fea7722cbf1f55f94f322164350e3f77d693eeb84377fa1d8` |
| `pcb/temper.kicad_pcb` (read-only target) | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |

Accepted: outline `8.0/20.0–172.0/254.0 mm`, six copper layers in physical
stackup order `F.Cu / In3.Cu / In1.Cu / In2.Cu / In4.Cu / B.Cu`, 159 native
nets, 168 footprints, ENIG 1.6 mm. Ordinal layer IDs are explicitly
**not** physical order. The antenna keepout is marked `"assumed": true`
(no native antenna keepout exists). Internal required connections and future
obligations are separated.

### 1.3 Memory applicability context (P2) — ACCEPTED

| Artifact | Identity |
|---|---|
| Catalog | `harness-lab/memory/catalog.json` (catalog v1; module schema `memory/v1`) `124d91c59ba4c98727c48f5bff40172d4a05ca7bf273c8c0fe192a6720aba058` |
| Entries | `buck-mem-001…005` content hashes `feb5a98f…`, `eea09592…`, `e50a3232…`, `12c3eacc…`, `9908a4ac…` |
| Selection receipt (accepted/live-path payload) | `trial-assisted/memory-selection.json` selection `c4c31c10710dd85a96c2e07c6083f818e959a0a7394953d039bac32f24bce1e5` |
| Materialized revision | `cb216b8a210e30bc29cbeb86eac35fb20fa28e1c07d17d3cd13688ecca2c4fb7` (notes `83da8094…`, skills `4283bde9…`) |

Accepted: all five entries are `expert-curated`, `board_specific=false`;
`buck-mem-005` alone declares `exact_fact_transfer =
"only-on-matching-source-identity"` and is recorded as re-checkable, not
assumed. Selection matches **declared capabilities + source identities**, not
semantic similarity. `memory.p1_interface()` defines the task-context keys
(`task_capabilities`, `source_identities`). All five evidence hashes were
re-verified against the current evidence files and match exactly.

### 1.4 Output manifest contract (P3/P1) — ACCEPTED

| Artifact | Schema / identity |
|---|---|
| P1 U4 handoff | `harness-lab/runs/mcu-20260910-a/handoff.json` (`temper.mcu-u4-handoff.v1`) |
| Accepted MCU package | `pcb/blocks/mcu/` marker `ASSISTED-PACKAGE.json` (`temper.mcu-package-status.v1`), state `assisted-pending-schematic-parity` |
| P3 candidate index | `pcb/blocks/control-assembly/INDEX.md`, `assembly-candidate/candidate-index.json` (`control-assembly.candidate-index.v1`) |
| P3 binding | `verification/apparatus-only/candidate-binding.json` (`control-assembly.candidate-binding.v1`) |
| P3 input contract | `pcb/blocks/control-assembly/mcu-input-contract.json` (schema `control-assembly.mcu-input-contract.v1`) |

### 1.5 Cross-context consistency — ACCEPTED with one reconciled discrepancy

The single target-context digest `db3e07b6…` is named consistently by the P1
handoff (`context.target_context_sha256`), `INDEX-assisted.json`
(`target_context_sha256`), both apparatus result files
(`memory.source_identities["p3.target-context.json"]`), and the P1 candidate
manifest (`target_context.sha256`; `run_block.build_task_contract` re-checks
it and refuses on drift). The source wrapper/inventory pair
(`a3844663…` / `c7b53954…`) is shared by both apparatus attempts. The assembly
index names the accepted package (`pcb/blocks/mcu/`, board `f9087f4c…`) as its
MCU source.

**Reconciled discrepancy:** `docs/hardware/control-assembly/memory-report.md`
(P2) quoted a selection hash `bd3c56ff…` and a materialized size of 8243 bytes
that do not appear in any retained receipt and match no artifact. The
authoritative selection receipt is `c4c31c10…` (agrees with `handoff.json`,
`RUN.md`, `assisted-result.json`, and `trial-assisted/memory-selection.json`);
the materialized notes are 8981 bytes. The report has been reconciled to the
receipt (see §8). The **unassisted** attempt used a different content-bound
selection hash (`7073c176…`) because its task context carried the pre-fix
source identities (`b7e10748…` manifest, `f850c544…` board). Both select the
same five entry bytes.

**Missing inputs with named owners** (from `target-context.json.pending_inputs`
and the integration report): P1 combined source + MCU geometry (delivered),
P2 memory closeout (delivered, live remainder blocked on P1), P1
`BlockSession` profile for the combined assembly (P1), P1 vendorer for
`Inductor_SMD:L_Bourns_SRP1265A` (P1), scratch full-board overlay (blocked on
the live turn), `en`/`io0`/`scl`/`sda` MCU-local completion (next assembly
owner).

### 1.6 Documentation index consistency

`harness-lab/blocks/mcu/README.md` and the `docs/hardware/control-assembly/`
index name the same source/board context and the same accepted package state.
The coordinator added this report to `docs/hardware/control-assembly/README.md`
and to `harness-lab/blocks/mcu/README.md`; no owner contract was changed.

---

## 2. Generated source artifacts and submitted boards

Source-derived boards actually submitted to native checks (all in the
worktree, listed by full sha256):

| Board | sha256 | Meaning |
|---|---|---|
| MCU candidate, unassisted | `f850c544c9b8224c9474ac8592331e404f9c453cee7ec2ab1b7dfc2355fde2a0` | pre-generator-fix starting board |
| MCU candidate, assisted | `e60e651def16a1ca358d65c54c79369b879e9b2ae70e10f4ff0672be5400fde5` | accepted starting board |
| MCU routed, unassisted | `08df1890f205d462a902b8708b640dc4380dbc6e6d7d2f10339d2fd4ff8e7289` | final, judge fail |
| MCU routed, assisted | `f9087f4c4500415f897b3057c5ac0c6beb8828d177be469342199d99baa25dd2` | accepted package board |
| Assembly candidate (unrouted) | `bde0b0055397e06c72cb8c6f5dbe4e6f30474af132616ea60eb4502c24d1649d` | U2 generated |
| Assembly routed | `09c6e46d6c35ad954df1989897945e018b4a80aa15d71ce8470a57c813e4e7c4` | U3 apparatus-only routed |

Combined wrapper build (`source/combined-bridge.json`, schema
`control-assembly.combined-bridge.v1`): netlist
`05c0fbb0ed2bdeaff4c6368019126dbeba9d5dd4cf458a4f1f71f89774237aa5`, BOM
`45d0ddeda89b83b53d9116e1c6cd8fdf2158799c081ef70b5d886ea19833a403`, 19
functional instances mapped by canonical path (9 `buck.*` + 10 `mcu.*`).

---

## 3. Attempts, interventions, rejected edits, incomplete results

**Every attempt is labelled non-live.** The only live attempt is #1; it did
not execute.

| # | Attempt | Kind | Result | Identity |
|---|---|---|---|---|
| 1 | `live-01` (`opencode/muse-spark-1.3-contributor-free`) | live | **transport_blocked**, 0 tool calls, HTTP 429, retry-after ~7726 s | `handoff.json → live_transport`; `live-01/` wire evidence |
| 2 | discarded driver smokes (pre-handshake delivery design; agent `tools:false`) | apparatus | discarded, retained in `runs/` | `trial-dry/`, `trial-probe*` |
| 3 | unassisted scripted construction | apparatus | **fail** (33 DRC: `silk_overlap`/`silk_over_copper`; judge 100 incl. parity) | board `08df1890…`, `autonomous-result.json` |
| 4 | assisted scripted construction | apparatus | **pass host judge** (0 findings); 0 DRC; 19 ERC warnings; 67 parity | board `f9087f4c…`, `assisted-result.json` |
| 5 | P3 composition + routing | apparatus | **routing pass** (0 introduced DRC/ERC); `power_width` fail; parity 98; overlay pending | `verification/apparatus-only/summary.json` |

### Interventions (all recorded, none hidden)

1. **Generator property-geometry fix (operator):**
   `scripts/gen_pcb_skeleton.py::_restore_candidate_property_geometry` was
   added (now committed) because the U2 generator re-emitted bare
   `(property "Reference"/"Value")` entries and kiutils 1.4.8 drops their
   geometry, placing every reference field over its own pads/silk. The 34
   staging findings are intrinsic and not removable by any admitted
   `place`/`replace_copper` operation. This makes attempt #4 an
   **assisted** result.
2. **Adapter fix (P1):** `harness-lab/block_native.py::copper_layer_id`
   resolved KiCad file ordinals as pcbnew layer ids (`GetLayerName(3)` is
   `B.Mask`, not `In3.Cu`); fixed to resolve by `board.GetLayerID()`.
3. **P3 MCU placement revision:** nine staged parts at `y = 31` inside the
   assumed antenna keepout were moved to `y = 35` (placement only; source
   identity/footprint/orientation preserved) —
   `assembly-candidate/mcu-placement-revision.json`.
4. **P3 footprint fallback:** `Inductor_SMD:L_Bourns_SRP1265A` is in neither
   KiCad stock nor `pcb/libs`; P3 staged it from the prototype library. This
   is a **P1 vendor gap** (`block_source._stock_footprint_source`), named as a
   requested P1 fix, not silently absorbed.

### Rejected / impossible edits

- Intrinsic U2 silk findings were rejected as fixable by the admitted board
  operations; the fix was made in the generator (assisted), not by a
  compensating skill.
- A **zone** on the headless measure path makes KiCad segfault on teardown
  (exit 139 with a complete JSON body); ground was routed with explicit F.Cu
  copper. The adapter was not weakened.
- Whole-interface Atopile join (`buck.power_out ~ mcu.power`) is rejected by
  Atopile (two definitions of `voltage`); the wrapper uses the signal-level
  join and keeps each module's declaration.
- `run_block.BlockSession` was **not** instantiated for the combined assembly:
  its task contract (`REQUIRED_INTERNAL_NETS = ("vcc","gnd")`, MCU staging
  census) does not fit the 19-instance combined netlist
  (`buck-vcc`/`buck-vcc-1`). A P1-owned profile change is required; P3 did not
  edit P1 code.

### Incomplete results

Live delivery/construction; schematic parity (67 MCU / 98 assembly);
scratch full-board overlay / cross-view comparison; `power_width` (19
inherited 0.3 mm segments on `buck-vcc-1`/`fb`/`boot`, below the 0.6 mm
assembly floor); MCU-local `en`/`io0`/`scl`/`sda` (7 unconnected DRC items).

---

## 4. Memory selection, delivery, and use (P2 U4 + P1 integration)

- **Selected:** all five `buck-mem-001…005`, zero exclusions, deterministic
  `(priority, id)` order. Receipt selection `c4c31c10…`.
- **Delivered:** materialized through `artifacts.Store` revision
  `cb216b8a…`, loaded with `Workspace.apply_revision`; a retained
  `model-input.json` capture exists and
  `handoff.json.memory.model_delivery_proven = true`, `delivery_acknowledged
  = true` for the apparatus attempt (`mcu-apparatus-01`). This is delivery to
  the **retained model-input payload and workspace**, not to a live model.
- **Used:** none. The seed package is notes-only; `helper_calls: []`; no
  executable helper executed, so no use is claimed. Reading notes is never
  recorded as causing a decision.
- **Proposed / promoted:** none. Automatic extraction is a post-attempt step;
  there is no live attempt trace to extract from, and no proposal was
  fabricated.
- **Indeterminate by rule:** the P2 plan says a missing live model-input
  delivery makes the memory-reuse result indeterminate and prevents
  milestone closeout; a control cannot stand in for it. That condition holds
  here (the only live attempt produced 0 tool calls). This is a **second
  independent reason** the milestone cannot close.

---

## 5. Native validation (confirmed, not re-run)

Expensive live/model runs were not repeated. The committed native receipts
were re-read and the child suites re-run (see §7).

### 5.1 P1 MCU package (3 runs each, stable, identical board+protected hashes)

| Board | DRC violations | Unconnected | Parity | ERC | Judge |
|---|---|---|---|---|---|
| unassisted `08df1890…` | 33 | 0 | 67 | 19 warn | fail (100) |
| assisted `f9087f4c…` | 0 | 0 | 67 | 19 warn | fail (67) |

Protected state `1dba55c8…` matches the sealed contract on all runs.
`native_check.py` invokes `kicad-cli 10.0.4` DRC with
`--all-track-errors --schematic-parity --severity-all` and ERC
`--severity-all`, plus the block Rust judge. **Note the discrepancy:** the
block *host* judge omits `--schematic-parity` and therefore reports the
assisted board `pass`; the plan's parity-inclusive judge fails. The package is
accepted only as `assisted-pending-schematic-parity`.

### 5.2 P3 assembly (apparatus-only)

| Set | Baseline | Routed | Introduced | Resolved | Persistent |
|---|---|---|---|---|---|
| DRC (all-track + parity + all-severity) | 126 | 113 | **0** | 13 | 113 |
| ERC (all-severity, 0 errors) | 55 | 55 | **0** | 0 | 55 |
| Schematic parity (subset) | 98 | 98 | **0** | 0 | 98 |
| DRC unconnected | 20 | 7 | **0** | 13 | 7 |

Checks (`summary.json`, hash `e636d96c…`): `required_connectivity` pass,
`inter_block` pass, `antenna_keepout` pass, `no_placeholder_leftover` pass,
`production_digest` pass (exact), `power_width` **fail**.
`candidate-binding.json` binds source board `bde0b005…`, routed board
`09c6e46d…`, summary `e636d96c…`, production `00a27419…`.

---

## 6. Clean-directory replay of the retained source-to-board path (U3)

Feasible and **run**. `harness-lab/block_source.py --output-dir
<fresh temp dir>` recompiled `mcu.ato:McuCandidate` in a fresh offline Atopile
`0.2.69` workspace and regenerated the candidate.

Result: the generated **board, both schematics, `rules.json`,
`schematic_layout.json`, `fp-lib-table`, and the vendored library bytes are
byte-identical** to the retained assisted candidate:

- `mcu_candidate.kicad_pcb` → `e60e651d…` (exact)
- `mcu.kicad_sch` → `4cee6d79…` (exact)
- `mcu_candidate.kicad_sch` → `f5a1b369…` (exact)
- `rules.json` → `0ac4b0c3…`, `schematic_layout.json` → `a4601725…`,
  `fp-lib-table` → `53096730…` (exact)

The only differences are build-run ephemera: the netlist (`6b474572…` vs
`90d04ba4…`, temporary workspace paths), the resolved export
(`c449dd55…` vs `38916ebd…`), and the Atopile stdout digest. A semantic
comparison of the two `source-manifest.json` files shows `strict_map`,
`converted`, `staging`, `board`, `schematic`, and `target_context` **identical**.
The replay reproduces construction and checks, not the model's stochastic
decisions.

---

## 7. Tests and repository gates run

| Check | Result |
|---|---|
| MCU/assembly/memory pytest (`test_block_composition`, `test_control_assembly`, `test_memory`, `test_memory_integration`) | **64 passed** |
| P1 source bridge pytest (`test_block_source`) | **27 passed** (128.6 s; builds Atopile offline) |
| P1 judge pytest (`test_block_boundary`) | **15 passed** |
| P1 runner pytest (`test_block_runner`) | **13 passed** |
| harness-lab `cargo test --locked` | **pass** (56 + 3 + 8 tests) |
| harness-lab `cargo clippy -D warnings` | **pass** |
| harness-lab `cargo fmt --check` | **pass** |
| harness-lab `python -m unittest discover -s . -p 'test_*.py'` | **257 passed** (264.1 s) |
| Import boundary `scripts/import_linter_gate.py` | **PASSED** (5 kept, 0 broken) — requires `PYTHONPATH=packages/temper-placer/src`; the bare `uv run` form errors with "Could not find package 'temper_placer'", a tooling-path issue, not a violation |
| `scripts/check_stale_extensions.py` | `temper-design-bundle` and `temper-geometry` **fresh**; 6 unrelated placer accelerators missing (not built in this worktree) |
| `make regen-check` | **FAIL** — pre-existing, see below |

**Pre-existing failures (not introduced by this report; all trace to the
uncommitted P1/P2/P3 additions):**

1. `ruff check --isolated --select E4,E7,E9,F,I` → 2 × `I001` in
   `harness-lab/block_native.py` and `harness-lab/compose_assembly.py`.
2. `ruff format --check` → 17 files would be reformatted.
3. `make regen-check`:
   - `DRIFT gen_repo_state.py` — README package/plan counts behind new files.
   - `DRIFT gen_wasm_test_registry.py [temper-design-bundle]` — new Rust kernels.
   - `FAIL unwired-kernel` — `candidate_check_freshness`,
     `candidate_check_net_admission`, `candidate_convert_bridge`,
     `candidate_validate_pin_map` are not Rust-side wired.

The coordinator did **not** edit P1/P2/P3 feature files to silence these; they
are reported for the owner. Oracle hashes (163/163) and hash-order checks pass.

**Working-tree caveat (must be resolved before landing):** the branch is not
clean. Only the compact P1 run index/handoff, the `pcb/blocks/mcu/` package,
`memory.py`, `src/memory.rs`, and the P3 composition scripts are committed;
the working tree additionally carries **uncommitted** P1/P2/P3 source and
evidence (`harness-lab/block_source.py`, `run_block.py`, `blocks/`, `memory/`,
`src/block.rs`, `test_block_*.py`, `pcb/blocks/control-assembly/mcu-input-contract.json`,
`elec/src/modules.ato`, `scripts/gen_schematics.py`, `packages/temper-design-bundle/src/*`,
and the `interfaces.json`/`target-context.json` revisions), plus unrelated
buck-prototype work. All results above were produced from that working tree.
The coordinator preserved all of it and committed only its own documentation;
the owner must land the milestone artifacts so the branch is reproducible.

---

## 8. P2 memory closeout reconciliation

`docs/hardware/control-assembly/memory-report.md` was corrected to the
receipt-bound values: selection `c4c31c10…` (was `bd3c56ff…`) and materialized
notes 8981 bytes (was 8243). The report's substantive claims hold: expert-curated
selection, notes-only, nothing claimed as automatic learning, no live attempt.
Its "Delivered" paragraph already states that a missing live-delivery record
keeps reuse indeterminate — the condition that now applies.

---

## 9. What transferred, what failed, what changed, knowledge for the next run

**Transferred.** Five expert-curated buck procedures were selected and
delivered to the construction path with content-bound receipts. Reusable
harness capability now exists and is proven by tests: a source-derived board
generator with a strict Rust identity bridge, explicit bounded native board
operations with existing-validator feedback, a cross-unit memory
selection/delivery policy, and a block-composition path (19 instances mapped
by canonical source path, layer remap, via recreation, prototype exclusion).

**Failed / unverified.** No live model turn (transport). Schematic parity on
both boards. The cross-view full-board overlay. `power_width`. MCU-local
strapping/pull-up routing. The `BlockSession` combined-assembly profile and the
`L_Bourns_SRP1265A` vendor path are named P1 gaps.

**Changed in the harness (all owned by child plans, none by this report).**
New block source adapter + Rust bridge + block runner + memory policy +
composition scripts; two adapter fixes (copper-layer id, generator property
geometry); a documented headless-zone segfault workaround. The plan named a new
`zapote/` Rust workspace, but the implemented Rust validation lives in
`harness-lab/src/block.rs` and `packages/temper-design-bundle`; `zapote/` is an
unpopulated scaffold. This deviation is recorded, not silently accepted.

**Knowledge available for the next run.** The frozen memory catalog and
selection; the generator and adapter fixes; the verified layer/via/identity
mapping; the finding-set comparison method; and this report's evidence
identities. The abandoned `zapote/runs/mcu-20260910-a/` generation tree (a
superseded copy of the candidate, identical board bytes) was removed; all
failed-run evidence (transport block, discarded smokes, unassisted failure) is
preserved.

---

## 10. Remaining interface obligations for the next unit

These are named obligations, not fictional connectors. A full-board overlay
routes only obligations whose counterpart is in scope; none below is coppered
here. Source: `interfaces.json`, `identity-inventory.json`,
`integration-report.md` §8–9.

**Power.**
- `BUCK_VIN_15V` (+15V, SELV_LV): counterpart PS1 (IRM-10-15) is outside this
  candidate. **Not routed.**
- `BUCK_EN` (`en`): P1 source-side tie only; target U3 (SOT-23-6) has pads
  `gnd/sw/+15V/fb/boot` and **no EN pad**, so no board route exists unless P1
  changes the package. **Owner: P1.**
- Internal `BUCK_3V3_TO_MCU` and `BUCK_GND_TO_MCU` were routed and pass.
- `power_width` **fail**: 19 inherited 0.3 mm segments (`buck-vcc-1`, `fb`,
  `boot`) below the 0.6 mm assembly floor. **Owner: next assembly review.**

**RTD.**
- `RTD_SPI`: `RTD_CS_N`, `RTD_SCK`, `RTD_SDI`, `RTD_SDO`, `RTD_DRDY` →
  MAX31865 RTDSensing. MCU pads 18/12/19/20/17. **Not routed.**
- Source wrapper stubs required by ThermalSystem: `adc_ntc_stub` (GPIO3/pad
  15). OBLIGATION-1 (`relay_ctrl` IO16 vs firmware `CS_RTD2=16`) and
  OBLIGATION-5 (UART `TXD0/RXD0` vs GPIO43/44) remain contested and draw no
  copper until resolved.

**Safety.**
- `SAFETY`: `SHUTDOWN`, `RTD_HW_FAULT`, `WDT_RESET_N`, `WDT_KICK` → interlock +
  TPS3823. MCU pads 10 (SHUTDOWN), 6, 7, 22, 8. **Not routed.**
- OBLIGATION-2 (`fault_status_in` IO17 vs firmware `LED_FAULT=17`;
  `LED_POWER=18` has no source net). OBLIGATION-4 (`discharge_ctrl` IO47
  absent from `temper_pins.h`). The HV⇄SELV isolation barrier must be
  preserved across every copper layer; this section introduces no new
  crossing.

**Programming / UI.**
- `COMMS`: native USB `usb_dn`/`usb_dp` (pads 13/14), `i2c_sda_ui`/`i2c_scl_ui`
  (pads 31/32), UART `tx`/`rx` (pads 36/37). **Not routed.** OBLIGATION-3
  (native USB IO19/20 vs firmware `RELAY_BYPASS=19`/`FAULT_OUT=20`) is
  contested.
- MCU-local `en`, `io0`, `scl`, `sda` remain unconnected (7 DRC items); BOOT
  (`btn_boot`/`io0`) and reset (`btn_reset`/`en`) buttons are placed but not
  fully routed to the module.

---

## 11. Milestone verdict

**INCOMPLETE.** The section is an `apparatus-only-assisted` integration
candidate: source-derived, strictly identified, connectivity-checked, and
introducing zero DRC/ERC findings, but it is **not** a whole-cooker pass, **not**
proof of electrical performance, and **not** hardware-validated. Closure
requires, at minimum: a live model delivery/construction turn (or an accepted
equivalent), passing schematic parity on the MCU and assembly, the full-board
overlay comparison, resolution of the `power_width` finding and the P1-named
gaps, and the landing of the uncommitted milestone artifacts noted in §7.

Evidence identities: accepted MCU package `pcb/blocks/mcu/` (board
`f9087f4c…`, manifest `10cbe6db…`); assembly candidate
`pcb/blocks/control-assembly/` (source `bde0b005…`, routed `09c6e46d…`,
summary `e636d96c…`); target context `db3e07b6…`; P1 handoff
`harness-lab/runs/mcu-20260910-a/handoff.json`; P2 selection `c4c31c10…`;
production board `00a27419…` (unchanged).

---

## 12. Addendum — post-commit verification and a source-identity defect (2026-09-10)

After the milestone artifacts were committed, final verification surfaced a
**real source-identity defect in the accepted MCU package**, and the worktree
was found to be under **live concurrent editing by another session**. Both are
recorded here rather than hidden.

### 12.1 SW1/SW2 used a placeholder resistor footprint (R3 violation)

`pcb/blocks/mcu/source-manifest.json` records the accepted package's reset/boot
buttons as:

```
SW1  footprint Resistor_SMD:R_0603_1608Metric  mpn EVQ-P7A01P
SW2  footprint Resistor_SMD:R_0603_1608Metric  mpn EVQ-P7A01P
```

`pcb/blocks/mcu/mcu_candidate.kicad_pcb` physically places both as 0603
resistors. HEAD's `elec/src/components.ato` explicitly called this a
placeholder:

> Placeholder 0603 footprint: Button_Switch_SMD is not in the committed
> fp-lib-table yet. Swap to SW_SPST_B3U-1000P (or similar) once the library is
> added via tools/setup_kicad_env.py.

This slipped through the strict pin/part admission because a 0603 footprint
exposes pads `1,2`, which coincide with `Button.p1/p2`. The gate checked pad
*numbers*, not that the footprint is the purchased part — exactly the
"correct by coincidence" failure mode the plan's R3 forbids ("unresolved exact
purchased parts prevent admission"). **The accepted package therefore does not
satisfy R3 and the milestone Definition of Done ("Generated artifacts and
source agree").**

### 12.2 The source is now being corrected concurrently — and the gate rejects it

A concurrent session changed the `Button` footprint to
`Button_Switch_SMD:SW_SPST_EVQP7A` at 16:54 (working tree, not this branch's
commit; left untouched). That stock footprint has **pads `1,1,2,2`**.
`block_source.build_strict_pin_map` emits one entry per footprint pad, so
`candidate_validate_pin_map` correctly fires:

```
duplicate_map: map covers SW1.1 more than once
```

`harness-lab/test_block_source.py` consequently fails on the live tree
(10 passed, then a build error). This is caused by the concurrent source edit,
not by the committed milestone state; a re-run is not meaningful while another
session edits `elec/src/components.ato`. The correct fix is a reviewed explicit
alias map for the duplicated switch pads (KTD3/R3), delivered by P1.

### 12.3 Consequence for closure

The closed list of remaining closure work in §11 gains two items: (1) replace
the SW1/SW2 placeholder footprint with the real purchased switch and re-admit
the package, and (2) support duplicated switch pad numbers with a reviewed
alias map. Re-run `test_block_source.py` and regenerate the MCU package only
after the concurrent source edit lands.
