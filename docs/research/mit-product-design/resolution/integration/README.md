# Temper integration packet — T03, T04, T07, T08

**Stage:** revision-matched engineering-prototype preparation. No fabrication, powered-use, or production release is claimed. This packet joins the approved R4 flush-front concept to the current 120 V power-stage candidate; it does not turn either into a measured assembly.

## Revision and authority

| Item | Frozen input for this packet | Authority and limit |
| --- | --- | --- |
| Power source | `worktrees/ps-oracle` HEAD `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`, `zapote/power-stage-120v/DECISIONS.md` SHA-256 `a39a9016ab80e4cbbd46c6095621f3e7c3f809d6cf4142ee20a3b7d1860b758a` | D1/D2/D3/D5/D6 and later 2026-10-03 decisions. Conditional placement approval is not a fabrication release. |
| Routed PCB | `native-18/section.kicad_pcb`, SHA-256 `fb113d95819f1ea7cd8c27f929f7e88308eff44b663af85f71cd6f2bca5a0002` | 240 × 160 mm, four layers, current R9/R17 value revision. See native-18 verification. Current native-18 source build is **135 parts/83 nets**; the original 91/67 or interim 114/75 audits in the MIT review are historical. |
| Electrical source/frozen projection | `elec/src/power_stage_120v.ato` SHA-256 `de5424925fb034b5f699670d6522176696d1006ffa7dcb5c7a734a1d8cb2049b`; `elec/src/parts.ato` `44f3f32770d1cd2c50da5985d82c5836b5a9ad237d1c6585cb6066097a1a7472`. Frozen `default.net` `db15fd819a6d0c7a2818a12806175a517131bd97149f04409ac599a84f520fbc`, `default.csv` `ff81f288e3cac42ac1e0451790267ef255d184bf01399c8bfbfc37c9b95f04ee`, and `resolved-components.json` `6c389531d7516090f74108771cc907edacf9aa796c5275d958d4a2900a7e58a5` | The three frozen export hashes match the native-18 source manifest's `input_hashes`; current Ato source contains the R49k9Dt class, and frozen R9/R17 have the selected 49.9 kΩ MPN. This check does not claim a fresh Atopile compile. |
| Thermal model | D-18 `results.json` SHA-256 `60b9237fadc01ebc75fc8d249e026f46ca122f33b664ed4eca56224f4ce272c2` | Conditional 90-case loss budget, 62 candidate thermal cases; no demonstrated hot loss maximum. |
| R4 geometry | `output/temper-flush-front-r4/STEP/assembly.step` SHA-256 `b27ff932d8b640999c2c556503c66a08152c1a320d9fba31cb5d24572744cd21` | Historical intake assembly; superseded for front-compartment fit by the correction linked below. Its imported PCB remains historical. |
| R4 check | `evidence/front-panel-validation.json` SHA-256 `4bcddd6ff5a7481db90769012e52befddb6d9a96e87c797dd284542e8f5bd0ff` | Historical intake evidence: ten panel-versus-compartment collision hits; superseded by the correction linked below. |
| Existing validation | `output/temper-engineering-validation/requirements.csv` SHA-256 `17641cae0164c26c44aed116e4feb7bac98228278111a0dc1b99f91f00397713` | Proposed screens, physical results NOT RUN. Use its channel map and part-temperature sheet alongside this packet. |

The original MIT review's electrical baseline predates native-18. Its issue definitions remain useful, but dimensions, part counts, and package decisions must be drawn from the inputs above. The R4 hashes above preserve the intake snapshot. The corrected assembly hash is `2e89923f65e466831395a10a2ac7e307ded48fbb8b49e5c19e87b4da1df21291`; its front-panel receipt is `3ca63b8f368996f70576a38ce95f5f4962501f1e4c61b997007bcc66b0ac60e8` (19 nominal checks pass). See [mechanical correction](../mechanical.md). The [HOT5 source correction](../protection.md) also supersedes the electrical source with 142 components / 88 nets; the native-18 board itself is unchanged at 135 / 83. Neither correction closes current-board assembly integration. An additional EMI inlet module under discussion (D22) has no settled geometry or authority here.

## Work products and release gates

- [Interface register](interface-register.csv): identify every real mating surface, drawing, owner, and gap before an integrated STEP fit claim. Rows marked `OPEN` require a measured/supplier drawing and a checked native-18 board envelope.
- [Thermal and packaging budget](thermal-budget.md): carry D-18's accepted allocations into a measurement plan. Its computed junction values remain provisional until fan operating point, interface pressure, case temperatures, and actual switching histogram are checked.
- [Supplier and inspection packet](supplier-inspection.md): send as a draft drawing-review brief once actual material, process, and quantities are chosen. It does not authorize cutting provisional DXFs.
- [Exact component questions](component-questions.md): draft requests for the missing CDE high-frequency envelope and knob-switch safe travel/force. No supplier contact has occurred.
- [US/Mexico safety basis](market-safety.md): scope choices and earthing construction evidence for qualified safety review. Numeric PCB spacing and test limits are deliberately pending applicable edition/classification.
- [Full-size interaction and cleaning trial](controls-cleaning-trial.md) with blank [observations](controls-observations.csv) and [coupon results](cleaning-coupon-results.csv). All physical outcomes are `NOT_RUN`.

**Next controlled build decision:** electrical/thermal/mechanical owners jointly sign the input manifest, replace the historical imported PCB with native-18, fit a selected sink/fans/guards/duct and actual mains/coil/harness parts, and rerun complete assembly interference and insulation checks. If the R4 carrier change shifts the electronics cavity, update this packet's hashes and interface rows before using any fixture drawing.
