# Mechanical route to a buildable Temper prototype

**2026-10-04 — design integration work, not a manufacturing release.** The existing 370 × 440 × 105 mm folded R4 exterior can contain the *bare volume* of the D18 sink/fan example in its rear bay, but that does not connect the heat sources to it. A direct placement against either transverse edge of the front board clashes with retained R4 structure. The next mechanical decision is a jointly engineered board/sink interface, before ordering the enclosure or PCB.

Read [packaging study](packaging.md), [knob correction requirements](knob.md), and [drawing/inspection inputs](drawing-inputs.csv). The separate manufacturing packet owns the full traveler and release gates; these files supply its mechanical inputs.

## What this wave establishes

- Reconciled native-18 board `fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002`, revision `fda5ab9ec`, with R4 assembly `2e89923f65e466831395a10a2ac7e307ded48fbb8b49e5c19e87b4da1df21291`. Native-18 is still 135 components; the 142-component HOT5 source candidate is not routed. The saved stack is **1.653 mm**, distinct from the nominal 1.6 mm procurement target.
- Ran four OpenCascade solid-intersection probes against **252 retained R4 named parts**: initial rear bay 4 collisions; shifted rear bay 0; direct rear edge 20; direct front edge 93. Each STEP reimports validly. All are incomplete envelope studies. The study excludes the historical PCB and old cooling allocations explicitly, retains their chamber and the actual controls/support/sensor, and does not suppress failed intersections.
- Identified the actual modeled knob candidate, **C&K PTS645SH43SMTR92 LFS**, and confirmed its electrical stroke/force in the current manufacturer sheet. Proved that merely moving the current stop to regain the missing 0.20 mm would require accepting at least 0.70 mm total switch stroke before any positive trip margin. No such supplier permission exists in the reviewed sheet.
- Found an additional integration gate: **no dedicated PCB mounting-hole footprints exist** in the native-18 inventory. Component NPTHs are not automatically enclosure mounts. A mount/edge-retention design and electrical keepouts must be added jointly; no drilling into the existing board is implied.

## Recommended next design sequence

1. Power and mechanical engineers freeze a physically realizable five-device contact drawing, insulation/clamp stack, and compact long-edge sink/duct candidate meeting the unchanged D18 thermal allocation. Ask suppliers for a characterized custom sink and compare the documented shorter class; neither a smaller catalog body nor moving heat elsewhere is accepted without recalculation. Keep the current exterior as the initial constraint. If the complete hardware cannot satisfy it, return a quantified exterior/change choice to the owner.
2. Integrate that interface with the HOT5-updated populated PCB, dedicated board retention, complete controller/UI boards, fan supply, EMI hardware and harnesses. Model real heights, terminals, tool paths and populated underside. Assign required electrical distances from the approved insulation basis, not these nominal CAD gaps.
3. Build an **unpowered mechanical mockup**: device clamps and dummy packages, board mounting, duct/guard parts, actual cable bends, service removal, adjusted click cartridge, glass/support and seals. Close dimensions and procurement drawings before making a powered integrated prototype.
4. Qualify the actual material and joints, then run the controlled powered thermal/flow/fault program owned by power and validation. Repeat affected tests after any board, clamp, duct, seal or chassis revision. Manufacturing release then needs supplier capability and repeat-build evidence; one fitting mockup is insufficient.

## Source and artifact identities

- Frozen R4 source remains `output/temper-flush-front-r4/`; it was not changed. In particular `inputs/exterior-parameters.json` has inherited glass values: use current `catalog.json` and `src/enclosure.py` for the R4 **338 × 326 × 4 mm** glass at nominal z=101..105. Coil envelope top z=98 gives **3 mm nominal gap** to glass underside, not a toleranced acceptance. Coil winding/ferrite/support heights remain allocations.
- Study inputs, build adapter, full input hashes and collision receipts are at `output/temper-manufacture-readiness/mechanical/`. Read its README before opening any STEP. It is not a replacement for `output/temper-flush-front-r4/STEP/assembly.step`.
- Native board inventory is `output/temper-manufacture-readiness/pcb/native18-geometry.json`; the builder binds its board identity and saved thickness. Twenty-four assigned models are provisional envelopes, and even resolved library models do not prove manufacturer dimensions.
- Cooling authority remains D18 in `worktrees/ps-oracle/zapote/power-stage-120v/DECISIONS.md` and `validation-results/01-switching-parasitics/round17/delegation/out-D18/README.md`. This study does not lower its thermal budget based on the unresolved current/power envelope.

The MIT-derived skills supply datum, tolerance, load-path and assembly-review methods. Manufacturer information supplies catalog inputs. The only newly verified results here are digital geometry/identity checks and arithmetic; physical fit, thermal performance, leak resistance, switch durability and safety qualification remain unmeasured.
