# Charged parts on the DUT jacks (2026-11-05, revised 2026-11-08)

Datasheet audit items AFE-01 to AFE-04 found that the four BNC jacks have no protection, and Rev F defers protection to Rev G. This study measures the gap. For each way a charged capacitor can meet the jacks, it finds how much voltage the front end takes before a datasheet limit is crossed. It then compares that with a professional meter.

```sh
python3 validation/charged-dut/charged_dut_spice.py --jobs 10      # self-test, then 3,686 transients (~8 min, 10 cores) -> charged-dut.json
python3 validation/charged-dut/charged_dut_spice.py --check-readme # the tables below == tables rendered from charged-dut.json
python3 validation/charged-dut/charged_dut_spice.py --compare REF  # every threshold that differs from the JSON at git REF
python3 validation/charged-dut/charged_dut_spice.py --bench        # bench-esd-knee.json, the bring-up prediction
```

Notes on the run:
- A run that stops before its end time is retried with looser options, then reported as an error rather than counted; the current run has 0 errors.
- The sweep refuses to start unless the self-test passes.
- Every table between `generated` markers is written by `--write-readme`, and `--check-readme` fails if one drifts from the JSON.

## Revision of 2026-11-08 (review of `1a8a11081`)

An independent review found four problems in the first version, now fixed:
1. **Wrong limit used.** The first version judged resistors against a 0.625 W "peak" limit, which is really the 5 s short-time overload. It set three thresholds, including the old "1 V on the L side". Resistor peak power and relay contact current above 2 A have no datasheet pulse figure, so they are now reported as unrated, not judged.
2. **Codec input path missing.** The follower and TIA outputs reach the TAC5112 through the divider, the 1 µF coupling capacitor and the BAT54S clamps to 3V3A. The model now includes that path and judges:
   - the codec pins against −0.3 to 5.656 V;
   - AVDD (3V3A) against 3.9 V;
   - the BAT54S against IFSM 600 mA;
   - the divider parts against their working voltage.
3. **Relay contacts unreported.** The K1–K3 contacts in the RG and RF paths are now reported.
4. **1 kΩ option only run powered.** Option A was simulated with the meter on only. It now runs unpowered too, and its conclusion changes (see below).

The 0.5 V grid point and an ESD-cell sensitivity run are also new. `--compare 1a8a11081` lists all 48 threshold changes. Each traces to one of three causes:
- **Resistor reclassification.** Thresholds that were ended by "peak power > 0.625 W" are now ended by the next real limit:
  - the 100 Ω two-terminal limit goes from 10 to 16 V;
  - the 100 Ω L-side limit goes from 1–2 to 5 V;
  - several unpowered HBM-scale limits rise.
- **3V3A pumping, at 1 µF and 100 µF.** Two-terminal on 5 kΩ / 100 kΩ falls from 16 to 10 V, and with the relays reset two-terminal falls from 16 to 7 V and sense-first from 10 to 7 V.
- **The 0.5 V grid point.** The unpowered ground-referenced "0 V" becomes 0.5 V.

## Method

The circuit is Rev F as built, taken from `cad/design.json`:
- **Source side:** U6A buffer → R104 47 Ω → range resistor (through K1–K3) → HCUR.
- **Current side:** LCUR → R94 22 Ω → TIA (U7A, range feedback resistor through K1–K3, plus C104), with C78 from DUT_LO to GND.
- **Sense side:** HPOT and LPOT go straight to the U6B and U7B follower inputs; R105 and R106 1 kΩ tie them to the current jacks.
- **Codec inputs:** HIGH_BUF → C1P, LOW_BUF → C1M and C2P, TIA_OUT → C2M. Each leg is 1 kΩ into a 1 kΩ + 560 pF divider, then 1 µF to the BAT54S clamp node (D11–D14, to GND and 3V3A), then 470 Ω to a 40 kΩ codec input biased at AVDD/2.

Rails:
- Each LDO sources only, including the AP2112K on 3V3A.
- ±12 V have 5 µF each and the loads from `regulator_check.json`.
- 3V3A has 5 µF and 1.5 mA, the lowest TAC5112 IAVDD in its supply-current table, so it pumps as easily as it can.
- **Unpowered:** every rail starts at 0 V. The relays latch, so an unpowered meter keeps its last range.

