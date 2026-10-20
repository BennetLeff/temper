# Stage-53 current-transformer correction

Verified on 2026-10-20 against the user-selected stage-53 board, not the older native-13/native-17 bench plans. This correction supports the probe's independent CT cross-check; it is not a calibration or a powered-test result.

## Board identity and source evidence

Board: `worktrees/runs-native21/s53/c53int/section.kicad_pcb`, relative to the Temper repository root. Its SHA-256 remains:

`82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`.

T1's Value and MPN fields both read **CST3015-200ED**. R39 is **RC1206FR-073RL**, the 3 Ω burden. The board's footprint description and provisional 3D-model filename still mention CST3015-100ED; those metadata do not override the electrical fields.

[Coilcraft documents 1608-1 and 1608-2, revised 2025-09-08](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf) are archived as [`sources/CST3015.pdf`](../sources/CST3015.pdf), with a text extraction beside them. PDF SHA-256:

`0da51f0ee5831b9b633eb10bc8008332e6f461f05f10eacff6d288fdee60bd5f`.

| CST3015-200ED datum | Datasheet value / meaning |
|---|---|
| Turns ratio | 1:200 |
| Secondary inductance | 12.80 mH nominal, ±25%, measured at 1 kHz and 0.1 Vrms |
| Secondary DCR | 5.94 Ω maximum at the stated 25°C conditions |
| Secondary volt-time product | 1276 V·µs, secondary pins 4–3 |
| Listed sensed current | 87 A at a 40°C temperature rise under the specified simultaneous primary/secondary DC-current test; not an absolute maximum or saturation-current boundary |
| Tabulated terminating resistor | 2 Ω gives 1 V output at 100 A primary; it is a scaling example, not a requirement to change this board's 3 Ω burden |
| Family body envelope | 23.0 × 30.0 mm maximum, 15.2 mm maximum height; common family drawing on page 2 |

## Symmetric tank-waveform flux estimate

For `Iprimary = Ipk sin(2πft)`, neglecting magnetizing current and treating the burden as resistive, use the conservative induced-secondary voltage estimate:

`Vs,pk ≈ (Ipk / 200) × (3 Ω + 5.94 Ω)`.

Including winding resistance budgets core excitation beyond the voltage measured only across the burden. The burden capacitor and actual CT transfer function still matter to the measured waveform. Integrating that sinusoidal estimate over one positive half-cycle gives:

`Δ(V·t) = Ipk × 8.94 / (200 × π × f)`.

| Frequency | Primary peak | Half-cycle estimate | Fraction of 1276 V·µs |
|---|---:|---:|---:|
| 35 kHz | 88 A | 35.77 V·µs | 2.80% |
| 35 kHz | 126 A | 51.22 V·µs | 4.01% |
| 60 kHz | 126 A | 29.88 V·µs | 2.34% |

The corrected estimate retains a large volt-time margin for the assumed symmetric waveform. It does not prove absence of saturation under DC bias, flux walk, asymmetric bursts, a disconnected/altered burden, remanent flux, elevated winding temperature or all possible fault waveforms. Nor does it establish thermal suitability for continuous 126 A operation. For comparison, 88 A peak sine is 62.2 Arms; 126 A peak sine is 89.1 Arms, so waveform duration and temperature need their own assessment.

The nominal burden gain remains 15 mV/A: `3 Ω / 200 = 1.5 Ω / 100`. That coincidence does not preserve the old CT's inductance, DCR, flux, phase or reset behavior.

## DC pulses and reset are separate cases

The older double-pulse procedure integrates the complete ramp, freewheel interval and second pulse. If its current shape were applied to the stage-53 CT, the 37 A plateau estimate would be `37/200 × 8.94 = 1.6539 V`. At a 50 V bus, ideal linear ramps to 37 A would consume approximately 61.2, 153.0 and 611.9 V·µs for 100 µH, 250 µH and 1 mH respectively. Each 10 µs of constant 37 A freewheel adds about 16.54 V·µs; the second pulse adds more.

Half of the new tabulated product is 638 V·µs. The 1 mH ramp alone nearly consumes that example half-rating budget, so it is not justified by the larger CT rating. These are conditional arithmetic comparisons, not approval to reuse the native-17 fixture on stage 53 or a newly adopted pulse limit. Re-establish the actual current path, assembled secondary circuit, initial flux, waveform and required margin before setting a test limit.

The simple RL estimate is `τ ≈ 12.8 mH / (3 + 5.94) Ω = 1.43 ms`. It combines nominal inductance with **maximum** DCR, so it is not a worst-case upper bound on reset time. For perspective, the +25% inductance corner and zero winding resistance would give about 5.33 ms with a nominal 3 Ω burden, before burden tolerance, capacitor/clamp dynamics and core nonlinearity. Therefore the historical fixed 10 ms wait is not automatically a stage-53 reset qualification. Measure or model the actual secondary circuit and confirm repeatable reset and waveform response.

## Historical documents and metadata repair

The old `validation-plan/BENCH-SWITCHING.md` explicitly freezes native-17; `validation-plan/05-resonant-tank-envelope.md` identifies native-13, and `sim-kit/02-chain/ct_frontend.cir` models the 1:100 part with 1.5 Ω burden. Preserve those historical identities. The reviewable patch in [`maintenance/stage53-ct-applicability.patch`](../maintenance/stage53-ct-applicability.patch) adds stage-53 applicability notes and corrected arithmetic without relabeling the original fixtures or simulation results. It has not been applied to that separate worktree.

For a future stage-53 producer revision, change T1's footprint description to identify the fitted CST3015-200ED and the common CST3015 family land pattern. Replace the misleading model filename with a verified manufacturer model or a clearly named `CST3015_family_envelope_provisional.step` mechanical surrogate. The common family dimensions support a shared envelope, but do not certify the existing model's shape, lead placement or electrical ratio. The referenced STEP file is not bundled beneath the inspected snapshot's expected `s53/models3d/power-parts/` path, so this record does not claim to have inspected that model.

Make metadata/model-path repairs in the producer source, include the actual model resource, re-export and review the result, and deliberately publish a new baseline with fresh hashes and provenance. Do not edit or repin the current hash-pinned board merely to remove the old name. This correction leaves that board unchanged.
