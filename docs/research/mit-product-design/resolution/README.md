# Resolving the Temper product review

**2026-10-04 follow-up:** the [manufacturing-readiness packet](../readiness/README.md)
adds current source/board checks, cooling space studies and build records. Its
[power reconciliation](../readiness/power/README.md) supersedes the treatment of
45 A as a normal-operation allocation: the independent shunt path has a
conditional static trip range of 38.44–85.55 A at +85 °C board temperature with
an assumed +50 °C shunt rise. The 45 A model remains a historical comparative
screen; no operating-current envelope is released. These are calculated
thresholds, not measured trip or current-extinction results.

The corrections below address the original eight findings against the **actual successor designs**. Three demonstrable defects have digital corrections: misleading capacitor/power modeling, missing HOT5 brownout detection, and ten R4 front-compartment collisions. **The product is not yet qualified or ready for fabrication.** Current-board integration, supplier limits and physical tests remain open; a software or CAD correction closes only the property it checks.

## Design basis

- Electrical intake: `worktrees/ps-oracle` at `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`. Native-18 has **135 components and 83 nets**, a 240 × 160 mm outline, and four copper layers. Its board SHA-256 is `fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002`. Earlier 91/67 and 114/75 summaries do not describe this board. The existing interlock is reused; a new latch is not needed merely because the original review did not include it.
- Mechanical intake: `output/temper-flush-front-r4` is the approved continuous flush-front direction. R2 and folded-aluminum packages remain historical comparisons. R4's imported PCB is an older design; clearance to it does not establish clearance to native-18.
- Product decisions: preserve the current US/Mexico 120/127 V, 60 Hz, 15 A direction and the approved D18 cooling allocations. A specific production heat-sink/fan assembly and its installed performance remain unselected/unmeasured. Do not silently substitute the earlier enclosure's cooling assumption.
- Existing physical fixtures and data templates: `output/temper-engineering-validation`. Their existence does not establish that the experiments ran. The user confirmed **no assembled hardware yet** on 2026-10-03; physical results remain `NOT_RUN`.

## Work and verification

The user authorized correction of T01–T08 from the [original review](../application/review.md). Independent Sol workers own the capacitor model, R4 geometry, protection circuit, and integration packet. The parent inspects the actual changes and reruns the relevant checks. Work stays in the `mit-product-guidance` worktree; the original main checkout and the other electrical task's checkout are preserved.

The [electrical model correction](electrical-model.md), [HOT5 circuit correction](protection.md), and [mechanical correction](mechanical.md) give the changes and verification limits. The [integration packet](integration/README.md) carries revision identities, mating interfaces, cooling requirements, supplier inspection details, market/earthing basis, and observable control/cleaning trials.

The historical 45 A comparative screen gives the selected 70 µH / 0.54 µF model **14.8% at 114 V and 4.3% at 127 V** full-power outcomes over assumed intended-pan samples. These are conditional model results, not measured cookware coverage or implementable power guarantees: the model omits the independent shunt path's dynamic response. Do not raise protection thresholds to recover the old claim. Real coil/pan impedance and the required power envelope must be reconciled with both protection paths before finalizing the resonant bank, board and cooling package.

## Remaining dependencies in order

1. **Power envelope:** measure the selected coil and intended pans, obtain CDE limits for both exact capacitor variants, and reconcile tank and shunt waveforms with both protection paths, their tolerances and delays. Select or revise coil/bank/control limits against that evidence.
2. **Integrated hardware:** choose the sink, fans, dedicated fan supply, inlet/EMI arrangement and their actual envelopes. The 305 mm candidate sink does not fit the old 265 mm chamber. Build a current populated-board assembly and incorporate the HOT5 source change into the native layout before repeating fit, routing and insulation checks.
3. **Mechanical limits:** obtain safe switch travel/force and selected seal/adhesive/glass limits. The inherited knob click stack still has a -0.20 mm worst-case actuation margin; shifting its stop without a maximum safe stroke could exchange a missed click for damage. Close both bounds before accepting it.
4. **Prototype evidence:** use the supplied fault, thermal, manufacturing, control and cleaning records on an assembled prototype. Fault extinction, shorted-switch interruption, installed cooling, PE/insulation, glass retention, sensor contact loss, seals and repeated service remain `NOT_RUN`.

These dependencies are deliberately not marked resolved by the new CAD or connectivity passes. They require specific missing measurements, component selections and supplier limits, not another software assertion.

## What qualifies as closure

| Finding | Digital closure | Evidence still required for product closure |
|---|---|---|
| T01 — capacitor envelope | Correct the model's false safety implication, selected topology, deterministic corners, and current-sharing assumptions | Exact capacitor waveform/frequency/temperature envelope, real coil/pans, measured stress and sharing |
| T02 — fault extinction | Correct a demonstrated circuit gap and verify the generated source/net/BOM; identify each full-chain interface | Delay and residual-energy captures, shorted-switch interruption/fuse coordination, rail-collapse and startup behavior |
| T03 — cooling/package | Use native-18 and D18 allocations together; retain geometry conflicts instead of hiding them | Selected hardware, populated board STEP, operating fan curve, closed-assembly thermal/fault tests |
| T04 — insulation/earthing | Preserve direct protective bonding and record the actual construction and market-classification decisions | Applicable edition/classification, material evidence, final construction review and electrical safety tests |
| T05 — actuation | Remove the R4 carrier/compartment collisions and check PCB placement correspondence; expose both ends of the travel/force budget | Supplier safe mechanical stroke/force, working mechanism and hot/cold/cycled measurements |
| T06 — glass/sensor/seals | Define datum, load, compression, contact and service stacks with testable acceptance sources | Selected materials, load/contact/leak/thermal-cycle tests, contact-loss detection independent of pan presence |
| T07 — manufacturing | Provide exact drawing/inspection requests, assembly sequence and traceable first-article records | Supplier process acceptance, bend coupons, actual material/hardware/finish, pilot evidence |
| T08 — controls/cleaning | Preserve the approved exterior and provide observable trial tasks and records | Real controls/firmware, representative cooking and cleaning observations, seal/finish durability |

An `OPEN`, `NOT_RUN`, or unknown supplier limit cannot be converted to a pass by relabeling it. These are specific remaining dependencies, not permission to fabricate or energize an unqualified assembly.
