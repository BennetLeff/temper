# Charged parts on the DUT jacks (2026-11-05)

Datasheet audit items AFE-01 to AFE-04 found that the four BNC jacks have no protection, and Rev F defers protection to Rev G. This study measures the gap. For each way a charged capacitor can meet the jacks, it finds how much voltage the front end can take before a datasheet limit is crossed. It then compares that with a professional meter.

Run it with `python3 validation/charged-dut/charged_dut_spice.py` (needs ngspice). It runs 2,766 transient cases in about 2 minutes on 10 cores, with 0 solver errors, and writes `charged-dut.json`. Any run that stops before its end time is retried with looser options, then reported as an error rather than counted.

## Method

The circuit is Rev F as built, taken from `cad/design.json`:
- **Source side:** U6A buffer → R104 47 Ω → range resistor → HCUR.
- **Current side:** LCUR → R94 22 Ω → TIA (U7A, range feedback resistor plus C104), with C78 from DUT_LO to GND.
- **Sense side:** HPOT and LPOT go straight to the U6B and U7B follower inputs; R105 and R106 1 kΩ tie them to the current jacks.

Rails:
- Each LDO can source current but cannot sink it.
- Each rail has 5 µF of capacitance and the loads from `regulator_check.json`.
- **Unpowered:** the rails start at 0 V. The relays latch, so an unpowered meter keeps its last range.

The op-amp model is behavioural:
- ESD diodes to both rails, with 2 Ω series resistance.
- A 300 µA differential clamp.
- GBWP 70 MHz and slew rate 187 V/µs.
- Output swing of VS − 0.23 V, and 108 mA short-circuit current drawn from the rail it flows from.

TI's macromodel is not used: it models the ESD cells as 50 Ω switches, which would understate the current.

Leads and DUT:
- **Leads:** 1 m of RG-58 each, as 100 pF plus 0.3 µH and 0.05 Ω.
- **DUT:** the capacitor with 10 mΩ ESR and 5 nH ESL, making contact in 5 ns.

Connections modelled:

| Scenario | What touches the DUT |
|---|---|
| `kelvin` | Kelvin clips: HCUR + HPOT on one terminal, LCUR + LPOT on the other |
| `sense_first` | Only the sense jaws, HPOT and LPOT, have touched yet |
| `current_only` | Two-terminal leads on HCUR and LCUR |
| `h_to_gnd` / `l_to_gnd` | One terminal is ground-referenced, as for a part still in a circuit |

Each case runs at:
- **Six meter states:** powered on 100 Ω, 5 kΩ, 100 kΩ and with all relays reset; unpowered on 100 Ω and 100 kΩ.
- **Three capacitances:** 10 nF, 1 µF and 100 µF.
- **Fifteen voltages from 1 to 1000 V,** in both polarities.

**Classes.**
- **A, within ratings.** Every OPA2810 limit holds (SBOS789C 7.1):
  - input current ≤ 10 mA;
  - differential input ≤ 7 V;
  - total supply ≤ 28 V;
  - LDO outputs not reversed.

  Resistors stay within their working voltage and at or under 0.625 W peak; that is the 5 s short-time overload, the only overload figure either resistor datasheet gives. The capacitors stay within 50 V.

  An output current above 40 mA is reported but not judged. Note 4 of the datasheet makes 40 mA a long-term electromigration limit, and the part limits its own output at about 100 mA.
- **B, HBM-scale.** Only the 10 mA continuous input current is exceeded, and every pin's pulse stays within the HBM pulse the part is rated for: peak ≤ 1.67 A and I²t ≤ 2.1·10⁻⁷ A²s. This is context, not a rating.
- **C.** Anything else.

## Result: how many volts the meter takes (class A; class B in brackets where higher)

| Scenario | Powered, 1 µF | Powered, 100 µF | Unpowered, 1 µF | What ends it |
|---|---|---|---|---|
| Kelvin clips | **7 V** (every range) | 7 V | 1 V (3) | 10 V: the contact step drives U6B to 8.4–9 V differential. The datasheet covers steps up to 7 V |
| Sense jaws first | 10 V | 10 V | 1 V (3) | 13 V: both followers about 8.6 V differential |
| Two-terminal | 10 V (100 Ω), 16 V | 10 / 16 V | 1–2 V (10–16) | R105 0.64 W, TIA differential 8.4 V |
| Ground-referenced, H side | 5 V | 5 V | 0 V (1) | U6B differential, ESD current |
| Ground-referenced, L side | 1 V (100 Ω), 3 V | 1–3 V | 0 V (1) | 100 Ω range: R43 0.81 W peak at 2 V, because the TIA sinks V/22 Ω |

10 nF behaves like 1 µF when powered, and is HBM-scale up to 10–13 V when unpowered. All 90 rows (5 scenarios × 6 states × 3 capacitances) are in `charged-dut.json` `safe_voltage`.

