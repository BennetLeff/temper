# Revision 2 verification record

Run date: 2026-10-04. Status: **SIMULATION_AND_TEST_PREPARATION; physical tests NOT_RUN**. Base: `470ac33eced8a46791eff201efc2a8a57d0ee0c9`. Work performed in the isolated `codex/glass-sensor-simulation` checkout; the unrelated dirty primary checkout was preserved.

## Executed

| Check | Result | Evidence |
|---|---|---|
| Assembled thermal/beam model |23 tests pass (14 inherited +9 new), 8 CSVs /1191 rows |[log](logs/thermal.log), [runner](thermal/run.sh) |
| Cap-local contact study |10 tests pass; fault, error-budget, spring and release sweeps replay |[log](logs/contact.log) |
| Bond/lead study |11 tests pass;5 CSVs replay |[log](logs/bond-leads.log) |
| Induction study |16 tests pass;5 CSVs replay; source snapshot hash checked |[log](logs/induction.log) |
| CAD replay |5 positions,29 valid shapes each; no rigid pairwise intersections; STEP reimport valid |[log](logs/mechanical.log) |
| Deterministic evidence |25 CSVs byte-for-byte identical on integrated replay; CAD geometry JSON exactly equal |[artifact checks](logs/artifact-checks.txt) |
| Python/CAD/report |Ruff check passes on both generators; CAD source formatted and loop state explicitly initialized |CAD replay confirms unchanged geometry |
| Rust |rustfmt and `rustc -D warnings` pass; direct clippy-driver passes for assembled model |One scoped `needless_range_loop` allow belongs only to the pinned inherited radial kernel |
| Import boundaries |5 contracts kept,0 broken; gate passes |[log](logs/import-gate.log) |
| Historical preservation |146 files in PR1 hardening manifest still match full SHA-256 |Includes firmware, baseline inputs and previous evidence; no historical evidence repinned |
| Artifact validation |Local report targets exist; SVG XML parses; output CSV row counts/schema and cap-volume identity checked |[artifact checks](logs/artifact-checks.txt) |

Tools: rustc1.92.0; CadQuery2.6.1 in the existing temporary CAD environment; Python with Matplotlib3.10.8 for presentation only. Physics remains in Rust. The report chart was inspected directly. Full HTML browser layout was not inspected: local-file preview was disallowed by the browser policy; no alternate serving route was attempted.

Replay copies were made under `/private/tmp/temper-r2-integrated-check`; CAD export timestamps were not copied back. Source hashes in `source-provenance.json` identify the final deliverable bytes, excluding the manifest itself. Thermal `inputs.sha256` pins the historical kernel and external study inputs separately.

The import gate initially could not write its analysis cache under sandbox permissions; that was a tool error, not a contract failure. The authorized rerun is recorded in `logs/import-gate.log`.

## Scope and limits

No production firmware changed in revision2. The prior15/15 host CTest result is historical evidence in [PR1 verification](../hardening/verification.md), not a newly executed R2 firmware qualification. The pre-existing all-target host build failure in `test_profiles.c` remains as documented there. No ESP-IDF, hardware-in-loop, wet leakage, induction-on or endurance pass is claimed.

The CAD check excludes labeled flexible seal/wire/witness envelopes from rigid intersections. It does not prove manufacturing feasibility, hot tolerance clearance, post/weld/clamp strength, pan rocking across cookware or complete seal closure. Static local displacement cannot distinguish all physical contact faults; negative fault cases remain intentional failures in the model. Neither step response nor DC error is calibrated against a physical cartridge.
