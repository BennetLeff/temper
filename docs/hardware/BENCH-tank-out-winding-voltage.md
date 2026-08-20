# Bench procedure — `tank-out` winding voltage across T1's primary

**Status:** NOT YET PERFORMED. This procedure exists so that the measurement,
once taken, lands in `elec/tank_out_working_voltage.yaml` and flows into the
insulation classification. Until it does, `scripts/check_tank_out_declaration.py`
exits 6 and `tank-out` stays classified `TANK`.

---

## ⚠ READ THIS FIRST — THE PROBE IS A SAFETY INTERLOCK, NOT A PREFERENCE

**`tank-out` and `PWR_RTN` sit on a mains-referenced, floating bus.**
`PWR_RTN` is the voltage-doubler midpoint (`elec/src/main.ato:247,283`). It is
**not** at earth potential in any way you may rely on. The insulation manifest
declares it at **120 V r.m.s. against earth** on the IEC 60335-1 cl. 29.2
neutral-NOTE basis — no earth credit is taken for the neutral connection —
and on a reversed, non-polarised or faulted outlet it can sit at **full line
potential**.

### If you put a conventional earth-referenced oscilloscope probe on this node

The probe's ground lead bonds the doubler midpoint **directly to protective
earth through the probe ground wire and the scope chassis**. That is a short
across the mains, through a thin signal-return wire, limited only by the
supply's source impedance.

What happens, in order, in well under a second:

- the probe ground lead **fuses and arcs** — it is a few-milliohm wire rated
  for signal return, not fault current, and it is centimetres from your hand;
- the scope's front end is **destroyed**, and the scope chassis is live in the
  interval before anything clears;
- the breaker or RCD may or may not clear it in time, and **it does not clear
  it before the arc**;
- **you are holding the probe.**

This is an equipment-destruction, arc-flash and electrocution hazard. It is
not a data-quality note and it is not recoverable by being careful.

### Therefore — mandatory

Use **either**:

1. a **high-voltage differential probe**, or
2. a **fully isolated oscilloscope** (battery-powered isolated-input
   instrument, or a scope with galvanically isolated channels).

Never an earth-referenced passive probe. Never two earth-referenced probes in
a maths-channel A−B subtraction: both ground leads still bond the bus to earth,
so that arrangement has **exactly the same failure** as one probe.

### Ratings the probe must actually have

The differential quantity is millivolts. **The common mode is not.** Both probe
tips ride the mains-referenced bus, so the probe must survive and reject the
common mode, and that — not the signal — sets the specification.

| Parameter | Requirement | Why |
|---|---|---|
| Common-mode voltage | **≥ 1000 V peak**, CAT II 300 V minimum | `PWR_RTN` reaches ~170 V peak to earth under the declared model, full line potential on a faulted outlet, plus mains transients. |
| Differential range | must survive **≥ 340 V** (the full bus) while resolving **~10 mV** | If a tip slips onto `SW_NODE` or the coil side you are across the whole tank, not the winding. |
| **CMRR at 47 kHz** | **≥ 80 dB; higher is strongly preferred** | See below — this is the hard part. |
| Bandwidth | **≥ 1 MHz** (20 × f_sw); 20 MHz recommended | `scripts/check_tank_out_declaration.py` rejects anything below 20 × f_sw. |

### The CMRR problem — the single most likely way to get a wrong number

You are trying to resolve roughly **40–140 mV** of differential signal sitting
on **~170 V peak** of 47 kHz-modulated common mode. A typical general-purpose
high-voltage differential probe has CMRR of only about **60 dB at 100 kHz**.
At that figure the common-mode feedthrough alone is

```
170 V × 10^(−60/20) ≈ 170 mV
```

— **larger than the quantity being measured.** A probe like that will give you
a confident, repeatable, completely meaningless reading, and it will read
*high*, which pushes the answer toward the expensive conclusion.

**First choice is an optically isolated probe** (IsoVu-class, ~120 dB at
100 kHz) or a fully isolated scope. If you only have a conventional
differential probe, **the common-mode null in Step 6 is not optional** — it is
what tells you whether your instrument can see this signal at all.

