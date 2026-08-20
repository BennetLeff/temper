<!-- provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
     The barrier-12.6mm half of this document (§3) was measured at
     fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (origin/fix/power-islands-backbone-on-in2cu),
     working tree clean, extensions rebuilt and re-verified 10/10 fresh there.
     branch agent/per-pairing-placement-route (merge of
     origin/fix/power-islands-backbone-on-in2cu fd4e73644 and
     origin/analysis/per-pairing-placer-solve 30edd0a93, merged clean).
     Board measured: pcb/temper.kicad_pcb sha256
     26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b -- verified
     identical before and after every measurement below; never opened for
     writing. Every candidate board was emitted to a scratch path outside the
     repo. No placement was written back, so no power_pcb_dataset/drc_ceiling.json
     re-measurement is owed.
     Environment: this worktree's OWN .venv (`make venv-isolate` under
     `env -u CONDA_PREFIX`). `scripts/check_stale_extensions.py` PASSED 10/10
     fresh before every measurement in both configurations, and
     `resolve_insulation_declaration` was verified present on the
     temper_design_bundle_python surface before any per-pairing run (the
     timestamp comparison alone does not prove it). kicad-cli 10.0.5.
     pcb/temper.kicad_dru regenerated in-process from
     scripts/generate_kicad_dru.py's `generate_dru()` and written into each
     scratch DRC directory alongside temper.kicad_pro, fp-lib-table and libs/;
     pcb/temper.kicad_dru itself was never written.
     Machine: 62 GB RAM, >32 GB free throughout; no competing route_board.py.
     No cProfile was attached to any quoted run. -->
---
module: router
tags: [routing, placement, creepage, cp-sat, iec60664, connectivity, isolation-barrier]
problem_type: diagnosis
---

# 2026-08-19: the per-pairing placement, routed — connectivity improves on every metric, and the creepage-halo mechanism is confirmed causally

**Authority: analysis and measurement only.** `pcb/temper.kicad_pcb` was not
modified (sha256 `26981fea…c110b`, verified before and after). The placement
routed below is a measurement written to a scratch file, not a candidate for
the board. Landing a new placement is the owner's decision.

## 0. Headline

`analysis/per-pairing-placer-solve` produced a compliant placement and nobody
had routed it. This session regenerated it, **confirmed it reproduces exactly**,
routed it, and measured the delta against a control routed in the same process
tree from the same branch.

**Connectivity improves on every metric**, and the improvement is causally
attributable: the placement takes **50 → 23** of the zero-copper nets out of the
"own pad inside a foreign net's creepage halo" bucket, and **149 → 83** pads out
of a foreign halo statically. It also compacts the HV keepout union, adding
**+3 818 mm²** of routable area. Both mechanisms are real; the second one was
not anticipated by the brief and is the larger of the two at the derived
barrier width.

**One confound had to be controlled first, and it is large.** Merging the
per-pairing branch also raises the *router's* own barrier constant from 12.6 to
20.0 mm, which is not a placement effect at all (§1). Everything is therefore
reported in **both** configurations.

## 1. The confound: merging the per-pairing branch moves the router, not just the placer

`MIN_BARRIER_WIDTH_MM` is the literal `12.6` on `origin/main`. On the
per-pairing branch it is **derived** — `_barrier_floor_mm()` over
`elec/insulation_manifest.yaml` — and evaluates to **20.0 mm** (`SELV<->TANK`,
Table 17 row vi ×2). That figure is a **PROVEN FLOOR ONLY**, not a requirement
(47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope; IEC 60664-4 not obtained).
Two router-side consequences, neither caused by any placement:

* `DEFAULT_CORRIDOR_WIDTH_MM = MIN_BARRIER_WIDTH_MM + 0.5`, so the disc
  `compute_hv_selv_keepout` unions around **every** HV pad grows 13.1 → 20.5 mm.
  That union is a hard obstacle for the A* grid, the straight-line fallback, the
  zone pour and the via search.