Models:
- **OPA2810:** behavioural, with:
  - ESD diodes to both rails (IS 10⁻¹⁵, 2 Ω);
  - a 300 µA differential clamp;
  - GBWP 70 MHz and 187 V/µs;
  - VS − 0.23 V swing;
  - 108 mA short-circuit current.

  TI's macromodel models the ESD cells as 50 Ω switches, which would understate the current.
- **BAT54S:** fitted at or under every maximum VF in its datasheet table.
- **Leads:** 1 m of RG-58 each, as 100 pF plus 0.3 µH and 0.05 Ω.
- **DUT:** the capacitor with 10 mΩ ESR and 5 nH ESL, making contact in 5 ns.

Model checks (`--selftest`, run before every sweep). The last row reproduces audit AFE-07's hand calculation, which checks the codec-path wiring:

<!-- generated:selftest -->
| Check | Model | Datasheet / hand | Pass |
|---|---|---|---|
| BAT54S VF at 0.1 mA | 0.240 V | ≤ 0.24 V | yes |
| BAT54S VF at 1 mA | 0.315 V | ≤ 0.32 V | yes |
| BAT54S VF at 10 mA | 0.399 V | ≤ 0.4 V | yes |
| BAT54S VF at 30 mA | 0.454 V | ≤ 0.5 V | yes |
| BAT54S VF at 100 mA | 0.563 V | ≤ 1 V | yes |
| AFE-07: 11 V step on a follower output, clamp current | 7.04 mA | 6.93 mA | yes |
<!-- /generated -->

| Scenario | What touches the DUT |
|---|---|
| `kelvin` | Kelvin clips: HCUR + HPOT on one terminal, LCUR + LPOT on the other |
| `sense_first` | Only the sense jaws, HPOT and LPOT, have touched yet |
| `current_only` | Two-terminal leads on HCUR and LCUR |
| `h_to_gnd` / `l_to_gnd` | One terminal is ground-referenced, as for a part still in a circuit |

Each scenario runs at:
- **Six meter states:** powered on 100 Ω, 5 kΩ, 100 kΩ and with every relay reset; unpowered on 100 Ω and 100 kΩ.
- **Three capacitances:** 10 nF, 1 µF and 100 µF.
- **Sixteen voltages from 0.5 to 1000 V,** in both polarities.

**Classes.**
- **A, within ratings.** Every datasheet rating holds at every instant:
  - OPA2810: input current ≤ 10 mA, differential input ≤ 7 V, total supply ≤ 28 V;
  - LDO outputs not reversed;
  - TAC5112: pins −0.3 to 5.656 V, AVDD ≤ 3.9 V;
  - BAT54S: ≤ 600 mA;
  - resistors and capacitors within their working voltage.
- **B, HBM-scale.** Only the 10 mA continuous input current is exceeded, and each pin's pulse stays within the HBM pulse the part is rated for (peak ≤ 1.67 A, I²t ≤ 2.1·10⁻⁷ A²s). This is context, not a rating.
- **C.** Anything else.

Reported but not judged:
- OPA2810 output above 40 mA: a long-term electromigration limit (note 4), and the part limits itself at about 100 mA.
- Resistor peak power above 0.625 W, and relay contact current above 2 A: unrated pulses.
- A TAC5112 pin between −0.3 and −0.45 V: the BAT54S negative clamp, audit AFE-07. The clamp node sits at −(0.3–0.4) V whenever a follower or TIA output steps fast negative. That happens in ordinary overloads too, and the audit accepted it with a bench check. Below −0.45 V the case is class C.

## Result: how many volts the meter takes

Class A, with class B in brackets where higher. A range such as "7–10" is the lowest to highest over the powered states (100 Ω, 5 kΩ, 100 kΩ, reset) or the unpowered ones (100 Ω, 100 kΩ):