### Before you touch anything

- Power the unit through an **isolation transformer** and an **RCD**.
- Assume every exposed conductor in the HV section is live.
- Discharge the bus capacitors and **verify 0 V** before connecting or moving
  any probe. `c_bus1`/`c_bus2` hold charge.
- Connect probes with the unit **de-energised**. Never re-position a probe on
  a live board.
- Work with one hand where practical, and have someone else present.

---

## 1. What is being measured, and why the exact two points matter

`tank-out` is a **two-pad net**: the litz coil's far terminal (`R30` pad 2) and
T1's primary input (`T1` pad 1). Nothing else touches it. It is separated from
`PWR_RTN` by exactly one thing — a single turn of the CST3015-100ED primary
(`elec/src/main.ato:823-824`).

**The quantity of record is the voltage across that single turn:**

> **T1 pad 1 (`tank-out`) referred to T1 pad 2 (`PWR_RTN`)**, as **long-term
> r.m.s.** — the quantity IEC 60664-1 cl. 3.2.1.1 specifies for creepage.
> **Not** peak, **not** peak-to-peak, **not** a cycle mean.

### Physical access

T1 is at board **(53.21, 148.91) mm, rotated 90°, on the top copper layer**
(`F.Cu`). Its primary pads are 9.0 × 4.8 mm SMD lands on 15.36 mm centres:

| Point | Net | Board position | Access |
|---|---|---|---|
| **T1 pad 1** | `tank-out` | **(46.36, 141.23) mm** | Solder fillet / pad extension. The land is 9.0 mm for a 7.36 mm terminal, so **0.82 mm of copper is exposed on each side** of the part body. |
| **T1 pad 2** | `PWR_RTN` | **(46.36, 156.59) mm** | Same — 0.82 mm exposed fillet. |

The silkscreen dot at footprint-local `(12.9, −6.85)` marks **pin 1**; the part
body carries the same dot. Pad 1 is the one **on the dot side**.

**Solder a short wire pigtail to each fillet** while the board is
de-energised, and land the probe on the pigtails. Do not try to hold probe tips
on 0.82 mm of fillet next to a live mains bus.

### Do not substitute R30 pad 2, except as a bound

`R30` pad 2 is the same net, and it is far easier to reach — a Ø8 mm
through-hole pad at **(36.1, 124.48) mm**. But it is **19.7 mm of copper away**
from T1 pad 1. That copper carries the full tank current, and its own
inductance is of the *same order as the quantity being measured* (a 2 cm run is
roughly 10–20 nH, against a CT primary leakage estimated at 5–7 nH).

So a reading taken at R30 pad 2 is an **upper bound that can be several times
the real answer**, not the answer. If you take it, record it as
`v_tank_out_to_pwr_rtn_vrms` **only** if it still passes the falsification
threshold — a bound that passes is informative; a bound that fails proves
nothing.

Likewise, reference **T1 pad 2 specifically**, not some other `PWR_RTN` point.
`PWR_RTN` carries the full tank return current and has its own I·R and L·dI/dt
drops along it. The two pads of the same component is the only pairing that
isolates the winding.

Keep the two pigtails **twisted together** up to the probe head. The loop they
enclose picks up the tank's own field, and at 47 kHz and ~32 A peak a few cm²
of loop will inject millivolts.

---

## 2. Operating condition

The winding drop is **linear in tank current**, so a reading without a recorded
current is a measurement of nothing.

| Setting | Value | Source |
|---|---|---|
| Output power | **1800 W** (the committed operating point) | `docs/evidence/2026-08-15-ocp-threshold-decision.md` §2 |
| Expected tank current | **22.5 A r.m.s. / 31.9 A peak** | same |
| Switching frequency | **≈46.6 kHz** at that point (47 kHz nominal) | `docs/evidence/2026-07-28-coil-selection-research.md` §4.2 |
| Pan | **flat-bottomed cast iron**, fully covering the coil | the committed `cast_iron` preset; pan material sets the loaded inductance and hence the current |