* `packages/temper-placer/configs/pair_creepage.generated.yaml` goes from a flat
  12.6 to per-pairing figures, several of them 20.0. The router reads this file
  directly (`router_v6/pair_creepage.default_creepage_table`), so every creepage
  halo it stamps changes size.

Exactly **three files** separate the two router configurations —
`pair_creepage.generated.yaml`, `zone_pour_creepage.generated.yaml`,
`core/isolation_constants.py`. **`router_v6/` itself is byte-identical**:

```
git diff --stat origin/fix/power-islands-backbone-on-in2cu...agent/per-pairing-placement-route \
    -- packages/temper-placer/src/temper_placer/router_v6/     # empty
```

What the raise costs in routable area, measured on the **committed** placement
(`…-keepout-area.py`):

| corridor width | HV keepout | % of board | free area |
|---|---:|---:|---:|
| 13.1 mm (barrier 12.6) | 25 753.1 mm² | 67.1 % | 12 622.9 mm² |
| 20.5 mm (barrier 20.0) | 33 822.6 mm² | 88.1 % | **4 553.4 mm²** |

Free area falls by 64 %. That, and not the placement, is why a route on this
branch at the committed placement collapses from 4 907 segments to 758 (§4).

**Consequence for reading this document:** §3 is the comparison against the
brief's 282/606 reference and is the one to quote. §4 is the comparison at the
figures the placement was actually solved for.

## 2. The placement reproduces — exactly

`docs/evidence/2026-08-19-per-pairing-route-solve-model-e.py`, seed 42, 600 s
budget, no ablation sweep (the four headline rows only), no cProfile.

| # | model | published verdict | **this session** | time |
|---|---|---|---|---:|
| **A** | netclass (DRU-resolved) + tank creepage, **no barrier** | `optimal`, 168/168 | **`optimal`, 168/168** | 34.9 s |
| **B** | A + per-pairing barrier, all 8 isolators | `infeasible` | **`infeasible`** | 26.1 s |
| **D** | B with **T1 alone** relaxed | `infeasible` | **`infeasible`** | 25.8 s |
| **E** | B with **T1 and T2** relaxed | `optimal`, 168/168 | **`optimal`, 168/168** | 38.4 s |

The encoded setbacks came back identical too — `MAINS` 4.80, `DC_BUS` 8.00,
`SWITCHING` 8.00 *(proven floor only)*, `TANK` 20.00 *(proven floor only)*,
`all_determinable = False`. **Row E is the placement routed below**, and it is a
placement in which T1's and T2's straddle constraints were exempted; both are
intra-package shortfalls that no placement can fix. Every verdict downstream is
**CONDITIONAL** on the two indeterminate pairings.

### 2a. Writing it to a board

`…-apply-placement.py` uses the production contract from `cli/__init__.py`'s
`optimize`: `board_origin=board.origin`, `components=netlist.components`,
`rotation = rotations.get(ref, 0) * 90.0`, then
`copy_kicad_project_sidecar`. Result: **168 components updated, 0 skipped**,
`check_placement_roundtrip` **PASS (168 components, 521 pads)**,
`check_board_containment` **PASS**, template sha256 unchanged. The write is
deterministic — two independent runs produced byte-identical
`bf9dde9a8d15a2bb4b0a6126e5ee318fe5e7b34a0e36b5cc1c17e6a620f4bc01`.

> **Defect found on the way.** `check_placement_roundtrip`'s docstring says
> `positions` are "in the same coordinate frame the writer wrote (file
> coordinates)", but the production CLI at `cli/__init__.py:760` passes
> `cp_result.positions`, which is the `normalize=True` frame — off by
> `board.origin` = (8, 20) mm. On this board every one of 689 pad comparisons
> is displaced by exactly that vector. The oracle is not catching what it
> claims to; it happens not to fire because the CLI is the only caller.
> Reported, not fixed here (out of scope, and it is a gate change).

## 3. The measurement against the brief's reference (barrier 12.6 mm)

