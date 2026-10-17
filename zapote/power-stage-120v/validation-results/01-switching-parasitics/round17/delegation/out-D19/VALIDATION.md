# D-19 validation receipt

Main-context review of the report and numerical scripts; no independent peer review or physical compliance test is claimed.

| Check | Result | Evidence |
|---|---|---|
| Original round-3 fixture | PASS, exact JSON equality | `fixture.json`, `prepare.py` |
| Matching 443 ns switching baseline | PASS, three measurements within 1 ppm | `baseline-comparison.json`, baseline raw/logs |
| Vendor fetch/hash and kit smoke | PASS before simulation | `smoke.txt`, library digest in `provenance.json`; no library committed |
| Isolated edges | 16 complete; no aborted row used | `edges.json`, `raw/` |
| Independent raw replay of edge metrics | PASS, unchanged exact CSV/JSON hashes | `edge-replay-check.json`, `edges.py --replay` |
| Periodic operating-envelope coverage | PARTIAL: inspect exact status inventory, never infer margins for aborted/unsettled rows | `periodic-table.md`, `periodic-runs/`, `provenance.json` |
| Periodic steady-state screening | Only complete runs with <1% last-period RMS change in all three source signals enter spectra | `sweep.py`, per-case JSON |
| Periodic raw/FFT replay | PASS for every non-aborted saved waveform, including the rejected unsettled case | `replay-check.json` |
| 60 kHz timestep comparison | Critical 240 kHz line stable; full-band spectrum NOT qualified | `step-comparison.json` |
| 35 kHz timestep comparison | Missing successful second tier; coarse attempt aborted | per-case JSON/logs |
| Fourier phase/RMS, PE reference, limits and analytic RLC checks | 5 tests PASS | `tests.txt`, `test_spectrum.py` |
| Script name/error lint | Ruff F/E9 PASS | `ruff.txt` |
| Import boundaries | PASS, 0 new violations | `import-gate.txt` |
| Derived-artifact consistency | PASS, read-only check | `regen-check.txt` |
| Plot inspection | Edge and discrete-harmonic plots visually checked | `edges.png`, `spectrum.png` |
| Scope | Only this `out-D19/` folder; no board/netlist/firmware/vendor-library changes | Git diff |

The 60 kHz timestep check moves some combined-sensitivity lines by up to 6.72 dB. It also changes the minimum headroom of one exploratory filter from −0.99 to +5.47 dB. This prevents an all-band numerical acceptance claim. The low-frequency DM shortfall survives that check; it does not validate other current/line/ESL points, hot operation, leg B, the physical RF filter or regulatory receiver behavior.

Task 07 B5/C1 remain open. A completed report of these limitations is not closure of the underlying EMI qualification. No Rust workspace, native bridge or firmware build was run for D-19. Read-only regeneration was used to respect the output-only scope; no unrelated generated files were rewritten.

Git whitespace checks pass for maintained source/report files. Native simulator logs retain their original trailing whitespace, and standard CSV files retain CRLF record endings; those evidence formats are not rewritten to satisfy a prose whitespace check.