<!-- generated:thresholds -->
| Scenario | Powered 10 nF | Powered 1 µF | Powered 100 µF | Unpowered 10 nF | Unpowered 1 µF | Unpowered 100 µF | First limit crossed, powered 1 µF |
|---|---|---|---|---|---|---|---|
| `kelvin` | 7 | 7 | 7 | 1 (16) | 1 (3) | 1 (2) | 10 V (100R): u6b Vdiff 7.98 V > 7 |
| `sense_first` | 10 | 7–10 | 7–10 | 1 (13) | 1 (3) | 1 (2) | 10 V (reset): 3V3A 3.30..3.93 V outside TAC5112 AVDD -0.3..3.9 |
| `current_only` | 16 | 7–16 | 7–16 | 1–2 (30) | 1–2 (10–20) | 1–2 (3) | 10 V (reset): 3V3A 3.30..3.93 V outside TAC5112 AVDD -0.3..3.9 |
| `h_to_gnd` | 5 | 5 | 5 | 0.5 (10) | 0.5 (1) | 0.5 (1) | 7 V (100R): u6b Vdiff 9.86 V > 7; u6b input 36.1 mA > 10 |
| `l_to_gnd` | 3–5 | 3–5 | 3–5 | 0.5 (13) | 0.5 (1) | 0.5 (1) | 5 V (5k): u7a Vdiff 8.34 V > 7 |
<!-- /generated -->

<!-- generated:strict -->
Counting the AFE-07 pin excursion as a failure, powered Kelvin falls from 7 V to 2–7 V.
<!-- /generated -->

<!-- generated:unrated -->
In every case counted as class A, the largest resistor pulse is 1.19 W peak (RG, current_only powered/100R 100 uF 16 V; 7.55 mJ dissipated over the whole run, an upper bound on the pulse) and the largest relay contact current is 0 A.
<!-- /generated -->

That pulse has no datasheet rating. It is 1.9 times the 5 s overload power, for about one time constant of 100 µF in the 100 Ω path (tens of ms), and its energy is a fraction of a percent of the 3.1 J that the 5 s overload dissipates.

What the table shows:
- **Powered, Kelvin clips: 7 V on every range and capacitance.** The first limit is the 7 V differential rating of U6B, reached in the first nanoseconds of contact.
- **Unpowered: 1 V with clips, 0.5 V ground-referenced.** With the rails at 0 V, every ESD cell conducts.
- **New: 3V3A.** With the relays reset, or on two-terminal leads at 5 kΩ / 100 kΩ, the codec clamps pump 3V3A past the TAC5112's 3.9 V AVDD limit at 10–13 V (the last safe voltages are 7–10 V). The AP2112K cannot sink. This is the AFE-07 concern, now quantified.

## Bench events (Kelvin clips)

<!-- generated:events -->
| Event | C, V, energy | Powered 100 kΩ | Powered 100 Ω | Unpowered 100 kΩ |
|---|---|---|---|---|
| Film cap left charged by a DMM diode test | 10 nF, 3 V, 45 nJ | A: ESD 0.48 mA, I²t < 1 % of HBM | A: ESD 0.46 mA, I²t < 1 % of HBM | B: ESD 1.2e+02 mA, I²t < 1 % of HBM |
| Ceramic decoupling cap pulled from a live 5 V board | 1 µF, 5 V, 12.5 µJ | A: ESD 0.58 mA, I²t < 1 % of HBM | A: ESD 0.56 mA, I²t < 1 % of HBM | C: ESD 7.3e+02 mA, I²t 4.7× HBM; rails +0.5 / -0.49 V |
| Electrolytic after a 12 V bias test | 100 µF, 12 V, 7.2 mJ | C: ESD 55 mA, I²t < 1 % of HBM; 3V3A 4.04 V | C: ESD 42 mA, I²t < 1 % of HBM | C: ESD 2.4 A, I²t 2.1e+02× HBM; rails +5.09 / -5.01 V |
| Resonant-tank film cap, partly bled | 1 µF, 30 V, 450 µJ | C: ESD 1 A, I²t 9.4× HBM; 3V3A 4.03 V | C: ESD 9.7e+02 mA, I²t 8.6× HBM | C: ESD 6.3 A, I²t 3.5e+02× HBM; rails +4.01 / -4.01 V |
| Resonant-tank film cap straight off a running cooker | 1 µF, 400 V, 80 mJ | C: ESD 84 A, I²t 6.1e+04× HBM; rails +64.8 / -64.7 V; 3V3A 4.64 V | C: ESD 84 A, I²t 6e+04× HBM; rails +64.4 / -64.2 V; 3V3A 4.82 V; relay 2.2 A | C: ESD 89 A, I²t 6.9e+04× HBM; rails +56.4 / -56.3 V |
| Keysight E4980A limit at 2 uF (1 J) | 2 µF, 1000 V, 1 J | C: ESD 2.3e+02 A, I²t 6.4e+05× HBM; rails +226 / -226 V; 3V3A 4.64 V | C: ESD 2.3e+02 A, I²t 6.3e+05× HBM; rails +226 / -224 V; 3V3A 11 V; relay 5.7 A | C: ESD 2.3e+02 A, I²t 6.8e+05× HBM; rails +220 / -219 V |
<!-- /generated -->

