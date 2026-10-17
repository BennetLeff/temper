# Inverter U3 measurement-readiness receipt

Date: 2026-09-23. Worktree branch: `codex/zapote-inverter-u3-readiness`; implementation base `afb8b9e31`. This receipt covers the R3 digital evidence inventory in [U3-MEASUREMENT-READINESS.md](../U3-MEASUREMENT-READINESS.md), not the moving Rev38 checkout or a physical article.

## Input identities

`measurement-sources.sha256` locks the following committed donor bytes and the source checker requires all four roles before evaluating the manifest:

| Role | SHA-256 |
| --- | --- |
| Rev38 `pfc_power.ato` candidate | `e3daa14ea8b74344c307a86908c86cbf4d9b44447af367febeb4b581a84ba761` |
| Accepted standalone `gate_drive_unit.ato` source | `6e81398feb135f9a7382033173beda50f7a9cb8b7602ccab00a032f4fe40b2b1` |
| Prior ideal coupled-transient model | `920be23df47cc1dfbdac27cb7b9bfab77379b83bcebeca4d07c59a73b6a6201f` |
| Prior ideal transient case set | `3c4dee030650fe96dfec694a3c5239eee1a3b10fca952e9a19bb02043c2f94ab` |

New checker and inputs at this receipt: Rust source `13324080ea475c296696b18bd03f4fdbe29a1bc2c73caae85d338530c65daec3`; manifest `db2432c0101ec702473643696a873ad525a6863765a31f8d175e3da38fbfedc1`; scenario set `533d9003be18fcfb54364da11895fa9a95d54538cd5cf2bc58f1e056832e5bce`; saved output `7789dddfd08c9ac26a27d513d0b291f9683cd9d2f7e4bf1624774be5ff045a2d`.

## Verification

Run from repository root with the commands in the U3 document. `rustc --edition=2021 --test` ran **16 passing tests**. They include absent scenario/manifest rows, one pan relabeled as the weak pan, 47 kHz alone, free-air L substituted for loaded complex impedance, nominal 390 V substituted for a bounded maximum, gate-off substituted for current-zero, equal VD/VB substituted for F2 evidence, F2 credited for direct-bank interruption, stale return, forged measured origin without raw data, and a complete synthetic row remaining indeterminate. `rustfmt --check` and `git diff --check` passed. The optimized binary returned exit **2**, and its output replay matched `measurement-output.tsv` byte-for-byte. The four source hashes matched current worktree files. No physical captures were run or authored.

## Result and remaining decision

**INDETERMINATE: 0 capture records, 20 missing, 0 rejected.** The 20 scenario slots establish a concrete campaign and a fail-closed accounting method. They do not turn earlier chart readings, ideal 47 kHz waveforms, the 390 V target, an unverified stop delay, or an F2-open model into selected part limits. Each future measured row must be tied to an article, calibrated fixture, raw file, full digest and independent review; the checker can reach `REVIEW_PENDING` at most. A new source revision requires deliberate lock update and replay. Actual loaded coil/pan bounds, bus extrema/source behavior, synchronized stop/current-zero waveforms, bank fault-loop containment, exact device and capacitor ratings, and native construction remain open.
