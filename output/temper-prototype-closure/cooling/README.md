# Cooling/contact and click-fixture outputs

`contact-bearing-cold-study.step` is a **cold mockup candidate**, not an integrated release assembly. It contains all 135 native-18 component models, 250 retained R4 named parts, a bespoke 200 mm sink/contact scheme and a floating four-shoe PCB carrier. It explicitly removes the old board/cooling and two historical chamber allocations. Clip volumes are installation-space allocations, not verified Max03NG geometry. The corrected MOS drawing interval includes the generic rear plane but permits both interference and gap at the fixed interface. Actual seating, coplanarity, clamp pressure and bridge offset are unverified, so the thermal interface dimensions are not ready to machine for real packages. See the engineering notes for the corrected drawing-sign erratum. Complete ducts, new electrical chamber, carrier-to-chassis attachments, guards, harnesses and native-19 HOT5 parts are absent.

`checks.json` records hashes, omissions, exact intersections, contact planes and valid STEP reimport. Zero intersections establish only nominal fit of those modeled solids against the included board and R4 parts. They do not establish thermal flow, electrical insulation, strength or supplier manufacturability.

`click-cartridge-cold-fixture.step` is a simple holding plate for the real switch cartridge in an external force/displacement stand. It does not authorize 0.52 mm switch travel. `click-fixture-checks.json` records its holes, geometry and exclusions.

Replay from repository root using an existing CadQuery 2.6.1 environment:

```sh
/private/tmp/temper-center-sensor-env/bin/python zapote/power-stage-120v/prototype-closure/cooling/build_study.py
/private/tmp/temper-center-sensor-env/bin/python zapote/power-stage-120v/prototype-closure/cooling/build_control_coupon.py
```

[Engineering notes](../../../docs/research/mit-product-design/readiness/mechanical/cooling-closure/README.md) are part of this deliverable. Keep this README with any forwarded STEP. Generated STEP binaries are excluded from publication unless the owner chooses to share them.
