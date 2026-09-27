# 02 — Protection timing and trip-threshold spread

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first. This task needs task 01's loop inductance and fault turn-off
waveform. If 01 isn't done, use its analytic range (10–40 nH) and mark the
result provisional.

## Goal

Answer three questions with worst-case numbers:

1. **Threshold spread.** Over all tolerance and temperature corners, where do
   the over-current trip (nominal ≈ 61 A) and the over-voltage trip (nominal
   ≈ 280 V) actually land? Can normal operation (37 A tank peak, up to 198 V
   bus) cause a nuisance trip?
2. **Response time.** How long from the fault crossing the threshold until the
   MOSFET gates are off? This is the total chain delay.
3. **Survival.** For each fault scenario, is the current or voltage reached at
   that moment within the device ratings? If a fault is too fast for this
   hardware to stop, say so plainly. That's a key finding, not a failure of
   the task.

Evidence class: **bounded calculation** for the threshold worst case and the
delay sum; **simulation/model-based** for the waveforms. The physical test
that confirms it is the bench OCP trip test with injected current and a
measured trip-to-gate-off delay (POWER-SECTION.md §7 item 6).

## The protection chain

Trace every link in `frozen/default.net` before trusting this summary. It
comes from POWER-SECTION.md and FAULT-INTERFACE.md.

**Over-current (OCP):**

- **Sensing:** R5 is a 1 mΩ 4-terminal shunt (WSK2512R0010FEA) in the common
  low-side return. Pad 2 is the Kelvin `leg_ret` pickup and pad 3 is
  `ocp_kelvin_n`.
- **Filter and threshold:** R33, R32 and C30 (10 kΩ 0.1 %, 100 pF C0G) form
  the `ocp_node` filter. R34/R35 (10.5 kΩ / 10 kΩ 0.1 %) and C31 (1 nF)
  divide `ref25` down to `ocp_thresh`.
- **Reference:** U5 is an LM4040A25 (2.5 V), biased by R31 (5.6 kΩ) from
  `hot5`, the 5 V from U3 MC78L05.
- **Comparator:** U6 is a TLV3201AIDBVR; its output is `ocp_ok_hot`.

**Over-voltage (OVP):**

- **Divider:** R26–R29 (4 × 470 kΩ) on top, R30 (15.8 kΩ 0.1 %) on the bottom,
  giving `vsense_in`, filtered by C27 (1 nF).
- **Threshold:** R36/R37 (10 kΩ / 140 kΩ 0.1 %) from `ref25` set
  `ovp_thresh`, with C33 (1 nF).
- **Comparator:** U7 is a TLV3201; its output is `ovp_ok_hot`.

**Combining and isolation:**

1. U8 (SN74LVC1G00, NAND) combines the two OK signals.
2. U9 (ISO7710DWR, non-F, default-high) carries the result across the barrier.
3. The output is J4.10 `BUS_FAULT`, high on a fault.

**Shutdown:**

1. `BUS_FAULT` goes to the interlock board (`zapote/interlock/INTERFACES.md`).
2. The interlock removes `PERMIT` (J4.9).
3. The permit FETs Q1/Q4 (AO3400A) act on the driver disable nets
   (`leg_a-dis`, `leg_b-dis`, `*-permit_gate`).
4. UCC21550 outputs go low and the MOSFETs turn off.

Also read `ORACLE-REVIEW.md`, `DC-LINK-CLAMP.md`, `REFERENCE-BIAS.md` and
`tools/bus_voltage_sim.py`. The existing bus simulation assumes a flat 300 ns
trip delay and absolute tank-current sensing. This task replaces that
assumption with the real chain.

## Datasheets needed

Record the URL, revision and page for each value.

| Part | Values |
| --- | --- |
| TLV3201 | Offset (max over temperature), propagation delay vs overdrive, output levels at 5 V |
| LM4040A25 | Initial accuracy, tempco, minimum cathode current |
| Resistors | Tolerance and TCR (0.1 % RT0603 series; 1 % RC series) |
| WSK2512R0010FEA | Tolerance and TCR |
| SN74LVC1G00 | tpd at 5 V |
| ISO7710 | Propagation delay and default output |
| AO3400A | Switching times at the actual gate drive |
| UCC21550 | DIS/EN-to-output delay, propagation delay, UVLO; **whether both outputs are forced low when both inputs are high** (dead-time/interlock mode) |
| IPW65R018CFD7 | ID,pulse, SOA curves, transient thermal impedance, whether a short-circuit withstand time is specified |
| Interlock board | Its input-to-PERMIT latency, from `zapote/interlock/` docs (if absent, BLOCKED for that link: state it) |

## Step 1: threshold spread

Write `scripts/thresholds.py`:

1. Derive `ocp_thresh`, `ocp_node` and the trip current symbolically from the
   actual resistor network in the netlist. Include the Kelvin offset network
   (R32/R33) exactly as connected. Cross-check the nominal result against the
   documented ≈ 61 A. **If it disagrees by more than 2 %, stop and report.**
2. Do the same for OVP (documented ≈ 280 V).
3. **Extreme-value worst case:** every tolerance at the adverse limit, at
   board temperatures of −10 °C and +85 °C (use the TCRs and tempcos). Include:
   - comparator offset
   - LM4040 initial accuracy plus tempco
   - resistor tolerance plus TCR
   - shunt tolerance plus TCR
   - the effect of the shunt's own heating: take its power from task 03 if
     available; otherwise assume +50 °C and say so
4. **Monte Carlo:** 100,000 samples, with uniform distributions for
   resistors and gaussian (3σ at the limit) for ICs. Report the 0.1 % and
   99.9 % points.
5. Output `outputs/thresholds.json` and a short table.

## Step 2: delay budget

Build `outputs/delay_budget.csv`. Give one row per link, with typical and
maximum values and the source of each:

| Link | Value |
| --- | --- |
| Current reaches threshold → `ocp_node` crosses `ocp_thresh` | Filter delay; depends on di/dt. Compute in step 3 |
| TLV3201 propagation | At the overdrive found in step 3 |
| NAND tpd | |
| ISO7710 propagation | |
| Interlock board: BUS_FAULT → PERMIT low | |
| PERMIT → permit FET → driver disable | AO3400A plus RC on the gate net |
| UCC21550 disable → output low | |
| Gate discharge to below VGS(th) | Through 3.9 Ω plus the driver pull-down, from the task 01 model |

Report the total at typical and maximum.

## Step 3: fault scenarios

Use ngspice. Reuse task 01's deck, adding the RC filter and a behavioural
comparator with the datasheet offset and delay. For each scenario, find the
current or voltage at the moment the gates are actually off.

| ID | Scenario | Model |
| --- | --- | --- |
| F1 | **Hard shoot-through**: both devices of one leg on, from a driver fault or dead-time loss | Current rises at ≈ V_bus / L_loop (tens of A per ns). Show when 61 A is crossed vs when protection acts. Then check whether the UCC21550 input interlock prevents this state; that's the real protection |
| F2 | **Tank over-current**: pan removed, or driving at resonance | Tank current ramps at ≈ V_bus / L_coil (≈ 2.8 A/µs at 198 V with 70 µH) plus the resonant build-up. Find the peak current at gate-off |
| F3 | **Bus over-voltage**: slow line surge, and returned tank energy after F2 | Use `tools/bus_voltage_sim.py` for the returned energy, but with this task's real delay. Compare the bus peak with D3's clamp (MRT130KP295CV; DC-LINK-CLAMP.md) and the 650 V VDS |
| F4 | **Controller dead with PWM stuck** | Which state does each input default to? Is PERMIT removed? |
| F5 | **HOT5 brown-out** | Do U6/U7/U8 outputs keep BUS_FAULT asserted as the 5 V rail falls? Cross-check FAULT-INTERFACE.md |

## Acceptance criteria

| Check | Pass |
| --- | --- |
| Minimum worst-case OCP trip | ≥ 1.2 × 37 A = 44 A (no nuisance trip at full power). Report the actual margin |
| Maximum worst-case OCP trip, plus overshoot during the maximum chain delay, for F2 | ≤ the lowest of: IPW65R018CFD7 ID,pulse at the relevant pulse width and temperature; T1's 88 A rating; the task 01 S2 VDS limit (≤ 585 V turn-off at that current) |
| OVP window | Minimum trip is above the maximum normal bus (198 V plus ripple; state the value used). Maximum trip plus delay keeps the bus below the D3 clamp stand-off coordination in DC-LINK-CLAMP.md |
| F1 | Either the driver datasheet proves both outputs can't be on together (quote the section), or the report states **"hard shoot-through is not stopped by OCP within device limits"** as an open risk. Either answer passes the task; hiding it doesn't |
| F4/F5 | Every input and output defaults to a safe state, with the datasheet section cited |

## Deliverables

In `validation-results/02-protection-timing/`:

- `README.md`
- `outputs/thresholds.json`
- `outputs/delay_budget.csv`
- the waveform plots for F2 and F3
- a scenario table with the verdict for each

## Pitfalls

- The TLV3201's delay grows at small overdrive. Use the curve at the actual
  overdrive, not the headline number.
- R5 is 1 mΩ, so 61 A is only 61 mV. Offsets of a few millivolts matter.
  Don't round.
- Kelvin: `ocp_kelvin_n` is the HV_RET side of the shunt, so its sign during
  conduction is negative relative to `leg_ret`. Get the sign right from the
  netlist.
- Don't model the interlock board from memory. If its latency isn't
  documented, mark that link BLOCKED and give the result with a stated
  assumption as well.