**Confirm the current before trusting the voltage.** Read the board's own
`I_SENSE` (T1's burden, 4.99 Ω on `I_SENSE`, `modules.ato:1703`) or use a
clamp meter on the coil lead. If the tank is not near 22.5 A r.m.s., the
operating point is wrong and the voltage reading does not correspond to the
committed condition — fix that first, and record whatever current you actually
achieved in `measurement.tank_current_arms`.

Let the unit run at power for **≥ 60 s** before capturing, so the coil, pan and
bus have settled. Note that 35.4–40 A is the **superseded OCP *trip* level**,
not an operating current — do not target it.

---

## 3. Scope setup

- **Sample rate ≥ 100 MSa/s** (≳2000 samples per 47 kHz cycle).
- **Bandwidth limit to 20 MHz.** You need ≥ 1 MHz to resolve the waveform, but
  leaving the front end wide open adds broadband noise, and noise **inflates
  r.m.s.** — it biases this measurement toward the expensive answer.
- **DC coupling.** Do not AC-couple. There should be no DC term across a
  winding; if there is one, that is a finding, and AC coupling would hide it.
- Vertical scale: set for the **differential** signal, expected in the tens to
  low hundreds of millivolts. Use the probe's most sensitive range that does
  not clip.
- Capture **≥ 20 complete switching cycles** (≥ 425 µs at 47 kHz).

---

## 4. Procedure

1. **De-energised**: solder pigtails to T1 pad 1 and T1 pad 2 fillets, twist
   them together, dress them away from the coil.
2. **De-energised**: connect the differential probe. Verify the probe is set to
   the intended attenuation and that its CM rating covers the bus.
3. **De-energised**: verify the bus capacitors read 0 V.
4. Energise through the isolation transformer and RCD. Bring the unit to
   **1800 W** with the cast-iron pan. Wait ≥ 60 s.
5. **Record the tank current** (§2).
6. **COMMON-MODE NULL — mandatory control.** With the unit still running at
   full power, move **both** probe tips to the **same** point (T1 pad 2), so
   the true differential input is exactly zero. Capture and record the residual
   r.m.s. This is your measurement's **noise floor**.
   - If the residual is **≥ ⅓ of the reading** you get in step 7, **your
     instrument cannot resolve this signal.** Stop and get a probe with better
     CMRR. Do not report the step-7 number.
   - Record the residual in the evidence document either way.
7. **De-energise**, restore the probe to pad 1 / pad 2, re-energise, return to
   1800 W, wait ≥ 60 s, and capture.
8. Repeat step 7 for **≥ 5 independent captures**, re-energising between them.
9. **De-energise and discharge** before removing anything.

---

## 5. Computing the long-term r.m.s.

The quantity is the **steady-state cyclic r.m.s.**

- Use the scope's **cyclic RMS** (or true RMS gated to an **integer number of
  complete cycles**). A non-integer window leaves a partial cycle in the
  average and biases the result — this is the most common way to get a wrong
  r.m.s. off a scope.
- Compute over **≥ 20 whole cycles**.
- **Do not** report the fundamental-only r.m.s. from an FFT. The tank drive is
  square-edged; the harmonics are part of the working voltage.
- Report the **mean of the ≥ 5 captures**, and record the spread. If the spread
  exceeds ±20 %, the setup is unstable — most likely probe loop pickup or a
  drifting operating point — and must be fixed before the number is usable.
- Record the number **as measured**. Do not subtract the step-6 residual: the
  null is a validity check, not a calibration.

Take the earth-referenced reading (`v_tank_out_to_earth_vrms`) as a **separate
capture**, probe tips on T1 pad 1 and the chassis protective-earth stud. It
will read of order 120 V. It exists to make the manifest's *declared* 120 V
`PWR_RTN`-to-earth figure falsifiable — that figure has never itself been
measured.

---

## 6. What the result means — including what falsifies the prediction

Enter the result in `elec/tank_out_working_voltage.yaml` and run:

```
uv run python scripts/check_tank_out_declaration.py
```

The gate derives the consequence. The thresholds it applies:

| Measured r.m.s., T1 pad 1 → pad 2 | Verdict | Consequence |
|---|---|---|
| **≤ 1.0 V** | `SUPPORTS_MAINS` | Composition against the declared 120 V stays in IEC 60335-1 **Table 17 row ii**. Supports moving `tank-out` to `MAINS`: **4.8 mm** required against **9.100 mm** standing off — T1 passes, and every isolation component on the board is compliant. |
| **> 1.0 V and ≤ 35.0 V** | `CONTESTED` | The row does **not** move (the composition stays in row ii up to `√(125² − 120²) = 35.0 V` exactly), **but this project's own published prediction is falsified.** A human must reconcile it. The gate still fails. |
| **> 35.0 V** | `CONFIRMS_TANK` | The composition leaves row ii. **TANK stands.** T1 is a real blocker: 9.100 mm against ≥ 20.0 mm required, and **no commercially available current transformer clears it** — the category tops out at 9.2 mm. |

### The falsification criterion, stated plainly

`docs/evidence/2026-08-19-t1-sense-node-relocation.md` §5 predicted:

> *"If this exceeds ~1 V, §3 is wrong and the `TANK` classification should
> stand."*

**A steady-state cyclic r.m.s. above 1.0 V at the committed 1800 W operating
point falsifies the MAINS reading.** That is the number to beat. The 1.0 V
figure is **this project's own criterion**, published in advance — it is not a
standards clause and is not presented as one.

### On the ≤ 0.600 V "volt-time" bound — it does not govern this reading

The same document §3.2 bounds the winding at **≤ 0.600 V** from the part's
638 V·µs rating referred through 1:100 over a 10.638 µs half-period.

**That bound applies only to the core-coupled part of the voltage.** A
volt-time product limits *core flux*. The leakage-reactance and DCR components
of the pad-to-pad voltage produce no core flux at all, and the simulation
(`simulation/harness/run_tank_out_winding_voltage.py`) shows the total is
**dominated by leakage**. So a reading between 0.600 V and 1.0 V does **not**
mean the part is outside its rating, and does not by itself falsify anything.
Record it and move on to the 1.0 V criterion.

### There is also a FLOOR — a reading that is too low is a broken measurement

The irreducible resistive part of this voltage is fixed by committed values:
the 4.99 Ω burden and 1.54 Ω secondary DCR referred through 1:100
(`(4.99 + 1.54)/100² = 653 µΩ`), plus the 0.0001 Ω primary DCR. At 22.5 A that
is about **17 mV r.m.s., and it cannot be less.**

**A reading below ~15 mV means your measurement is wrong, not that the answer
is better than hoped.** Check for an open pigtail, a probe on the wrong range,
a probe still in its ÷500 setting, or an operating point far below 1800 W.

### Back out the parameter nobody has published

While you are here, the measurement yields the CST3015-100ED's **primary
leakage inductance**, which appears in no datasheet this repository holds and
which the simulation had to bracket:

```
L_leak ≈ √(V_measured² − V_resistive²) / (2π · f_sw · I_tank)
```

with `V_resistive ≈ 653 µΩ × I_tank`. Record it in the evidence document. The
simulation's geometric estimate was **5–7 nH**, and the 1.0 V criterion
corresponds to roughly **94–144 nH** depending on current — so this single
number is what closes the question for good.

---

## 7. Recording the result

1. Write a dated evidence document under `docs/evidence/` with the scope
   captures, the step-6 common-mode null residual, the achieved operating
   point, and the derived `L_leak`.
2. Fill in the `measurement:` block of `elec/tank_out_working_voltage.yaml`.
3. Recompute the digest:
   ```
   uv run python scripts/check_tank_out_declaration.py --print-digest
   ```
   and paste it into `verification.declared_state_sha256`.
4. Fill in `verification:`. `measured_at_commit` must **resolve** in this
   repository, not merely look like a SHA.
5. Run the gate and expect it to tell you the derived consequence — and to keep
   failing until `elec/insulation_manifest.yaml` has been deliberately moved to
   agree with it. **That failure is the mechanism working.**

**Do not fill this declaration in from the simulation.** A simulation is not a
measurement, and the gate exists precisely so that it cannot be satisfied by an
assumption.