**Benchmark.** The Keysight/Agilent E4980A survives a charged capacitor up to 1000 V below 2 µF and √(2/C) V above, which is 1 J ([user manual, Measurement circuit protection, Table 52](https://www.manualsdir.com/manuals/318036/atec-agilent-e4980a.html?page=29)). Rev F's limit is 7 V powered and 0.5–1 V unpowered. At 1 µF and 7 V that is 25 µJ, against 1 J.

At tank-capacitor voltages, the ESD cells steer the charge into the ±12 V rails, and nothing on those rails can sink it:
- At 400 V the rails reach about ±65 V, past the absolute maximum of everything on them.
- The relay contacts carry 2.2 A (400 V) and 5.7 A (1000 V) on the 100 Ω range, against a 2 A continuous carrying rating.
- An LDO whose output is pumped above its input drives current backwards towards the TPS65131. The model does not include that path, so the damage could spread further than shown.

## Protection option A: 1 kΩ in series with each follower input

This is the audit's hedge: DNP footprints in series with HPOT and LPOT, at 1 µF.

<!-- generated:option_a -->
| Scenario | Meter state (1 µF) | Without | With 1 kΩ |
|---|---|---|---|
| `kelvin` | powered/100k | 7 | 7 |
| `sense_first` | powered/100k | 10 | 10 |
| `current_only` | powered/100k | 10 | 10 |
| `h_to_gnd` | powered/100k | 5 | 5 |
| `l_to_gnd` | powered/100k | 3 | 3 |
| `kelvin` | unpowered/100R | 1 (3) | 1 (10) |
| `sense_first` | unpowered/100R | 1 (3) | 10 (30) |
| `current_only` | unpowered/100R | 1 (10) | 1 (10) |
| `h_to_gnd` | unpowered/100R | 0.5 (1) | 2 (16) |
| `l_to_gnd` | unpowered/100R | 0.5 (1) | 0.5 (3) |
| `kelvin` | unpowered/100k | 1 (3) | 1 (20) |
| `sense_first` | unpowered/100k | 1 (3) | 10 (20) |
| `current_only` | unpowered/100k | 2 (20) | 2 (30) |
| `h_to_gnd` | unpowered/100k | 0.5 (1) | 5 (20) |
| `l_to_gnd` | unpowered/100k | 0.5 (1) | 0.5 (3) |
<!-- /generated -->

- **Powered:** it changes nothing. The limit is the step reaching the follower faster than it can slew, and a series resistor into a few pF does not slow that step.
- **Unpowered:** it helps whenever the follower inputs are the path in. Sense jaws first rises from 1 to 10 V, and the H side ground-referenced from 0.5 to 2–5 V.
- **Not with Kelvin clips:** these stay at 1 V. The current jacks reach U7A's input cell through R94 (22 Ω) and U6A's output cell through R104, and the option touches neither path.

Option A alone therefore does not lift the normal-use unpowered limit, and it would still touch the verified follower nodes. It stays out of Rev F. It belongs in the Rev G network, together with a fix for the LCUR and HCUR paths.

## ESD-cell sensitivity (unpowered, 1 µF)

The cells' real forward voltage is not published. The model uses IS 10⁻¹⁵; this run repeats the unpowered rows with a stronger cell, IS 10⁻¹²:

<!-- generated:esd_sensitivity -->
| Scenario | Meter state (1 µF) | IS 1e-15 (VF 0.79 V at 10 mA) | IS 1e-12 (VF 0.62 V) |
|---|---|---|---|
| `kelvin` | unpowered/100R | 1 (3) | 1 (2) |
| `sense_first` | unpowered/100R | 1 (3) | 1 (2) |
| `current_only` | unpowered/100R | 1 (10) | 1 (10) |
| `h_to_gnd` | unpowered/100R | 0.5 (1) | 0.5 (1) |
| `l_to_gnd` | unpowered/100R | 0.5 (1) | 0.5 (1) |
| `kelvin` | unpowered/100k | 1 (3) | 0.5 (2) |
| `sense_first` | unpowered/100k | 1 (3) | 1 (2) |
| `current_only` | unpowered/100k | 2 (20) | 1 (20) |
| `h_to_gnd` | unpowered/100k | 0.5 (1) | 0.5 (1) |
| `l_to_gnd` | unpowered/100k | 0.5 (1) | 0.5 (1) |
<!-- /generated -->

With the stronger cell, unpowered Kelvin on the 100 kΩ range falls to 0.5 V. At 0.5 V every unpowered scenario is within ratings in both models, which sets the discharge rule below.

`--bench` writes the bring-up check of this knee, `bench-esd-knee.json`:
- Leave the meter unpowered and the relays on 100 kΩ.
- Push 1 mA and 5 mA into the HPOT and LPOT centre pins from a current-limited supply. 5 mA is half the 10 mA rating.
- Read the pin and the ±12 V test pads.

The pin-minus-rail difference is the real cell's forward voltage; place it between the two models.

## Decision for Rev F: no board change

Any protection that matters here has to absorb millijoules to joules and send the charge to GND, not to the rails. That means clamps at the jacks, plus a limit on what reaches 3V3A. On DUT_HI, a clamp's capacitance and leakage load the 100 kΩ range: a 1 nF TVS behind 100 kΩ is a 1.6 kHz pole. Doing it properly needs:
- re-extracted parasitics;
- the 360-case stability matrix rerun;
- a new accuracy map.

That is the Rev G study already recorded in the plan.

**Rev F rule, from the tables above:**
1. Power the meter and let it report the 100 kΩ range before connecting anything.
2. Discharge every capacitor through a resistor and confirm **below 0.5 V** with a DMM before clipping on. 0.5 V is within ratings in every scenario, powered or not, for both ESD-cell models. Powered with Kelvin clips, the margin is 14 times.
3. Never measure a part that is still in a circuit or referenced to ground.
4. For tank and bus capacitors, use a discharge resistor rated for the voltage, for example 10 kΩ 5 W. One time constant is 10 ms per µF, and 400 V falls below 0.5 V in seven time constants. Then confirm with the DMM.
5. Wear a grounded wrist strap, and do not touch the BNC centre pins. They go straight to the OPA2810 inputs, whose rating is HBM 2.5 kV; a hand-held discharge (IEC 61000-4-2 contact, 8 kV at level 4) exceeds it.

**Rev G requirements, from this model:**
- **Minimum:** class A powered and unpowered for 1 µF at 30 V (450 µJ, the partly bled tank cap), on every connection pattern, including 3V3A and the TAC5112 pins.
- **Stretch:** the E4980A's 1 J.
- Clamp to GND, never to ±12 V or 3V3A.
- Keep the step at every op-amp input below 7 V differential.
- Limit any ESD-cell current to 10 mA when unpowered: series R ≥ (V_clamp − 0.6 V) / 10 mA, on all four jacks (option A covers only the two sense jacks).
- Relay contacts within 2 A, or rated for the pulse.
- Human ESD on the centre pins: IEC 61000-4-2 contact discharge as a test case.
- Then rerun this script with the new network. Option A in `deck()` shows how to add one.

## Limits of the model

- **Leads:** lumped L and C, not transmission lines.
- **ESD cells:** 2 Ω diodes; the real cells are unpublished. The IS sensitivity and the bench check bound this.
- **Codec pin:** modelled as its 40 kΩ input, with no internal clamp. A real internal diode would hold the pin slightly above the BAT54S clamp node.
- **HBM comparison:** context, not a rating. A longer pulse of equal I²t heats a junction less, so the comparison is conservative for long events.
- **Rails:** the 5 µF of rail capacitance and the resistive rail loads are assumptions, stated in the script.
- **LDO reverse path:** not modelled.
- **Unrated pulses:** resistor and relay pulses are reported, not judged.

None of this changes the conclusion. The limits are a few volts, set by the 7 V differential, 10 mA and 3.9 V AVDD ratings, and they are reached in the first nanoseconds to microseconds of contact.
