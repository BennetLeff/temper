# Keep only 1000:1 — worthwhile simplification, conditional measurement fit

Research, 2026-10-20; no circuit/BOM/CAD changes. Basis: this probe's README, design/circuit records, BOM, `tools/layout.rs`, and archived `validation/spice/probe_lv.inc`. Rev B has 2000:1 input dividers, a fixed ×2 subtractor and an additional ×5 branch: “×10 overall” currently means **200:1**, not 100:1.

## Verdict

**Prefer one 1000:1 range for the several-hundred-volt coil/capacitor waveform, provided the actual scope passes the experiment below.** Its strongest benefits are fewer parts, one calibration, and removal of an unused saturated amplifier. Keep the fine option if small differential voltages or single-cycle phase near startup/current zero are important. Dropping it provides little direct enclosure shrink because HV geometry dominates.

“300 V becomes 0.3 V, ample on any scope at 50 mV/div” needs an amplitude convention: 300 Vpp occupies six divisions; 300 Vpk becomes 0.6 Vpp and occupies twelve. An eight-division display then needs ≥75 mV/div, normally 100 mV/div. Visibility alone establishes neither accuracy nor phase resolution.

## Analog noise estimate

Use 300 K, uncorrelated sources and datasheet typical flatband densities. [ADA4817](https://www.analog.com/media/en/technical-documentation/data-sheets/ADA4817-1_4817-2.pdf) specifies 4 nV/√Hz and 2.5 fA/√Hz at 100 kHz. [OPA810](https://www.ti.com/lit/ds/symlink/opa810.pdf) specifies 6.3 nV/√Hz at 500 kHz and 5 fA/√Hz at 10 kHz; its low-frequency noise rises. These calculations extrapolate those points; they are not guaranteed spectra.

With the source shorted, each compensated divider presents approximately

`Ztap = 5000 Ω / (1 + j·2πf·5000 Ω·13.2 nF)`.

The equivalent upper-string capacitance contributes approximately 6.6 pF alongside the low leg. Crucially, Johnson noise is `sqrt(4kT·Re(Ztap))`, not `sqrt(4kT·|Ztap|)`.

| Frequency | Magnitude of Ztap | Divider thermal density, per tap |
|---|---:|---:|
| 35 kHz | 344 Ω | 0.626 nV/√Hz |
| 60 kHz | 201 Ω | 0.366 nV/√Hz |
| 5 MHz | 2.41 Ω | 0.00439 nV/√Hz |

Including each 220 Ω input resistor, ADA current-noise voltage is only 0.00105/0.00076/0.00055 nV/√Hz at those frequencies. The 220 Ω resistor's own thermal noise is 1.91 nV/√Hz. Thus neither an unfiltered 5 kΩ thermal estimate nor a current-noise argument justifies the fine stage.

Before output filtering, contributions at the wide output are approximately: two ADA voltage sources 11.31; two 220 Ω resistors 5.40; all six subtractor resistors 9.96; U3 voltage noise 18.9 (noise gain **3**, signal gain 2); U4 voltage noise 6.3 nV/√Hz. OPA current noise through sub-kΩ impedances is below 0.01 nV/√Hz. Filter/output resistors add about 1–2 nV/√Hz. RSS is approximately **26 nV/√Hz**, or **26 µV/√Hz input referred** in the tank band.

A rectangular 35–60 kHz analysis band gives approximately 4 mVrms input noise; rectangular DC–5 MHz gives approximately 57 mVrms. These are illustrative integrals, excluding low-frequency excess noise, interference and common-mode conversion; the real output filter reduces upstream broadband noise, while U4 noise is downstream. A 5 MHz bandwidth is not brick-wall: measure actual integrated noise. The fine stage largely preserves upstream input-referred noise while reducing the scope contribution fivefold at the same scope settings.

## Scope and phase limits

For an illustrative eight-division ADC span at 50 mV/div:

| ADC | Scope LSB | 1000:1 input LSB | Ideal quantization RMS, input |
|---|---:|---:|---:|
| 8 bit | 1.56 mV | 1.56 V | 0.451 V |
| 12 bit | 97.7 µV | 97.7 mV | 28.2 mV |

Actual ADC span/overscan differs. `LSB/√12` assumes adequately distributed quantization error. Scope noise already includes digitization; do not add quantization again to a published measured total.

The primary [Siglent SDS1000X-E datasheet](https://int.siglent.com/u_file/download/25_04_27/SDS1000X-E_DataSheet_EN04H.pdf) specifies 8 bits and noise ≤0.1 division at ≥2 mV/div: a loose **≤5 mVrms** bound at 50 mV/div, equivalent to 5 V here. The [Tek 5 Series B datasheet](https://www.tek.com/fr/datasheet/5-series-b-mso-mixed-signal-oscilloscope-datasheet) specifies 12-bit ADCs; its <2 GHz models list typical **207 µVrms**, 1 MΩ, 20 MHz, High Res at 50 mV/div: 0.207 V input equivalent. These are different modes/bandwidths, not a controlled comparison or a 5 MHz guarantee. The probe's filter cannot remove noise generated inside the scope.

For a sine, zero-crossing noise gives approximately `σphase = σV/Vpk` radians. At 1 V input-equivalent noise, 300 Vpk yields 0.19°; 10 Vpk yields 5.7°. At 60 kHz, 1° is 46 ns. Voltage/current phase also needs CT delay calibration; this probe does not measure current. Averaging helps repetitive noise, but not single-cycle transients or systematic common-mode error: 1 kV common mode at 60 dB CMRR already permits 1 V error, independent of range.

## Concrete simplification and experiment

Remove U12, C96/C97, R67/R68/R97–R99, R100–R103, SW1 and its wire landing/harness: **13 BOM components**, including one offboard switch. Retain U3/U4, R70 and overload circuitry. U12 removal saves about 3.7 mA per rail, approximately 36 mW at ±4.8 V. The U12 cell around x180–215/y17–35 spans roughly 630 mm², only 3% of the 20,160 mm² board; this bounding rectangle is not guaranteed reclaimable area.

Hardwire RAW_OUT to the filter/detector. Removing R101 changes the 180 pF filter pole from 6.00 to **9.06 MHz**; approximately 272 pF restores 6 MHz (270 pF gives 6.04 MHz). Removing only R103 barely changes loading; retain R71/R72 for U6. Detector loading removal would require redesign, not simple deletion. Recalculate gain, bandwidth and phase; the existing simulation is not this variant. Retain nominal 1.406 kV/tip and 1.266 kV differential warnings, the wide analog-zero requirement and clipping qualification; delete fine-specific thresholds/offset allowances. Unused-U12 saturation disappears; upstream overload does not.

On the intended scope, compare grounded-input spectra/RMS, then 10/20/300 V-equivalent signals at 35/45/60 kHz and 5 MHz using low-voltage fixtures. Compare 1000:1 against the existing fine path with optimal scale, fixed bandwidth and raw versus averaged acquisitions. Require measured ≤2% amplitude and ≤1° residual voltage/current phase at the smallest wanted signal, plus overload recovery. Decide from that scope-specific evidence before deleting hardware.
