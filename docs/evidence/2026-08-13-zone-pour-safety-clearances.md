<!-- provenance: branch fix/zone-pour-safety-clearances, worktree /home/bennet/Desktop/temper/.claude/worktrees/zone-pour, base origin/main b5e94b6f1. HEAD at every measurement below: d07ff245b (worktree clean, `git status --porcelain` empty, `git grep -l "^<<<<<<< " -- '*.py' '*.rs' '*.yaml'` empty). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- byte-identical to the hash docs/evidence/2026-08-12-dru-rule-precedence.md and docs/evidence/2026-08-12-router-safety-clearances.md both record, and NEVER written by this task (`git status --porcelain pcb/` empty throughout; every board this document measures is a copy under this session's scratchpad, outside the repo). pcb/temper.kicad_dru is byte-identical to main's after regeneration -- this task adds an export to scripts/generate_kicad_dru.py and changes no rule. power_pcb_dataset/drc_ceiling.json not touched. kicad-cli 10.0.5. No solve was run, so scripts/verify_pumpkin_engine.py was not required and is not claimed; no placement was computed and no board was written back, so `board_origin=board.origin` has no call site here. No subagents dispatched. -->

# Zone pours: the per-net maximum came from a standard row that does not exist, the pour is now carved per PAIR — +60% poured copper at an unchanged 6.0mm mains-to-SELV barrier. And the brief's 1.80mm figure is a pad pitch, not a pour.

**Verdict up front.**

1. **The 1.80mm `ac_l` gap is not poured copper.** `docs/evidence/2026-08-12-dru-rule-precedence-violations.csv`'s single `ac_l` row is `kind_a=Pad, kind_b=Pad, components=R6` — the two ends of one through-hole resistor, 1.80mm apart because that is R6's own pad pitch. No pour, no track, no routing decision can move it. The real poured `ac_l` figure is **6.0005mm against a 6.0mm requirement** (sec 2).
2. **What the pours actually applied: a single scalar, 6.0mm, on every zone on the board**, derived by maximising `netclass_rules.yaml`'s `class_pairs` over the *pour-eligible* classes only. Every one of that table's HV rows cites "IEC 60335-1 Table 16 working isolation at 400V", a row established not to exist (PR #1081), and its own comments call the figures "legacy, not primary-cited" (sec 3).
3. **KiCad's zone filler already applies per-pair clearance correctly, once the DRU is correct.** Measured: with the zone's local clearance set to 0.05mm, 6mm and 20mm on the same board, the poured-copper violation count is **0, 0, 0** while the copper area moves 22,746 → 12,254 → 5,634 mm². The repo's scalar was not buying safety; it was only removing copper (sec 4).
4. **kicad-cli never tests zone-to-pad clearance at all.** A `.kicad_dru` containing only `A.Type == 'Zone' && B.Type == 'Pad'` at **20mm** reports **zero** violations on a board with 128 filled zone polygons and 793 netted pads; the same probe against `Track` at 0.5mm reports 19. Every partner kicad-cli pairs with a zone is a Track or a Via (sec 4.3). A pour that is wrong against a pad is invisible to this project's whole DRC apparatus.
5. **The fix, measured:** poured-copper pair-clearance violations **0 → 0**, `ac_l` to nearest SELV/LV copper **6.0005mm → 6.0005mm** (requirement 6.0mm), `ac_l` poured copper **417.64 → 739.41 mm²** (+77%), all poured copper **7,339.75 → 11,725.69 mm²** (+60%), **pad connectivity 29/139 → 29/139** — and that is pad connectivity, this project's declared primary completion metric, not routed/attempted (sec 5).
6. **The ground pour survives, and #1099's collapse does not recur — because it cannot.** `gnd`'s plane is `_ground_plane.py`'s In1.Cu generator, which does not go through `_emit_zone_pours` at all and is not touched here. Its `OTHER_NET_CLEARANCE_MM = 0.05` governs the F.Cu/B.Cu MST backbone and drop-via placement, **not the pour** (sec 6).
7. **KiCad's zone filler is not deterministic**, even under this repo's own `MaximumThreads=1` pin: six fills of the byte-identical committed board produced 126–132 filled polygons. Every A/B figure here is therefore reported with its measurement protocol, and the two columns are single runs of a step whose noise is characterised in sec 5.3.

---

## 1. Which nets take the zone-pour path

`_should_route()` (`router_v6/_net_policy.py`) excludes a net from Stage 4's A\* only when `_zone_layers_for_net()` says a pour will actually cover it. Measured against `pcb/temper.kicad_pcb`'s 162 distinct named nets:

| net | netclass | safety category | pour layers |
|---|---|---|---|
| `ac_l` | ACMains | **AC** | F.Cu, B.Cu |
| `ac_n` | ACMains | **AC** | F.Cu, B.Cu |
| `+170V_BUS` | HighVoltage | **HV** | F.Cu, B.Cu |
| `+15V_LS` | HighVoltage | **HV** | F.Cu, B.Cu |
| `DC_BUS_RTN` | HighVoltage | **HV** | F.Cu, B.Cu |
| `PWR_RTN` | HighVoltage | **HV** | F.Cu, B.Cu |
| `SW_NODE` | HighVoltage | **HV** | F.Cu, B.Cu |

Seven nets, exactly the list `docs/evidence/2026-08-12-router-safety-clearances.md` sec 2.4 names, and **every one of them is mains or HV**. The mechanism the brief asked to verify is intact: the exclusion is conditional on pour eligibility, not on the net's name, since the 2026-08-08 fix.

**But "excluded from A\*" and "gets a pour" are not the same set, and the difference matters.** `_zone_layers_for_net()` grants pour eligibility to **17** nets — the seven above plus ten more (`a`, `zcd`, `w1_1`, `w1_2`, `tank-out`, `tank.c_tank1-p2`, `power_in.ntc-no`, `hb.power_loop.q_high-g`, `discharge.k_dis1-nc`, `discharge.k_dis2-nc`) whose names do not match `_should_route()`'s HV/power patterns. Those ten are **both** A\*-routed and poured. So the pour path is not a fallback for what A\* declines; it is a second copper-producing mechanism running over a larger, overlapping set, and a per-pair defect in it reaches ten nets that #1112's fix also touches.

`gnd` is **not** in either list. It is netclass `Power`, which declares no `plane_required`/`plane_preferred` strategy, so `_zone_layers_for_net("gnd") == []`. Its plane comes from a different module entirely — see sec 6.

Reproduce: `docs/evidence/2026-08-13-zone-pour-safety-clearances-measure.py` shares the parsing; the net list above is `[n for n in board_nets if not _should_route(n)]` and `[n for n in board_nets if _zone_layers_for_net(n)]`.

---

## 2. The `ac_l` gap, measured both ways

### 2.1 The 1.80mm figure is a pad pitch

`docs/evidence/2026-08-12-dru-rule-precedence-violations.csv` contains exactly one `ac_l` row:

```
rule,required_mm,actual_mm,deficit_mm,net_a,net_b,class_a,class_b,kind_a,kind_b,components,x_mm,y_mm
AC Mains to LV,6.0,1.8,4.2,ac_l,power_in.r_zcd_top1-p2,ACMains,Default,Pad,Pad,R6,143.8125,59.73
```

`kind_a=Pad`, `kind_b=Pad`, one component, `R6`. This is R6's own two pads: `ac_l` on one end and the ZCD divider's midpoint net on the other, 1.80mm apart because that is the footprint's pitch. It is a **placement/part-selection** violation — the same class as `docs/evidence/2026-08-12-dru-rule-precedence.md`'s own "48-violation placement floor" that survives stripping all copper. No pour, no track and no A\* decision can change it; only a different footprint (or a different classification for the divider midpoint, which `docs/evidence/2026-08-12-selv-net-assignment.md` is separately live on) can.

This is reported rather than worked around because the brief framed it as *"mains copper is currently poured within 1.80mm of SELV"*. It is not. The barrier the brief is worried about is real; this particular number is measuring something else.

### 2.2 The poured figure

Measured on the board's own zones after `kicad-cli pcb drc --refill-zones --save-board`, minimum distance from any `ac_l` filled polygon to any copper belonging to a net in the SELV/LV domain on the same layer:

| board | `ac_l` poured copper | closest SELV/LV copper | required | verdict |
|---|---:|---:|---:|---|
| committed board, refilled | 306.96 mm² | **6.0005 mm** (`y` track, B.Cu) | 6.0 mm | OK |
| pours re-emitted, **before** this change | 417.64 mm² | **6.0005 mm** (`sw` track, B.Cu) | 6.0 mm | OK |
| pours re-emitted, **after** this change | **739.41 mm²** | **6.0005 mm** (`safety-line-2` track, B.Cu) | 6.0 mm | OK |

The mains barrier holds in all three columns, at the same figure, while the pour that has to hold it grows by 77%. The recurring `0.0005 mm` is KiCad's own fill quantisation, present in kicad-cli's numbers too (sec 4.2).

---

## 3. What the pours applied before

`router_v6/_zone_pour_stitch.py::_emit_zone_pours`, on `origin/main`:

```python
zone_netclasses = {class of every POUR-ELIGIBLE net in pad_positions}
for nc in zone_netclasses:
    eff = own_clearance
    for other_nc in zone_netclasses:          # <- pour-eligible classes only
        pair_key = tuple(sorted((nc, other_nc)))
        if pair_key in class_pairs:
            eff = max(eff, class_pairs[pair_key]["clearance"])
        else:
            eff = max(eff, max(own_clearance, other_clearance))
    effective_clearance[nc] = eff
```

Evaluated against this board (`ACMains`, `HighVoltage`, `HighVoltageTank` are the live pour classes), this yields:

```
{'ACMains': 6.0, 'HighVoltage': 6.0, 'HighVoltageTank': 6.0}
```

and the emitted zones confirm it — **every one of `pcb/temper.kicad_pcb`'s 96 committed zones carries `(connect_pads yes (clearance 6))`**, including `+3V3`, `vcc`, `+15V`, `V_BUS_SENSE`, `GATE_HS/LS` and `PWM_HS/LS`. (Those seven are stale: they predate the 2026-07-28 `routing_strategy` eligibility fix and the current code would not emit them at all. Re-emitting with `origin/main`'s emitter produces 94 zones, still all at `6.0000`.)

Three separable defects:

**It is a per-NET maximum.** One scalar cannot express 6.0mm-to-SELV *and* 3.0mm-to-HV *and* 0.5mm-to-gate-drive, which is what `pcb/temper.kicad_dru` actually requires of an `ACMains` pour. Answering "what clearance does the pour apply?" with one number is the defect, not the number's value.

**The maximum ranges over the wrong set.** `zone_netclasses` is the set of classes that *themselves pour*. The clearance a pour keeps from class C is therefore computed without C in the maximum unless C also pours. It lands on 6.0mm here only because every pour-eligible class on this board is HV or mains — an accident of the current eligibility list, not a property of the code. Grant one LV class `plane_preferred` and the same code emits a figure derived from classes the new pour may never be near.

**The numbers are `class_pairs`.** Every HV row of `packages/temper-placer/configs/netclass_rules.yaml`'s `class_pairs` carries `because: "IEC 60335-1 Table 16 working isolation at 400V — 6.0mm between mains and signal traces"`. That row does not exist; PR #1081 established this from recovered primary text. The same file's own comments say the figure is *"a legacy, not primary-cited, number"* and that *"the fab-authoritative enforcement point is scripts/generate_kicad_dru.py"*. `class_pairs` also names 5 of this board's 9 live classes and says **nothing about `Default`** — 69 of 110 nets, and the class on the SELV side of the mains barrier the whole exercise is about.

### 3.1 What `_ground_plane.py` and `_power_islands.py` use, since the brief asked

Neither of these is `_emit_zone_pours`, and neither uses `class_pairs`:

* **`_ground_plane.py` (In1.Cu, `gnd`).** The pour polygon is the board outline inset by `BOARD_EDGE_MARGIN_MM = 1.0`, minus a keepout that is `compute_hv_selv_keepout()`'s union of `DEFAULT_CORRIDOR_WIDTH_MM + KEEPOUT_EXTRA_MARGIN_MM` discs around every HV-domain pad, plus every HV net's own copper. `OTHER_NET_CLEARANCE_MM = 0.05` is **not** used to clip the pour — the module's own comment says so explicitly ("never to clip the pour itself (In1.Cu carries no pre-existing copper of any kind)"). It steers the F.Cu/B.Cu MST backbone and the drop vias. #1099's 0.05mm concession is therefore a **via-and-backbone-placement** concession, not a pour-clearance one, and the `gnd` connectivity collapse it records (46/86 → 7/86) was a spanning-tree effect, not a fill effect: the module's own note records that blocking the MST from crossing buffered holes "cost 25 pads of connectivity (46 -> 21/86), because the MST is a tree -- losing one 'hub' edge disconnects everything downstream of it".
* **`_power_islands.py` (In2.Cu, `Power` rails).** Same shape, same imported `compute_hv_selv_keepout`, its own `OTHER_NET_CLEARANCE_MM = 0.05` again only for stitch traces and vias, plus `INTER_RAIL_CLEARANCE_MM = 0.4` between rails on the shared inner layer.

Both are per-domain keepouts on layers that carry no other copper, not per-pair clearances, and both are **out of this change's scope** — stated rather than glossed. Making them pair-aware is a separate piece of work with a different failure mode (they are the modules #1099's connectivity finding actually concerns).