Configuration: `origin/fix/power-islands-backbone-on-in2cu` at
`fd4e73644`, extensions rebuilt and re-verified 10/10 fresh,
`MIN_BARRIER_WIDTH_MM = 12.6`, flat 12.6 pair-creepage table. Both boards routed
through `route_once` with **every default** (the default recipe), in the same
branch state, minutes apart.

**The baseline reproduces.** Every figure the brief quotes, and every DRC
category the reference commit `fd4e73644` enumerates:

| | brief / `fd4e73644` | **reproduced** |
|---|---:|---:|
| `unconnected_items` | 282 | **282** |
| nets ≥2 pins fully pad-connected | 60/139 | **60/139** |
| nets with zero copper emitted | 63 | **63** |
| pads inside a foreign creepage halo | 182/498 own-layer cells (36.5 %) | **182/498 (36.5 %)** |
| of the 63, attributed to a foreign halo | 50 | **50** |
| pad pairs closer than required creepage | 187 across 74 nets | **187 across 74 nets** |
| In1.Cu / In2.Cu / F.Cu segments | 294 / 227 / 485 | **294 / 227 / 485** |
| `clearance` / `creepage` | 129 / 106 | **129 / 106** |
| `via_dangling` / `shorting_items` | 26 / 20 | **26 / 20** |
| `hole_clearance` / `copper_edge_clearance` | 15 / 11 | **15 / 11** |
| `solder_mask_bridge` | 4 | **4** |
| total DRC violations | 606 | **604** |

Total 604 vs 606: **every enumerated copper category matches exactly**, my count
is 3/3 identical on identical bytes, and the residual 2 sit in cosmetic
categories the reference did not list. Not treated as a real delta in either
direction.

### 3a. The connectivity delta

| metric | committed placement | **model-E placement** | delta |
|---|---:|---:|---:|
| `unconnected_items` (kicad-cli) | 282 | **251** | **−31** |
| nets ≥2 pins fully pad-connected | 60/139 | **82/139** | **+22** |
| …on the ≥2-pad denominator | 33/112 | **55/112** | +22 |
| nets with zero copper emitted | 63 | **36** | **−27** |
| pads inside a foreign creepage halo | 182/498 (36.5 %) | **105/397 (26.4 %)** | **−77 cells** |
| DRC violations (`--all-track-errors`) | 604 | **539** | **−65** |
| pads connected | 171/496 | **215/496** | +44 |
| segments / vias / zones | 4907 / 149 / 152 | 5912 / 186 / 124 | +1005 / +37 / −28 |

Routed board digests (sha256):

* committed placement `697bad8936b3e16ed5168dfe113aead82c2ca93152a345e10df663883c30f370`
* **model-E placement `af99bd04fa5d873c20e14913f397781a2553f7c8be74f93e9ab39fb5068f5e07`**

### 3b. Per-category DRC, honestly

The −65 total is **carried by silkscreen, and the copper categories regress.**

| category | committed | model-E | delta |
|---|---:|---:|---:|
| `silk_overlap` | 199 *(at its 199 cap — a floor, not a count)* | 4 | ≤ −195 |
| `silk_over_copper` | 42 | 14 | −28 |
| `copper_edge_clearance` | 11 | 0 | −11 |
| `clearance` | 129 | **218** | **+89** |
| `hole_clearance` | 15 | **39** | **+24** |
| `shorting_items` | 20 | **43** | **+23** |
| `drill_out_of_range` | 6 | **20** | **+14** |
| `solder_mask_bridge` | 4 | **15** | **+11** |
| `creepage` | 106 | 108 | +2 |
| `via_dangling` | 26 | 29 | +3 |

Three things must be said plainly:

1. **`silk_overlap` 199 is a saturation floor**, not a count (kicad-cli's
   `ERROR_LIMIT`). The true committed value is ≥199, so the improvement is a
   lower bound and the total's −65 is a *lower* bound on the silk gain and
   simultaneously **hides a copper regression**.
2. **`clearance` +89, `shorting_items` +23** are partly a volume effect — the
   model-E board carries 20 % more segments and 25 % more vias, so there are
   more item-pairs to violate — and partly real.
