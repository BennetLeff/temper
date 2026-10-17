# 02 Protection timing — round 3 result

- Board: `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`.
- Date: 2026-09-27; source/kit revision `44417ae1489fd00e2d652fd3b2c1582b76d17630`; ngspice 45.2; Miniforge Python; Codex GPT-6. Exact hashes are in `outputs/provenance.json`.
- Evidence class: bounded static calculation for stated conditions; distribution-assumed Monte Carlo; simulation/model-based CT transients; datasheet-backed F4/F5 logic.
- Verdict: **FAIL** task-02's 44 A minimum shunt OCP criterion at adverse +85°C corners; **BLOCKED** for a guaranteed gate-off/device-survival verdict. F5 slow HOT5 fall is **not proven fail-safe**.

## Summary

The full **108-case CT grid** ran as 18 analog transients × three offsets × two fixed-delay settings. The three formerly stalled original-deck cases complete with a 2.5 ns maximum step and no solver tolerance relaxation. Three prior case families agree within 0.00613%; halving the analog step changes a crossing by at most 0.00721 ns. These establish numerical consistency of the kit's ideal comparator/delay model.

Static corners with **assumed R5 +50°C self-heating** give **38.44–85.55 A** shunt OCP, **50.56–60.01 A** CT (either polarity), and **272.09–288.02 V** OVP. The shunt minimum is 5.56 A below the 44 A criterion; its maximum leaves only 2.45 A before T1's 88 A rating, without delay or gate-discharge overshoot. The failure occurs at the specified +85°C board corner, independently of the −10°C regulator-range gap.

## Method and assumptions

`thresholds.py` validates exact BOM MPNs and relevant pin/net endpoints. R32/R33 form the Kelvin OCP midpoint; R34/R35 form its threshold. Algebra gives `Itrip = [Vref·R33/R32 − (Vref·R35/(R34+R35)+VOS)·(1+R33/R32)]/R5`, or **60.9756 A − 2000·VOS** nominal. U7 compares the four 470 kΩ / R30 bus divider against R36/R37's REF25 fraction, giving 279.970 V nominal. Static CT transfer uses the ideal 1:100 ratio and R39=1.5 Ω, **15 mV per primary ampere**. C42 filtering, CT magnetization and clamp dynamics belong only to the separate transient deck; static CT bands assume ideal transfer.

The extreme calculation enumerates every relevant resistor vertex independently at −10 and +85°C, with ±0.1%/25 ppm/°C RT parts, ±1%/100 ppm/°C high-value RC parts, **±1%/200 ppm/°C R39 at 1.5 Ω**, and **±1%/250 ppm/°C R5 at 1 mΩ**. It includes TLV3201 ±4 mV over-temperature offset and adverse 5 nA bias on each input through source resistance; LM4040 A25I full-range ±19 mV plus ±1 mV current/load allowance; and CT 3.135–3.465 V SELV range. BAS116H's 80 nA limit at 75 V pulsed, 150°C is represented as ±80 µV across R42. The selected HOT5 regulator is specified from 0 to 125°C, so the −10°C corner is a conditional extrapolation; the +85°C failure is within its range. Exact source conditions are in `sources/README.md`.

The 100,000-sample Monte Carlo (`seed=320102`) samples board temperature uniformly −10..85°C, R5 at board temperature plus **assumed 50°C**, resistor tolerance/TCR uniformly and independently, and each IC offset/initial error normally with 3σ at its stated limit, clipped there. Comparator offsets are sampled separately per path. These distribution assumptions do not supersede extreme-value bounds. A6 can replace R5's 50°C rise and rerun the script.

`run_ct.py` retains the kit's CT/secondary/burden/C42/bias/R42/generic-clamp analog network. The ideal tanh comparator's midrail crossing equals the analog threshold; the transmission-line delays are feed-forward and do not load or feed back into the analog network. They are added after threshold extraction. This equivalence was checked against the original deck. Every analog run reached 200 µs and has a transcript. The fixed 45/55 ns setting is a **model parameter**, not a physical small-overdrive guarantee.

## Results

