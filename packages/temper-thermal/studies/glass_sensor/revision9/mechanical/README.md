# R9 nominal capture audit and open process witnesses

This derived study reads frozen R7/R5/R2 builders. It does not replace current CAD. Physical results are **NOT_RUN**. The complete retention force path is **not closed**: the three separate upper capture fingers have no modeled attachment capable of transmitting their upward reaction to the carrier.

Run from this directory with the existing CadQuery environment:

```sh
sh run.sh
shasum -a 256 -c artifacts.sha256
```

`TEMPER_CAD_PYTHON` can select an existing compatible interpreter; default `/private/tmp/temper-center-sensor-env/bin/python` (CadQuery 2.6.1). `TEMPER_GLASS_STUDY_ROOT` can relocate the inherited study directory, but all four pinned hashes must still match. No installation is performed. The runner invalidates old completion receipts before work and only writes a new receipt after all expected results and STEP digests agree. The source identities are checked before importing and after the capture run, and again at finalization. STEP timestamps can change on export; their digests identify this output snapshot.

`check_capture.py` samples seven sequential axial states for each complete R7 variant: cap lift 0/0.10/0.20 mm; then island lift 0.05/0.10 mm with cap lift held at 0.20 mm relative to it; then carrier lift 0.20/0.40 mm with both relative gaps taken up. It exports both final catch configurations for each variant. At the requested combined endpoint, carrier is fixed, island is +0.10 mm and cap is +0.30 mm absolute. At the downstream endpoint these become +0.40/+0.50/+0.70 mm. The latter is a geometric stop investigation, not an approved operating stroke.

The audit checks every modeled non-seal solid pair, including native leads, four complete extension routes, glass and witnesses. Intended same-terminal weld/lead overlaps are separately recorded; wrong-terminal and unintended collisions fail. All eight modeled weld-to-wire/native connections must remain present. The two flexible seal envelopes are excluded from collision claims. Contact tests require an upward-facing planar face against a downward-facing planar face, matching elevations and positive common area. B-rep face bounds use a 10⁻⁶ mm flatness/elevation tolerance to accommodate OCCT bounding-box padding; collision volume threshold is 10⁻⁶ mm³. These are numerical geometry tolerances, not manufacturing tolerances.

Each exported complete STEP is reimported, all solids validated, total volume compared within 10⁻⁴ mm³, and the critical catch/transfer bodies identified by volume and bounds. The actual reimported faces must reproduce the expected contact counts. Three intentional 0.01 mm overtravel probes must produce positive intersection. These checks establish sampled nominal geometry, not a continuous swept volume, lateral escape resistance, hot clearance, glass strength, spring stress, lead life, joint strength or sealing.

`inspect_joints.py` separately checks the finger attachment direction for all three variants. It deliberately reports `OPEN_UPWARD_TENSION_JOINT`, even when capture geometry passes. Holding the fingers fixed to the carrier in a kinematic model is a prescribed constraint, not evidence of a manufactured joint. Joining those bodies in CAD would not by itself qualify fabrication or assembly: the inward toes obstruct straight axial insertion of the Ø8 mm island flange, and no alternative insertion sequence, compatible carrier material, ceramic undercut process or positive attachment has been demonstrated.

`build_witness.py` exports **P9-569-OPEN-100** and **P9-569-OPEN-150**. Each contains only the inherited D6 316L cap, a centered 2.7 × 2.5 mm candidate bond volume and a 2.3 × 2.1 × 0.25 mm bare alumina witness. There is no RTD, wiring, cover, seal, cartridge, permanent gap spacer or holding fixture. External gap control remains separate. Ceramabond 569 is a named process candidate with unknown cured thermal properties; no 569 thermal response is predicted. A nominal CAD gap does not establish cured thickness or process capability.

Machine-readable results are `capture-checks.json`, `attachment-checks.json` and `process-witness-checks.json`. `artifacts.sha256` is a run-completion/output snapshot receipt, not a physical acceptance certificate. The parent `mechanical-resolution.md` reports conclusions and remaining decisions.

The later, separate **C9-BOLTED** M222 derivative replaces the undefined finger attachment with three screw/nut-mounted metal brackets and assembly passages. See `bolted-candidate.md`; run `sh run_candidate.sh` and verify `candidate-artifacts.sha256`. Its three STEP exports and access checks are excluded from the baseline receipt. The baseline's `OPEN_UPWARD_TENSION_JOINT` remains true for R7. The candidate has a defined threaded-joint concept and nominal bearing/assembly geometry, but no hot strength, preload, locking, production assembly or inherited thermal-performance claim.