3. **`hole_clearance` +24 and `drill_out_of_range` +14 are placement-caused and
   are a genuine defect of this placement.** The CP-SAT model constrains
   inter-component separation and creepage; it does not constrain hole-to-hole
   spacing or drill-to-edge. This placement is *not* landable as-is on that
   basis alone, independent of T1/T2.
4. **`creepage` does not improve** (106 → 108, inside the documented ±1–2
   flicker), even though the placement takes the count of below-requirement pad
   pairs down by 81 (187 → 106; a count delta, not a proven resolved-set — no
   pair-level set comparison was run). Routed copper generates its own creepage
   violations, and that offsets the pad-level gain. The pad-pair census and the
   routed-board census are different measurements and should not be conflated.

## 4. The measurement at the figures the placement was solved for (barrier 20.0 mm)

Configuration: `agent/per-pairing-placement-route`, `MIN_BARRIER_WIDTH_MM =
20.0`, per-pairing creepage table. Same router code.

| metric | committed placement | **model-E placement** | delta |
|---|---:|---:|---:|
| `unconnected_items` | 354 | **258** | **−96** |
| nets ≥2 pins fully pad-connected | 37/139 | **79/139** | **+42** |
| …on the ≥2-pad denominator | 10/112 | **52/112** | +42 |
| nets with zero copper emitted | 90 | **39** | **−51** |
| DRC violations | 631 | 693 | +62 |
| `creepage` | 245 | **114** | **−131** |
| pads connected | 132/496 | **218/496** | +86 |
| segments / vias / zones | 758 / 52 / 73 | 6166 / 194 / 96 | +5408 / +142 / +23 |

Routed digests: committed
`2b0d36102d0f1a9849a2675481165be2e02cf193c7f2d7b9c82e75232d0f8a79`, model-E
`128d5c3202c583ffd9ce8183c364e354a80dadfcd08957d3405bd8accdda5dfb`.

Two observations:

* At the derived barrier the committed placement is **very nearly unroutable** —
  758 segments, 10/112 nets connected, 88.1 % of the board inside the keepout.
  The model-E placement recovers it to 6166 segments and 52/112.
* **The model-E placement at the harder 20.0 mm barrier (258 unconnected) still
  beats the committed placement at the easier 12.6 mm barrier (282).**
* `creepage` 245 → 114 here is the placement doing real work against the
  *derived* rules, which is exactly what it was solved against.

## 5. Causal attribution

The brief asked specifically whether an improvement is because haloed pads were
freed, and warned that this session has repeatedly found correlated numbers with
different causes. Two mechanisms were measured **directly**, both at the same
12.6 mm table so the comparison is like-for-like.

### 5a. Mechanism A — foreign creepage halos over own pads (the brief's hypothesis): CONFIRMED

Measured by re-running the mechanism-A instrumented route
(`git show origin/analysis/mechanism-a-zero-copper:docs/evidence/2026-08-19-mechanism-a-instrument-route.py`,
plus an added `--pcb` so it can route a board other than the committed one —
observation-only, the routed call is still `route_once` with every default) and
its analyzer, on **both** placements:

| | committed | **model-E** |
|---|---:|---:|
| own-layer pad cells freed by `_unblock_net_pads` then re-blocked by `_stamp_foreign_creepage_halos` | **182 / 498 (36.5 %)** | **105 / 397 (26.4 %)** |
| zero-copper nets whose headline verdict is "own pad inside a FOREIGN CREEPAGE HALO" | **50 of 63** | **23 of 36** |
| …as a share of the zero-copper set | 79 % | 64 % |

Because the denominator moves with the run (fewer nets decline, so fewer pads
are sampled), the router-level number alone cannot separate "the placement freed
pads" from "the router declined different nets". So it was cross-checked with a
**static, route-independent** census (`…-halo-static.py`) — a pure function of
the placement and the creepage table:

| | committed | **model-E** | delta |
|---|---:|---:|---:|
| pad pairs closer than their required creepage | **187** | **106** | −81 |
| nets involved | **74** | **41** | −33 |
| **pads inside a foreign net's creepage halo** | **149 / 523** | **83 / 523** | **−66 (−44 %)** |
| `FinePitch ↔ HighVoltage` | 15 | **0** | −15 |
| `HighVoltageTank ↔ Power` | 3 | **0** | −3 |
| `Default ↔ HighVoltageTank` | 2 | **0** | −2 |

Both measurements move the same way, on a fixed denominator in the static case.
**Mechanism A is real and is a genuine cause of the connectivity gain.**

### 5b. Mechanism B — HV keepout union compaction: NOT ANTICIPATED, AND LARGER AT 20.0 mm

`compute_hv_selv_keepout` unions a disc around every HV pad. That union's area
depends on how *clustered* the HV pads are, which the placement controls
directly. Measured on the two placements (`…-keepout-area.py`, 109 HV pads,
board polygon 38 376 mm²):

| corridor width | committed free area | **model-E free area** | gain |
|---|---:|---:|---:|
| 13.1 mm | 12 622.9 mm² | **16 441.3 mm²** | **+3 818.4 mm² (+30.2 %)** |
| 20.5 mm | 4 553.4 mm² | **11 688.4 mm²** | **+7 135.0 mm² (+156.7 %)** |

The per-pairing placement pushes the HV domain to one side of the barrier, which
is what the barrier constraint *is* — and the side effect is that the keepout
discs overlap each other far more, so their union shrinks. At 12.6 mm this adds
30 % more routable area; at 20.0 mm it more than doubles it.

**This is the mechanism that explains §4's 758 → 6166 segments**, and it is
distinct from mechanism A: it is about where copper may be laid at all, not
about whether a specific pad is enterable.

### 5c. What is NOT attributable to the placement

* The `silk_overlap` collapse (199 → 4) is a **silkscreen** effect of spreading
  footprints out. It dominates the DRC total and says nothing about copper.
* `clearance` and `shorting_items` rise partly because there is simply more
  copper on the model-E board. Reported as a confound, not netted out — this
  document does not have a per-item-pair attribution for them.
* The `creepage` DRC count is essentially flat at 12.6 mm. The static pad-pair
  gain does not survive contact with routed copper.

## 6. Answering the brief's question directly

> *If connectivity does NOT improve, that is the more important result.*

It improves, in both configurations, on every connectivity metric:

* `unconnected_items` **282 → 251** at 12.6 mm, **354 → 258** at 20.0 mm.
* nets fully pad-connected **60/139 → 82/139** at 12.6 mm, **37/139 → 79/139** at
  20.0 mm.
* nets with zero copper **63 → 36** at 12.6 mm, **90 → 39** at 20.0 mm.

And the causal claim the brief asked to be verified rather than inferred holds:
the haloed-pad population really does fall, on a fixed denominator
(149 → 83 pads, 187 → 106 pairs, 74 → 41 nets).

**The placement was a binding cause. It was not the only one**, and it is not
sufficient: 251 unconnected items and 36 zero-copper nets remain, 23 of those 36
still have a pad inside a foreign halo, and the placement introduces 24 new
`hole_clearance` and 14 new `drill_out_of_range` violations that the CP-SAT
model does not constrain.

## 7. Constraints observed

* **`pcb/temper.kicad_pcb` was never modified.** sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified
  before and after every step, in both branch configurations. Every candidate
  board went to a scratch path outside the repo.
* **No requirement was lowered anywhere.** No clearance, creepage, copper-weight,
  loop-area, ampacity, annular-ring or DRU threshold was changed. The two
  indeterminate pairings stayed fail-closed at 20.0 and 8.0 mm; `determinable` is
  `False` for both and every dependent verdict above is labelled CONDITIONAL.
  The 12.6 mm configuration in §3 is `origin/fix/power-islands-backbone-on-in2cu`
  **as it already exists** — nothing was lowered to produce it, and it is
  measured *because* it is the reference the brief's 282/606 came from.
