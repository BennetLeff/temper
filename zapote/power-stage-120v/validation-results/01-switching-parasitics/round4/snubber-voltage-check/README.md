# External snubber voltage check for C2

**Scope:** 20 exact frozen C1 reference-inductance cases, spanning 120/198 V, both current directions, 39/51 kΩ typical driver timing, and 4–40 A. Eight retain C1's strict non-ZVS flag and 12 retain its strict ZVS flag. These include hard cases and sampled points close to either side of C1's threshold; the selected currents are actual C1 grid values, not inferred threshold currents. This is a model diagnostic, not a bound on the C1 grid, the D1 board-coupled matrix, or snubber thermal loss.

C2's provisional snubber proxy used ½ × 1 nF × incoming **die VDS²**. The A1/C1 1 nF snubbers are physically represented between the **external** `d_hs–s_hs` and `d_ls–s_ls` deck nodes. C1's frozen waves did not save all those nodes. The [probe deck](probe.cir) copies A1 byte-for-byte except for three added `.save` voltage vectors (`v(d_hs)`, `v(d_ls)`, and `v(s_ls)`; `v(s_hs)` was already saved). It does not add circuit elements or change solver options. The [runner](run_check.py) replays each frozen C1 parameter dictionary with ngspice 45.2 and the pinned Infineon model, at no more than two concurrent processes. [Selected-case provenance](selected_cases.json) records the C1 catalog, source and model hashes, source case/raw hashes, and the probe-deck hash. The simulator's own raw waves and logs are retained under ignored `outputs/runs/`, without vendor-library copies.

At each C1 gate-qualified, sustained-current onset surrogate (die VGS ≥3.5 V and model current ≥max(0.1 A, 0.1×|IL|) for 2 ns), the replay calculates ½CV² from the external capacitor terminals and from die VDS at the **same time**. The new onset agrees with the frozen C1 onset to floating-point precision. These are instantaneous capacitor **stored-energy** estimates, not energy necessarily dissipated in the snubber.

| Exact C1 case | C1 flag | External cap V | External ½CV² | Die-VDS proxy | Proxy / external |
| --- | --- | ---: | ---: | ---: | ---: |
| 120 V, DIR0, 39 kΩ, 4 A | non-ZVS | 108.907 V | 5.93033 µJ | 5.86774 µJ | 0.989 |
| 198 V, DIR0, 39 kΩ, 4 A | non-ZVS | 186.485 V | 17.38841 µJ | 17.26577 µJ | 0.993 |
| 198 V, DIR0, 39 kΩ, 20 A | non-ZVS | 6.634 V | 0.022004 µJ | 0.000292 µJ | 0.0133 |
| 198 V, DIR0, 51 kΩ, 8 A | non-ZVS | 12.987 V | 0.084328 µJ | 0.038959 µJ | 0.462 |
| 120 V, DIR1, 39 kΩ, 40 A | ZVS | 6.853 V | 0.023480 µJ | 0.000418 µJ | 0.0178 |
| 120 V, DIR1, 51 kΩ, 12 A | ZVS | 0.305 V | 0.0000466 µJ | 0.000273 µJ | 5.85 |

The [20-row table](summary.csv) and [full comparison](summary.json) retain every sampled case, signed voltage, energy, source hash, and replay metric. Across these cases, the largest absolute proxy error is **0.12264 µJ** (198 V, DIR0, 39 kΩ, 4 A); the median is **0.00678 µJ**. The largest error is less than **0.95%** of that case's ½ × 1 nF × VBUS² reference energy. Relative error becomes large when the residual voltage and energy approach zero: proxy/external ranges from **0.0133 to 5.85**. Thus die VDS is a poor *relative* surrogate for the external snubber's residual energy near ZVS, even though the absolute difference is small in this selected sample. Use the actual capacitor-terminal voltage in future board-coupled reruns; do not generalize the sample's maximum error to unsampled corners.

Adding these voltage probes changed **none** of the 20 frozen C1 low/high die-VDS peaks, driver-command crossing times, strict ZVS flags, or outgoing model-dissipative turn-off energies: every replayed delta is exactly zero at the saved floating-point precision. All 20 runs completed without simulator aborts and have complete, finite waves. No D1 matrix or preceding resonant half-cycle is represented, so these numbers do not qualify a physical switching or loss budget.

To replay from the A checkout with the frozen C1 worktree available:

```sh
/Users/bennet/Miniforge3/bin/python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/snubber-voltage-check/run_check.py --jobs 2 --c1-root /Users/bennet/.codex/worktrees/ps-r4-c1/temper/zapote/power-stage-120v/validation-results/01-switching-parasitics/round4/c1-zvs
```

The runner fails on a source-hash mismatch, changed probe deck, missing selected C1 case, simulator failure, incomplete/nonfinite wave, changed original metric or classification, or cached raw/log hash mismatch. It reuses the ignored saved probes only when their source and waveform identities still match.

Post-review cache checks also compare the frozen source-wave hash, channel-onset value and simulator version. Historical cases use the original selected-case provenance for their recorded simulator version; new cases record it individually. All 20 cached probe results remain unchanged. The original runner is preserved under ignored `outputs/runs/source-before-review/`.