---

## 4. How KiCad really resolves a pour's clearance — three measurements the fix depends on

### 4.1 The zone's `(clearance ...)` scalar is honoured, but only where no rule matches

The same board, zones refilled with the local clearance rewritten to three values:

| zone local clearance | filled polygons | total poured copper |
|---:|---:|---:|
| 0.05 mm | 204 | **22,746.16 mm²** |
| 6 mm | 131 | 12,253.56 mm² |
| 20 mm | 73 | 5,634.13 mm² |

So the field is live — it is not inert. But at every one of those three settings the `ac_l` pour sits at the *identical* distance from the same items (5.4005mm from R11's pad outline, 6.0005mm from the `y` track, to 1e-7 mm), because for those pairs a custom DRU rule matches and **the rule overrides the local clearance**. The scalar is consulted only for pairs no rule reaches.

### 4.2 The measurement agrees with kicad-cli to 0.0004 mm

`clearance` saturates at `EXTENDED_ERROR_LIMIT = 499` and #1112 sec 2.1 measured that #1111's partitioned protocol does not transfer to freshly-poured boards, so every number here is geometric. Cross-validated against kicad-cli with a probe DRU (`A.NetName == 'ac_l'`, `min 8mm`) on the refilled committed board:

| kicad-cli `actual` | this document's geometry | pair |
|---:|---:|---|
| 6.1422 mm | 6.1426 mm | `zcd` via ↔ `ac_l` zone, F.Cu |
| 6.5287 mm | 6.5287 mm | `zcd` track ↔ `ac_l` zone, B.Cu |
| 6.0005 mm | 6.0005 mm | `y` track ↔ `ac_l` zone, B.Cu |

### 4.3 kicad-cli never tests zone-to-pad clearance

| probe rule (sole rule in the file) | violations |
|---|---:|
| `A.Type == 'Zone' && B.Type == 'Pad'`, `min 20mm` | **0** |
| `A.Type == 'Zone' && B.Type == 'Track'`, `min 0.5mm` | 19 |
| `A.Type == 'Zone' && A.NetName == 'ac_l'`, `min 12mm` | 37 — partners: 35 Track, 2 Via, **0 Pad** |

On a board carrying 128 filled zone polygons and 793 netted pads. **This project's entire DRC apparatus — the ceiling, the gates, every violation count in every evidence document — is blind to a pour that is too close to a pad.** That is why the fix puts the requirement in the emitted geometry and not only in a field KiCad will or will not consult.

It is also why this document's measurement **excludes** pad-involving pairs, which is a decision with a second, independent reason: nearly every through-hole pad here carries `(remove_unused_layers yes)`, so on a layer where the pad has no connection KiCad keeps only the hole. Measured on R11 pad 2 (`size 2.4`, `drill 1.2`): the `ac_l` pour is 5.4005mm from the full 2.4mm outline and exactly **6.0005mm — the rule figure — from the 1.2mm hole**. Counting the outline manufactures a 0.6mm deficit that does not exist. Deciding which layers are "used" needs KiCad's own connectivity pass. Including pads (`--include-pads`) reports 35 violations before and is left available for inspection; none of them survive contact with the hole geometry, and none of them are quoted as results here.

---

## 5. The fix, and what it measures

### 5.1 What changed

`scripts/generate_kicad_dru.py` gains a second export,
`packages/temper-placer/configs/zone_pour_clearance.generated.yaml`: the same
`_matching_rules` analyser #1110 built and #1112 reused, run over a **Zone ↔ {Track, Pad, Via, Zone}** world instead of Track↔Track, with `pcb/temper.kicad_pro`'s netclass clearances as the fallback for pairs no rule matches — read from the project file rather than restated, because that is the file kicad-cli loads. A separate table is necessary, not tidy: `Default routing`'s condition names `Track` explicitly, so it does not reach zone↔pad, zone↔via or zone↔zone, and **64 class pairs resolve differently** between the two worlds. Every cross-domain safety figure is measured to be identical across all four item types, and `_assert_safety_pairs_type_invariant` re-derives that on every run and raises rather than letting a future rule quietly make a barrier figure depend on what it is measured against.

`router_v6/zone_pour_clearance.py` reads it and provides the two things a KiCad zone needs:

* `min_required()` → the `(clearance ...)` scalar. The **minimum**, because KiCad consults it only where no rule matches, so anything larger silently over-clears every relaxed pair and anything smaller is never reached.
* `pair_clearance_keepout()` → the region the pour must not enter: every other net's copper, each buffered by its own half-extent **plus that specific pair's figure**. Pads, pre-existing tracks and vias from the `ParsedPCB`; this route's freshly emitted tracks and vias parsed from the emitter's own output strings.

`_emit_zone_pours` carves each hull against that keepout before emitting it (`_carve_outline`, which splits a hull the keepout severs and drops fragments below the filler's own 0.25mm `min_thickness` scale).

Deliberately **not** carved against: other zones. KiCad resolves zone-to-zone overlap by priority at fill time, the measurement finds no zone-to-zone violation at any local clearance, and carving would make the result depend on which net's pour was emitted first — reintroducing exactly the order-dependence #1112 removed from the A\*.

### 5.2 Result

Protocol: parse `pcb/temper.kicad_pcb` (read-only), `strip_existing_zones`, call `_emit_zone_pours` with the production `design_rules`, write to a scratch board outside the repo, `kicad-cli pcb drc --all-track-errors --severity-all --refill-zones --save-board` under this repo's own thread-pinned env, then count uncapped from the filled geometry. Identical protocol on both columns; the **only** difference is which checkout supplies `_zone_pour_stitch.py` (`origin/main`'s for *before*, this branch's for *after* — verified byte-identical for `zone_emission.py` and `io/kicad_parser.py` between the two).

| metric | before | after | Δ |
|---|---:|---:|---|
| **poured-copper pair-clearance violations** | **0** | **0** | — |
| safety-governed subset | 0 | 0 | — |
| **`ac_l` → nearest SELV/LV copper** (req 6.0mm) | **6.0005 mm** | **6.0005 mm** | — |
| emitted zone `(clearance ...)` | `6.0000`, every zone | per-pair minimum | — |
| zones emitted | 94 | 199 | +105 |
| isolated-pad stitch segments | 4 | 34 | +30 |
| filled polygons | 113 | 196 | +83 |
| **`ac_l` poured copper** | 417.64 mm² | **739.41 mm²** | **+77.0%** |
| **all poured copper** | 7,339.75 mm² | **11,725.69 mm²** | **+59.8%** |
| **pad connectivity (`fully_connected`)** | **29 / 139** | **29 / 139** | — |

**The headline is honest about what it is.** The violation count does not fall because it was already zero on the population kicad-cli can see: KiCad's filler applies the per-pair DRU figure itself (sec 4.1), so the repo's 6.0mm scalar was never the thing holding the barrier — it was only removing copper. What this change buys is (a) the pour's clearance now derives from the enforced rule file instead of a citation to a standard row that does not exist, (b) the requirement is in the emitted geometry, where the sec-4.3 blind spot cannot hide a defect, and (c) 60% more copper on a board where pour area is thermal and EMI headroom.

**Pad connectivity is unchanged at 29/139, and that is the number being reported** — `audit_pad_connectivity`'s `fully_connected`, this project's declared primary completion metric (`docs/evidence/2026-08-11-pad-connectivity-ground-truth.md`), not `completion_rate`. The committed board measures the same 29/139, so neither column regresses it. `fake_completion` moves 53 → 61 and `honest_gap` 57 → 49, which is the 30 extra stitch segments the larger pours reach: more nets have *some* copper, none newly have *all* of it.

### 5.3 The noise floor, since it is bigger than several of these deltas

KiCad's zone filler is **not deterministic**, even under `_single_threaded_kicad_env()`'s `MaximumThreads=1`. Six fills of the byte-identical committed board:

| run | filled polygons | kicad-cli total violations |
|---|---:|---:|
| 1 | 128 | 2,290 |
| 2 | 128 | 2,177 |
| 3 | 129 | 2,158 |
| 4 | 130 | — |
| 5 | 132 | — |
| 6 | 126 | — |

126–132 polygons on identical input. The A/B above is a single run per column, so the polygon counts carry roughly ±3 of that noise; the copper-area and clearance figures are far outside it (+60% area; the `ac_l` barrier figure is identical to 1e-7 mm across all six baseline runs). **This is a finding in its own right for anyone ratcheting a fill-dependent number** — it is the same lesson as #1110 sec 8's "do not ratchet a saturated number", in a different mechanism.

---

## 6. Does the ground pour survive?

**Yes, and the #1099 conflict does not arise here, for a structural reason rather than a lucky one.**

`gnd` is netclass `Power`. `Power` declares no `plane_required`/`plane_preferred` routing strategy, so `_zone_layers_for_net("gnd")` returns `[]` and **`gnd` never reaches `_emit_zone_pours` at all**. Its plane is `_ground_plane.py`'s standalone In1.Cu generator, which calls the zone-emission primitives directly and is untouched by this change (sec 3.1). `_power_islands.py`'s In2.Cu rails are in the same position.

So the brief's stated worry — *"if a correct pour clearance collapses `gnd` connectivity 46/86 → 7/86 again, that is the finding"* — is not reachable through this change. The measured connectivity is unchanged at 29/139 across the committed board and both columns.

**This is not the same as saying the conflict does not exist.** It says the mains barrier and the ground plane are currently on *different layers* (F.Cu/B.Cu vs In1.Cu) built by *different code* with *different clearance models*, and the pour that carries the mains barrier is not the pour that carries the ground return. Whether In1.Cu's `compute_hv_selv_keepout` disc union is the right barrier for a mains-domain net is a real question this change does not answer and does not claim to.

---

## 7. Constraints checked

* **PD2 / 8.0mm isolation barrier with all 8 isolators, and #1082's IGBT heatsink co-location.** Both hold **by construction**: no placement was computed, no component moved, and `pcb/temper.kicad_pcb` was never written (`git status --porcelain pcb/` empty throughout; the input board's sha256 is unchanged and matches the two prior evidence documents). This change emits copper only.
* **`drc_ceiling.json`** untouched.
* **`pcb/temper.kicad_dru`** regenerates byte-identical to `main`'s. The generator change is purely additive — a second exported table — and `scripts/tests/test_generate_kicad_dru.py` passes 35/35 against it.
* **Routing OOM / `--net-batching`.** No route was run: the A/B re-emits pours over the committed board's own placement, which isolates the change under test from #1112's A\* and from Stage 3's memory behaviour entirely. That also means this document makes **no claim** about pour behaviour on a freshly-routed board, where the pours would be carved against ~3,300 fresh tracks instead of the committed board's 2,290. Measuring that needs a `--net-batching` route and is the obvious next step.

---

## 8. Tests

* `packages/temper-placer/tests/router_v6/test_zone_pour_clearance.py` (15 tests): the mains-to-`Default` bar is 6.0mm against every item type; same-domain pairs are relaxed to 3.0/0.2mm and that is pinned so a future edit cannot "restore" `class_pairs`' flat 6.0mm; unknown class and unknown item type resolve conservatively rather than raising; `min_required` is a minimum and is strictly below the mains bar; the generated yaml is re-derived from `pcb/temper.kicad_dru` and compared byte-for-byte (the drift gate); the carve holds 6.0mm from a `Default` track and 3.0mm from an HV track *in one geometry*; it never carves against the pour's own net or another layer; it splits, drops and passes through correctly.
* `packages/temper-placer/tests/router_v6/test_adapter.py::TestCrossClassZoneClearance` (5 tests) **rewritten, not deleted**. Every assertion in it pinned the per-net-max-over-`class_pairs` model faithfully, which is why it failed against the corrected one. It now asserts the opposite where the model changed — a `class_pairs` override of 8.0mm or 9.0mm must **not** appear in the output — and asserts the enforced figures where it did not. 98 passed, 1 skipped.