* **No check was made to pass by weakening it.** No test skipped, `xfail`ed,
  deleted or relaxed; no ratchet raised; no allowlist broadened; no
  `continue-on-error`, `|| true`, `# type: ignore` or `# noqa` added.
* **No oracle re-pinned**, none deleted or consolidated.
* **`power_pcb_dataset/drc_ceiling.json` was not re-baselined** and was not
  touched.
* `git stash` was not used. No pushed history was rewritten.
* The two edits to the borrowed mechanism-A harnesses (`--pcb`, `--census-board`)
  are **additive with unchanged defaults**, so the original invocation still
  reproduces the original output. They were made to scratch copies; the
  originals on `origin/analysis/mechanism-a-zero-copper` are untouched.

## 8. Reproduce

```bash
# --- setup ------------------------------------------------------------
env -u CONDA_PREFIX make venv-isolate
.venv/bin/python scripts/check_stale_extensions.py           # must be 10/10
.venv/bin/python -c "import temper_design_bundle_python as t; \
    assert hasattr(t,'resolve_insulation_declaration')"

# --- 1. regenerate the placement (rows A/B/D/E, ~2 min) ---------------
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-solve-model-e.py \
    --emit /tmp/placement_E.json

# --- 2. write it to a scratch board -----------------------------------
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-apply-placement.py \
    --placement /tmp/placement_E.json --output /tmp/board_E.kicad_pcb

# --- 3. route both, default recipe (~200 s each) ----------------------
.venv/bin/python scripts/route_board.py --pcb pcb/temper.kicad_pcb \
    --output /tmp/routed_committed.kicad_pcb
.venv/bin/python scripts/route_board.py --pcb /tmp/board_E.kicad_pcb \
    --output /tmp/routed_E.kicad_pcb

# --- 4. measure -------------------------------------------------------
for b in committed E; do
  .venv/bin/python docs/evidence/2026-08-19-per-pairing-route-connectivity.py \
      --board /tmp/routed_$b.kicad_pcb --label $b
  .venv/bin/python docs/evidence/2026-08-19-per-pairing-route-measure-board.py \
      --pcb /tmp/routed_$b.kicad_pcb --repo "$PWD" --label $b \
      --samples 3 --scratch /tmp/drcscratch
done

# --- 5. causal attribution -------------------------------------------
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-halo-static.py \
    --board pcb/temper.kicad_pcb --repo "$PWD" --label committed
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-halo-static.py \
    --board /tmp/board_E.kicad_pcb --repo "$PWD" --label model-E
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-keepout-area.py \
    --board pcb/temper.kicad_pcb --label committed
.venv/bin/python docs/evidence/2026-08-19-per-pairing-route-keepout-area.py \
    --board /tmp/board_E.kicad_pcb --label model-E

# --- 6. §3, the 12.6 mm reference configuration -----------------------
# same steps on origin/fix/power-islands-backbone-on-in2cu, extensions rebuilt
```

## 9. What this leaves open

1. **The 20.0 mm barrier makes this board very nearly unroutable at the
   committed placement** (88.1 % keepout, 758 segments). Whoever lands the
   per-pairing derivation must decide what to do about that; it is not a
   placement problem and no placement fully solves it.
2. **The placement introduces `hole_clearance` (+24) and `drill_out_of_range`
   (+14) violations.** The CP-SAT model does not constrain hole-to-hole spacing.
   That gap should be closed before any placement of this family is proposed for
   the board.
3. **23 of the remaining 36 zero-copper nets still have a pad inside a foreign
   creepage halo.** Mechanism A is reduced, not eliminated.
4. **`creepage` on the routed board does not improve at 12.6 mm** despite the
   static pad-pair gain. The routed-copper contribution to creepage has not been
   separated from the pad contribution.
5. **`check_placement_roundtrip`'s only production caller passes the wrong
   coordinate frame** (§2a). The oracle is not doing what its docstring says.
6. T1 and T2 remain intra-package shortfalls that no placement fixes, and
   `SELV<->TANK` still has no determinable requirement.