**Unpowered is the weak state.** With the rails at 0 V, every ESD cell conducts at about 0.6 V. A 1 µF capacitor at 5 V puts a 0.73 A peak into U6B's input cell for 14 µs, 4.7 times the HBM I²t, and charges both rails to ±0.5 V.

## Bench events (Kelvin clips)

| Event | C, V, energy | Powered 100 kΩ | Powered 100 Ω | Unpowered |
|---|---|---|---|---|
| Film cap left charged by a DMM diode test | 10 nF, 3 V, 45 nJ | A | A | B (124 mA for 0.2 µs) |
| Ceramic cap pulled from a live 5 V board | 1 µF, 5 V, 12.5 µJ | A | A | C (0.73 A, 4.7× HBM I²t) |
| Electrolytic after a 12 V bias test | 100 µF, 12 V, 7.2 mJ | C (U6B 9.6 V differential) | C (+ R43 0.92 W) | C (2.4 A for 34 ms, rails to ±5 V) |
| Tank film cap, partly bled | 1 µF, 30 V, 0.45 mJ | C (1.0 A ESD for 100 µs, 9× HBM) | C | C (6.3 A) |
| Tank film cap straight off a running cooker | 1 µF, 400 V, 80 mJ | C: **the ±12 V rails pump to ±65 V** | C | C: rails to ±56 V |
| Keysight E4980A rating at 2 µF | 2 µF, 1000 V, 1 J | C: rails to ±226 V | C | C |

**Benchmark.** The Keysight/Agilent E4980A survives a charged capacitor up to 1000 V below 2 µF and √(2/C) V above, which is 1 J ([user manual, Measurement circuit protection, Table 52](https://www.manualsdir.com/manuals/318036/atec-agilent-e4980a.html?page=29)). Rev F's limit is 7 V powered and 1 V unpowered, at any capacitance. At 1 µF that is 25 µJ against 1 J, more than four orders of magnitude apart.

At tank-capacitor voltages, the ESD cells steer the charge into the ±12 V rails, and nothing on those rails can sink it.
- At 400 V the rails reach ±65 V. That is past the absolute maximum of every part on them: both OPA2810s (28 V total), the OPA197, and the TPS7A49 and TPS7A30.
- A rail above its LDO's input also drives current backwards towards the TPS65131 output. The model does not include that path, so the damage could spread further than shown.

## Protection option tested and rejected for Rev F

**Series 1 kΩ at the HPOT and LPOT follower inputs** (the audit's DNP-footprint hedge): at 1 µF on the 100 kΩ range, the Kelvin limit stays at 7 V and the sense-first limit at 10 V. What limits the powered case is the step reaching the follower faster than it can slew. A series resistor into a few pF does not slow that step, so the hedge buys nothing here. It would still touch the verified follower nodes.

## Decision for Rev F: no board change

Any protection that matters here has to absorb millijoules to joules and send the charge to GND, not to the rails. That means clamps at the jacks. On DUT_HI, a clamp's capacitance and leakage load the 100 kΩ range: a 1 nF TVS behind 100 kΩ is a 1.6 kHz pole. Doing it properly needs:
- re-extracted parasitics;
- the 360-case stability matrix rerun;
- a new accuracy map.

That is the Rev G study already recorded in the plan.

**Rev F rule, from the table above:**
1. Power the meter and let it report the 100 kΩ range before connecting anything. Unpowered, the limit is about 1 V.
2. Discharge every capacitor through a resistor and confirm **below 1 V** with a DMM before clipping on. 1 V is within ratings in every powered scenario; the lowest powered threshold is 1 V, on the ground-referenced L side.
3. Never measure a part that is still in a circuit or referenced to ground.
4. For tank and bus capacitors, use a discharge resistor rated for the voltage, for example 10 kΩ 5 W. One time constant is 10 ms per µF, and 400 V falls below 1 V in six time constants. Then confirm with the DMM.

**Rev G requirements, from this model:**
- **Minimum:** class A powered and unpowered for 1 µF at 30 V (450 µJ, the partly bled tank cap).
- **Stretch:** the E4980A's 1 J.
- Clamp to GND, never to ±12 V.
- Keep the step at every op-amp input below 7 V differential.
- Limit any ESD-cell current to 10 mA when unpowered: series R ≥ (V_clamp − 0.6 V) / 10 mA.
- Then rerun this script with the new network. Option A in `deck()` shows how to add one.

## Limits of the model

- **Leads.** The leads are lumped L and C, not transmission lines.
- **ESD cells.** They are 2 Ω diodes; the real cells are unpublished.
- **HBM comparison.** It is context, not a rating. A longer pulse of equal I²t heats a junction less, so the comparison is conservative for the long events.
- **Rails.** The 5 µF of rail capacitance and the resistive rail loads are assumptions, stated in the script.
- **LDO reverse path.** Not modelled.

None of this changes the conclusion: the limits are a few volts, set by the 7 V differential and 10 mA ratings, and are reached on the first nanoseconds of contact.