| Quantity | Result | Evidence |
| --- | ---: | --- |
| Shunt OCP static, +85°C board/R5 +50°C | **38.44–85.55 A** | `outputs/thresholds.json` |
| CT static, either polarity, 3.135–3.465 V SELV | **50.56–60.01 A** | `outputs/thresholds.json` |
| Bus OVP static | **272.09–288.02 V** | `outputs/thresholds.json` |
| 100k MC shunt 0.1 / 99.9 percentile | 50.91 / 71.27 A | `outputs/thresholds.json` |
| 100k MC CT positive 0.1 / 99.9 percentile | 51.79 / 58.61 A | `outputs/thresholds.json` |
| 100k MC OVP 0.1 / 99.9 percentile | 277.20 / 282.78 V | `outputs/thresholds.json` |
| CT constant-delay model, max absolute current at OR | 59.87 A | `outputs/summary.json` |
| Previous-reference maximum crossing difference | 0.0922 ns; 0.000378% | `outputs/reference_comparisons.json` |
| Kit smoke third-case maximum difference | 0.00613% | `outputs/reference_comparisons.json` |
| Five-to-2.5-ns crossing change | 0.00721 ns | `outputs/timestep.json` |

For 106 modeled CT rows, the interval from the first nominal 55.17 A absolute-current crossing to OR is 71.0–336.3 ns. In two 39 kHz, 10 A, 1 MA/s, −4 mV rows, offset causes a trip on an **earlier negative lobe**, while the nominal 55.17 A reference first occurs on a later positive lobe. The subtraction is −10.26 µs and is **not a causal negative delay**. `outputs/reference-lobe.png` and `outputs/summary.json` retain these cases; they must not enter a shutdown sum.

## Sensitivity

[TI TLV3201 SBOS561C §§6.6, 6.9](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) states **55 ns maximum** at **20 mV overdrive and 15 pF load**, with typical curves beginning at 20 mV. The specified driven-transition condition does not guarantee 55 ns for an arbitrary slow ramp that first reaches 20 mV. `outputs/overdrive_bound.csv` therefore labels `20 mV + 55 ns` as a **conditional step-test extrapolation, not guaranteed ramp timing**. The 45/55 ns model columns are separate. Nominal shunt gain is 0.5 mV/A, so 20 mV requires another 40 A before filter lag; nominal CT gain is 15 mV/A, so it requires another 1.33 A, but a sinusoidal waveform may defer this to a later lobe.

At 3 MA/s and zero offset the shunt's conditional calculation reaches about **102.64 A** before downstream gate-off; at 1 MA/s, **101.53 A**. At an imposed 1 GA/s ramp the filter model reaches about 410 A. These are conditional modeled currents, not certified device-current bounds. All 108 CT plus 25 shunt rows are retained in the CSV. `stall_diagnosis.md` gives the one-at-a-time solver experiments.

`f4_f5.md` lists each input/output and its guaranteed supply range. For F4, the watchdog clears PERMIT if WDI stops, but its specified timeout is 0.9–2.5 s; one PWM stuck high is not immediately protected. UCC21550's 39 kΩ DT interlock forces both outputs low if **both** inputs are high. For F5, REF25 worst-case regulation requires HOT5 about ≥4.52 V while ISO7710's non-F default-high applies when its input side is ≤1.7 V with SELV valid. No path guarantees BUS_FAULT high across the intervening slow-fall region. HOT5 loss need not collapse the driver's independent 15 V output supply.

## Open items and physical confirmation

The static shunt nuisance finding needs a design-owner decision; this validation did not edit the board or source. B2 still needs B1's board-bound gate turn-off waveform, a qualified comparator small-overdrive/ramp latency, and downstream interlock/PERMIT timing to determine F2 current at actual gate-off and F3 returned-energy voltage. The CT deck still has a generic BAS116H-like clamp model. F4 single-stuck-PWM exposure and F5 HOT5 brownout require whole-chain tests or a justified independent shutdown path. The bench test should inject current over temperature/supply corners and measure input crossing, BUS_FAULT, PERMIT, driver output, MOSFET gate, current and VDS simultaneously.

## Reproduce

From `zapote/power-stage-120v` with the ignored vendor model in `validation-plan/sim-kit/models/vendor/`, its hash checked against `outputs/provenance.json`:

```sh
cd validation-plan/sim-kit && python3 smoke_test.py
cd ../..
python3 validation-results/02-protection-timing/round3/diagnose_stalls.py
python3 validation-results/02-protection-timing/round3/run_ct.py
python3 validation-results/02-protection-timing/round3/verify_ct.py
python3 validation-results/02-protection-timing/round3/verify_references.py
python3 validation-results/02-protection-timing/round3/overdrive_bound.py
/Users/bennet/Miniforge3/bin/python3 validation-results/02-protection-timing/round3/thresholds.py
python3 validation-results/02-protection-timing/round3/summarize.py
python3 validation-results/02-protection-timing/round3/provenance.py
```

`outputs/smoke_test_own.txt`, `outputs/run_ct_stdout.txt`, the original-deck stall logs, analog logs, selected compressed raw waveforms, `outputs/frontend_sweep.json`, and all scripts are retained beside this report.
