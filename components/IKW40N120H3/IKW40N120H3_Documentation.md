# IKW40N120H3 IGBT - Complete Design Guide for Induction Cooker Applications

## Document Information
- **Component**: IKW40N120H3
- **Manufacturer**: Infineon Technologies
- **Package**: TO-247-3 (PG-TO247-3)
- **Application**: Induction Cooker Power Switching
- **Document Version**: 1.0
- **Last Updated**: 2024

---

## Table of Contents

1. [High-Level Summary](#1-high-level-summary)
2. [Role in Induction Cooker](#2-role-in-induction-cooker)
3. [How to Use This Component](#3-how-to-use-this-component)
4. [SPICE Simulation Guide](#4-spice-simulation-guide)
5. [Safety Information](#5-safety-information)
6. [Design Considerations](#6-design-considerations)
7. [Thermal Management](#7-thermal-management)
8. [Gate Drive Design](#8-gate-drive-design)
9. [PCB Layout Guidelines](#9-pcb-layout-guidelines)
10. [Bill of Materials](#10-bill-of-materials)
11. [Troubleshooting](#11-troubleshooting)
12. [Additional Resources](#12-additional-resources)

---

## 1. High-Level Summary

### 1.1 What is the IKW40N120H3?

The **IKW40N120H3** is a high-performance Insulated Gate Bipolar Transistor (IGBT) designed for medium-power switching applications. It combines the best features of MOSFETs (voltage-controlled, fast switching) and bipolar transistors (low on-state voltage drop, high current capability).

**Key Technology Features:**
- **Trench Gate Technology**: Provides very low VCEsat and improved switching characteristics
- **Fieldstop Technology**: Thin wafer design enabling fast switching with low tail current
- **Integrated Freewheeling Diode**: Fast, soft recovery antiparallel diode for inductive loads
- **DuoPack Configuration**: IGBT + diode in single package for simplified half-bridge design

### 1.2 Electrical Specifications Summary

| Parameter | Symbol | Value | Unit | Notes |
|-----------|--------|-------|------|-------|
| **Voltage Ratings** |
| Collector-Emitter Voltage | VCE | 1200 | V | Maximum blocking voltage |
| Gate-Emitter Voltage | VGE | ±20 | V | Continuous |
| Transient Gate Voltage | VGE(trans) | ±30 | V | tp ≤ 10µs |
| **Current Ratings** |
| DC Collector Current | IC | 40 @ Tc=100°C | A | Limited by Tvj ≤ 175°C |
| | | 80 @ Tc=25°C | A | |
| Pulsed Collector Current | ICpulse | 160 | A | Limited by Tvj ≤ 175°C |
| Diode Forward Current | IF | 20 @ Tc=100°C | A | |
| **On-State Characteristics** |
| VCE Saturation (typ) | VCEsat | 2.05 @ 25°C | V | IC=40A, VGE=15V |
| | | 2.5 @ 125°C | V | |
| | | 2.7 @ 175°C | V | |
| Diode Forward Voltage (typ) | VF | 2.4 @ 25°C | V | IF=40A |
| Gate Threshold Voltage | VGEth | 5.0 - 6.5 | V | Typical: 5.8V |
| **Switching Characteristics** (VCC=600V, IC=40A, VGE=0/15V, RG=12Ω, Tvj=175°C) |
| Turn-on Delay | td(on) | 29 | ns | |
| Rise Time | tr | 49 | ns | |
| Turn-off Delay | td(off) | 366 | ns | |
| Fall Time | tf | 48 | ns | |
| Turn-on Energy | Eon | 4.4 | mJ | |
| Turn-off Energy | Eoff | 2.6 | mJ | |
| Total Switching Energy | Ets | 7.0 | mJ | |
| **Capacitances** (VCE=25V, VGE=0V, f=1MHz) |
| Input Capacitance | Cies | 2330 | pF | |
| Output Capacitance | Coes | 185 | pF | |
| Reverse Transfer Cap. | Cres | 130 | pF | Miller capacitance |
| Gate Charge | QG | 185 | nC | VCC=960V, IC=40A |
| **Diode Characteristics** |
| Reverse Recovery Time | trr | 639 | ns | @ 175°C, IF=40A, -diF/dt=500A/µs |
| Reverse Recovery Charge | Qrr | 4.3 | µC | @ 175°C |
| **Thermal Characteristics** |
| Junction-to-Case (IGBT) | Rth(j-c) | 0.31 | K/W | |
| Junction-to-Case (Diode) | Rth(j-c) | 1.11 | K/W | |
| Max Junction Temperature | Tvj(max) | 175 | °C | |
| Storage Temperature | Tstg | -55 to +150 | °C | |

### 1.3 Key Features for Induction Cooker Application

1. **Very Low VCEsat**: Minimizes conduction losses, improving efficiency (typically >95% in well-designed inverters)
2. **Fast Switching**: Enables operation at 20-100kHz for compact resonant tank design
3. **Soft Recovery Diode**: Reduces EMI and switching losses during freewheeling
4. **High Temperature Operation**: 175°C junction temperature allows robust design margins
5. **TO-247 Package**: Industry-standard package with good thermal performance and easy mounting

---

## 2. Role in Induction Cooker

### 2.1 Induction Heating Principle

Induction cookers work by generating a high-frequency alternating magnetic field that induces eddy currents in ferromagnetic cookware. The energy is converted directly into heat in the pot/pan, making it highly efficient.

**Energy Flow:**
```
AC Mains → Rectifier → DC Bus → IGBT Half-Bridge → Resonant Tank → Induction Coil → Magnetic Field → Cookware Heating
          (300-400V DC)        (20-100kHz AC)      (LC resonant)
```

### 2.2 Half-Bridge Topology

The IKW40N120H3 is typically used in pairs to form a **half-bridge inverter**:

```
        +VDC (300V)
            |
            |
        [Q1: HS IGBT]  ←--- IKW40N120H3 #1 (High-Side)
            |
            +------- SW (Switch Node) ---→ [Resonant Tank: Cres-Lcoil]
            |
        [Q2: LS IGBT]  ←--- IKW40N120H3 #2 (Low-Side)
            |
           GND
```

**Operating Principle:**
1. Q1 and Q2 switch alternately at high frequency (20-100kHz)
2. Dead time (0.5-2µs) prevents both conducting simultaneously (shoot-through)
3. Switch node (SW) produces a square wave that drives the resonant LC tank
4. LC tank filters the square wave into a sinusoidal current through the induction coil
5. Operating frequency is typically above resonance for soft-switching benefits

### 2.3 Why IGBT Instead of MOSFET?

| Aspect | IGBT (IKW40N120H3) | MOSFET |
|--------|-------------------|--------|
| **Voltage Rating** | 1200V | Typically 600-900V at similar cost |
| **On-State Loss** | Lower (VCEsat ≈ 2V) | Higher (RDS(on) × I²) at high current |
| **Switching Speed** | Fast (sub-100ns) | Faster, but... |
| **High Current** | Excellent (40-80A) | Expensive at this rating |
| **Ruggedness** | Very robust | More sensitive to avalanche |
| **Cost** | Lower for 1200V/40A | Higher |

**For induction cookers:** IGBTs offer the best balance of cost, performance, and ruggedness at the required voltage/current ratings.

### 2.4 Power Flow and Losses

**Input Power (AC Mains):**
- 120V AC (US) or 230V AC (EU) → Rectified to 170V or 325V DC (typical: 300-400V bus)
- Typical power levels: 1.8kW (low), 3.5kW (high)

**Losses in IGBTs:**
1. **Conduction Loss**: Pcond = VCEsat × IC(avg) ≈ 2.0V × 20A ≈ 40W per IGBT
2. **Switching Loss**: Psw = (Eon + Eoff) × fsw ≈ 7mJ × 50kHz ≈ 350W (worst case, typically 100-200W with ZVS)
3. **Gate Drive Loss**: Pgate = QG × VGE × fsw ≈ 185nC × 15V × 50kHz ≈ 0.14W (negligible)

**Total IGBT losses**: Typically 50-100W per device at 3.5kW output, requiring adequate heatsinking.

---

## 3. How to Use This Component

### 3.1 Pin Configuration (TO-247-3)

```
     Top View (leads facing down)

     1       2       3
    [G]     [C]     [E]
     |       |       |
     Gate  Collector Emitter

    Backside/Tab: Connected to Collector (Pin 2)
```

**Pin Functions:**
- **Pin 1 (G - Gate)**: Control input. Apply +15V to turn ON, 0V or negative to turn OFF
- **Pin 2 (C - Collector)**: High-voltage terminal. Connects to DC+ (high-side) or switch node (low-side)
- **Pin 3 (E - Emitter)**: Return path. Connects to switch node (high-side) or GND (low-side)
- **Backside Tab**: Electrically connected to Collector. Mount to heatsink with proper isolation.

### 3.2 Basic Half-Bridge Circuit

```
Components needed for one half-bridge:
- 2× IKW40N120H3 (Q1=high-side, Q2=low-side)
- 1× Gate driver IC (e.g., UCC21550, FOD3182)
- 2× Gate resistors (RG = 2.2-10Ω)
- DC bus capacitor (100-220µF electrolytic + 2.2µF film)
- Snubber capacitors (10-47nF across each IGBT)
- Resonant capacitor (0.1-0.47µF, high-current film type)
- Induction coil (50-150µH, Litz wire)
- Heatsink (thermal resistance < 1 K/W)
```

### 3.3 Step-by-Step Configuration

#### Step 1: DC Bus Setup
```
1. Rectify AC mains to DC (bridge rectifier for 120V, voltage doubler optional)
2. Add bulk capacitor: 100µF electrolytic (450V rated) + 2.2µF film (1000V)  3. Expected DC voltage: ~300V (from 120V AC), ~380V (from 230V AC)
4. Add bleeder resistor for discharge when unpowered (100kΩ, 5W)
```

#### Step 2: Mount IGBTs
```
1. Apply thermal compound to IGBT backside and heatsink
2. Use insulating pad (silicone or ceramic) between IGBT and heatsink
   - Required because tab is connected to Collector (high voltage)
   - Thermal resistance: ~0.5 K/W for silicone pad
3. Mount with M3 screw, torque: 0.6 Nm (do not overtighten)
4. Verify isolation: Measure resistance between Collector tab and heatsink (should be >1MΩ)
```

#### Step 3: Gate Drive Connection
```
High-Side IGBT:
- Gate driver output → RG (3.3Ω) → Q1 Gate
- Q1 Emitter → Returns to gate driver "COM" or "SW" pin (floating reference)
- Add 10kΩ resistor from Gate to Emitter for noise immunity

Low-Side IGBT:
- Gate driver output → RG (3.3Ω) → Q2 Gate
- Q2 Emitter → GND
- Add 10kΩ resistor from Gate to Emitter
```

#### Step 4: Resonant Tank Connection
```
1. Connect switch node (Q1 Emitter / Q2 Collector junction) to resonant capacitor
   - Use short, wide PCB traces or bus bars
   - Minimize inductance (<50nH)

2. Resonant capacitor → Induction coil → GND
   - Cres: 0.22µF (typical, adjust for desired resonant frequency)
   - Lcoil: 100µH (typical, depends on coil design)
   - f_resonant = 1/(2π√(LC)) ≈ 34kHz

3. Operate above resonance (e.g., 50kHz) for inductive load and soft switching
```

#### Step 5: Snubbers and Protection
```
1. RC snubber across each IGBT:
   - Rsnub = 47Ω (2W rated)
   - Csnub = 22nF (1kV ceramic)
   - Reduces dv/dt stress and EMI

2. Optional: Varistor or TVS across DC bus for overvoltage protection
   - Rating: 510V MOV or 430V TVS

3. Current sensing for overcurrent protection (using shunt or current transformer)
```

### 3.4 Gate Drive Voltage Selection

| VGE | IC (capability) | VCEsat | Switching Speed | Recommendation |
|-----|----------------|--------|-----------------|----------------|
| +10V | ~25A | Higher | Slower | Not recommended |
| +12V | ~32A | Medium | Medium | Acceptable for light loads |
| +15V | 40A (full rating) | Lowest (2.05V) | Fastest | **Recommended** |
| +18V | 40A+ | Slightly lower | Slightly faster | Marginal benefit, closer to abs max |
| +20V | 40A+ | Minimal improvement | Minimal improvement | **Not recommended** (at abs max rating) |

**Standard Practice**: Use **VGE = +15V** for ON, **0V or -5V** for OFF.
- Negative gate voltage improves noise immunity and turn-off speed
- Commercial gate drivers (UCC21550, FOD3182) typically provide 0/+15V

---

## 4. SPICE Simulation Guide

### 4.1 Model Files Provided

1. **IKW40N120H3.lib**: SPICE subcircuit model
   - Behavioral model capturing key IGBT and diode characteristics
   - Includes temperature-dependent parameters
   - Validated against datasheet specifications

2. **IKW40N120H3_test.cir**: Example test circuit
   - Complete half-bridge with UCC21550 gate driver
   - Resonant load representing induction coil
   - Ready to run in ngspice or KiCad simulator

### 4.2 Running the Simulation in ngspice

```bash
# Command line
ngspice IKW40N120H3_test.cir

# The simulation will:
# 1. Run transient analysis for 200µs (10 switching cycles)
# 2. Generate plots of key waveforms
# 3. Print measurements (propagation delay, dead time, currents, power)
# 4. Calculate efficiency estimate
```

### 4.3 Running in KiCad (Eeschema + Spice)

```
1. Create schematic using the provided .kicad_sym symbol
2. Assign SPICE model:
   - Right-click component → Properties → Simulation Model
   - Select "Subcircuit" and browse to IKW40N120H3.lib
3. Add voltage sources, passives, and configure simulation:
   - Simulation → Settings → Transient
   - Stop time: 200µs, Max time step: 10ns
4. Run simulation and probe waveforms
```

### 4.4 Expected Simulation Results

#### 4.4.1 Waveforms to Observe

1. **Gate Signals**
   - Should show clean 0/15V transitions
   - Rise/fall times: ~100ns (including gate resistor)
   - Dead time visible: ~1µs between HS and LS

2. **Switch Node Voltage V(SW)**
   - Square wave between 0V and 300V (VDC)
   - Some ringing acceptable (<50V overshoot with proper snubbing)
   - Duty cycle: ~45% each transistor

3. **Resonant Current I(L_COIL)**
   - Sinusoidal current (LC tank filters square wave)
   - Peak current: 20-40A depending on load
   - Frequency: 50kHz (switching frequency)
   - Phase relative to V(SW): lagging (operating above resonance)

4. **Collector-Emitter Voltage**
   - When ON: VCE ≈ 2.0-2.5V (VCEsat)
   - When OFF: VCE ≈ VDC (300V) for one device, 0V for the other
   - Look for overvoltage spikes (should be <400V with snubbers)

5. **DC Bus Current I(VDC)**
   - Pulsed current waveform
   - Average current = Output Power / VDC
   - Example: 1800W / 300V ≈ 6.0A average

#### 4.4.2 Key Measurements

Run these checks to validate the simulation:

| Parameter | Expected Range | How to Measure | Pass/Fail Criteria |
|-----------|---------------|----------------|-------------------|
| **Gate Drive** |
| Propagation Delay | 30-100ns | Time from input edge to gate voltage reaching Vth | < 200ns |
| Dead Time | 0.5-2µs | Time between LS fall and HS rise | > 0.3µs (prevent shoot-through) |
| Gate Voltage High | 14-15.5V | Peak of V(HS_GATE) | Within ±5% of supply |
| Gate Voltage Low | -0.5 to +0.5V | Valley of V(HS_GATE) | Close to 0V |
| **Power Stage** |
| SW Voltage Swing | 0 to VDC | Max/min of V(SW) | 0V < V(SW) < 1.1×VDC |
| VCEsat | 1.8-2.8V | V(C,E) when IGBT is ON | < 3.0V |
| Diode VF | 2.0-3.0V | V(E,C) when diode conducts | < 3.5V |
| Overvoltage Spike | <10% above VDC | Peak of V(SW) during turn-off | < 1.2×VDC (360V for 300V bus) |
| **Resonant Tank** |
| Coil Current Peak | 20-50A | Peak of I(L_COIL) | < ICpulse (160A) |
| Coil Current RMS | 10-30A | RMS of I(L_COIL) | < IC(max) at operating Tc |
| Resonant Frequency | Calculated from L, C | FFT of I(L_COIL) | Match 1/(2π√LC) |
| **Efficiency** |
| DC Input Power | Calculated | VDC × I(VDC)_avg | - |
| AC Output Power | Calculated | V(LOAD) × I(LOAD)_rms | - |
| Efficiency | >90% | P_out / P_in × 100% | > 85% (simplified model) |

### 4.5 Validation Checklist

Use this checklist to ensure the SPICE model is working correctly:

- [ ] **Model Loads Successfully**: No syntax errors when including .lib file
- [ ] **Gate Threshold Correct**: IGBT turns ON when VGE > ~5.8V, OFF when VGE < ~5.0V
- [ ] **VCEsat Reasonable**: ~2.0-2.5V at rated current (40A)
- [ ] **Temperature Dependence**: VCEsat increases with temperature (run at different TEMP values)
- [ ] **Switching Transients**: Turn-on and turn-off show realistic transitions (not instantaneous)
- [ ] **Capacitances Modeled**: Miller plateau visible in gate voltage waveform during switching
- [ ] **Diode Conduction**: Freewheeling diode conducts during dead time (negative current through IGBT)
- [ ] **Reverse Recovery**: Some current spike visible when diode stops conducting
- [ ] **No Unrealistic Behavior**: No negative voltages where impossible, no divide-by-zero errors
- [ ] **Steady State Reached**: Waveforms settle into repetitive pattern after a few cycles

### 4.6 Common Simulation Issues and Fixes

| Issue | Symptom | Likely Cause | Solution |
|-------|---------|--------------|----------|
| **Convergence Failure** | Simulation stops with "timestep too small" | Abrupt transitions, inadequate models | Add .options gmin=1e-12, use smaller max timestep (1ns) |
| **Unrealistic Spikes** | Huge voltage/current spikes (>>1kV, >>1kA) | Missing snubbers, parasitic inductance too high | Add RC snubbers, reduce parasitic L values |
| **No Switching** | Switch node stuck at one voltage | Gate drive issue, incorrect connections | Check VGE reaches >6V, verify gate driver supply |
| **Shoot-Through** | Both IGBTs conduct simultaneously, huge current | Insufficient dead time | Increase dead time in PWM signals to >0.5µs |
| **Thermal Runaway** | Temperature parameter causes unstable behavior | Positive feedback in model | Limit TEMP parameter to reasonable range (-40 to +175°C) |
| **Wrong Resonant Freq** | Current frequency doesn't match expected | Incorrect L or C values | Recalculate f = 1/(2π√LC), adjust component values |

### 4.7 Model Limitations

The provided SPICE model is a **behavioral approximation** suitable for circuit-level design. It does **NOT** model:

1. **Detailed Physics**: Internal carrier dynamics, latch-up mechanisms
2. **Short-Circuit Behavior**: Model may not accurately predict ISC or safe operating area under fault
3. **Extreme Transients**: Very fast (<1ns) transients may not be captured accurately
4. **Package Parasitics in Detail**: Only basic inductance modeled
5. **EMI**: High-frequency ringing and radiation not modeled

**For final design validation**, always:
- Build and test physical prototype
- Verify all waveforms on oscilloscope
- Perform thermal testing under worst-case conditions
- Conduct EMC testing per applicable standards

---

## 5. Safety Information

### ⚠️ WARNING: HIGH VOLTAGE DEVICE

The IKW40N120H3 operates with **LETHAL VOLTAGES** (300-400V DC in induction cookers). Improper design or handling can result in:
- **Electric shock** (potentially fatal)
- **Fire hazard** (device failure, PCB arcing)
- **Equipment damage**
- **Thermal burns** (heatsink temperatures >100°C)

### 5.1 Electrical Safety

#### 5.1.1 Voltage Ratings - ABSOLUTE MAXIMUM

| Parameter | Absolute Maximum | Safety Margin | Notes |
|-----------|-----------------|---------------|-------|
| VCE (Collector-Emitter) | 1200V | Operate ≤600V continuous | Transients from mains can reach 800V+ |
| VGE (Gate-Emitter) | ±20V continuous | Use ±15V max | ±30V transient (tp<10µs) allowed |
| Tvj (Junction Temperature) | 175°C | Design for ≤125°C | Ensures reliability and lifetime |

**NEVER EXCEED THESE RATINGS** - Permanent damage or catastrophic failure will occur.

#### 5.1.2 Safe Operating Area (SOA)

The IGBT has defined Safe Operating Area constraints:

1. **Forward Bias SOA** (FBSOA):
   - IC vs VCE curve defines maximum simultaneous current and voltage
   - For IKW40N120H3: Can handle 40A up to full 1200V in DC mode
   - Pulse operation: 160A pulse capability with VCE derating

2. **Reverse Bias SOA** (RBSOA) - Turn-off:
   - More restrictive than FBSOA
   - At turn-off: Maximum IC = 160A at VCE ≤ 1200V (datasheet Figure 7)
   - Stay within the curves for pulse durations

3. **Short Circuit Withstand**:
   - tSC = 10µs maximum at VCC ≤ 600V, VGE = 15V
   - Allowed number of short circuits: <1000 lifetime
   - Time between short circuits: ≥1.0s (thermal recovery)
   - **Recommendation**: Implement overcurrent protection to trip in <5µs

### 5.2 Thermal Safety

#### 5.2.1 Temperature Limits

| Parameter | Value | Consequence of Exceeding |
|-----------|-------|-------------------------|
| Tvj(max) | 175°C | Permanent damage, thermal runaway |
| Tc(max recommended) | 100°C | Ensures Tvj margin with power dissipation |
| Tstg | -55 to +150°C | Material degradation outside range |
| Tsolder | 260°C for 10s | Package damage, die cracking |

#### 5.2.2 Thermal Calculations

**Junction Temperature**:
```
Tvj = Tc + (Rth_jc × P_total)

Where:
- Tc = Case temperature (measured on backside tab)
- Rth_jc = 0.31 K/W (IGBT) or 1.11 K/W (diode)  - P_total = Conduction loss + Switching loss
```

**Case to Ambient**:
```
Tc = Ta + (Rth_ca × P_total)

Where:
- Ta = Ambient temperature  - Rth_ca = Rth_interface + Rth_heatsink
  - Rth_interface ≈ 0.5 K/W (thermal pad + compound)
  - Rth_heatsink: Depends on heatsink size (0.5-2 K/W typical)
```

**Example Calculation**:
- P_total = 80W (conduction) + 100W (switching) = 180W
- Ta = 40°C (internal electronics enclosure)
- Rth_jc = 0.31 K/W
- Rth_interface = 0.5 K/W
- Rth_heatsink = 0.8 K/W (forced air cooled)

```
Rth_ca = 0.5 + 0.8 = 1.3 K/W
Tc = 40°C + (1.3 K/W × 180W) = 40 + 234 = 274°C ❌ EXCEEDS LIMIT!

Need better heatsink:
Required Rth_total = (Tvj_max - Ta) / P_total = (125 - 40) / 180 = 0.47 K/W
Required Rth_ca = 0.47 - 0.31 = 0.16 K/W
This requires: Rth_heatsink < 0.16 - 0.5 = NOT ACHIEVABLE (negative!)

Solution: Reduce losses or add forced air cooling
With fan: Rth_heatsink can reach ~0.3 K/W
Rth_ca = 0.5 + 0.3 = 0.8 K/W
Tc = 40 + (0.8 × 180) = 184°C ❌ STILL TOO HIGH

Better solution: Reduce switching frequency or use two IGBTs in parallel
```

#### 5.2.3 Thermal Protection

**Mandatory:**
1. **Heatsink Temperature Sensor**: NTC thermistor or thermocouple on heatsink
   - Trip point: Tc > 90°C
   - Response time: <1 second

2. **Overtemperature Shutdown**: Disable gate drive if Tc exceeds limit
   - Prevents thermal runaway
   - Include hysteresis (e.g., trip at 90°C, resume at <70°C)

**Recommended:**
3. **Junction Temperature Estimation**: Calculate Tvj from Tc and measured power
4. **Thermal Foldback**: Reduce output power if temperature approaches limits

### 5.3 Overcurrent Protection

**Why Critical:**
- IGBTs can fail catastrophically if overcurrent persists
- Short circuits can draw >200A, exceeding pulse rating
- Magnetic saturation in induction coil can cause runaway current

**Protection Methods:**

1. **Current Sense + Fast Shutdown**:
   ```
   - Measure IC using shunt resistor or current transformer
   - If IC > 50A (125% of rating): Trigger shutdown within 1-5µs
   - Disable PWM and pull gates low
   - Typical implementation: Comparator + gate driver disable pin
   ```

2. **Desaturation Detection (VCE monitoring)**:
   ```
   - Monitor VCE while IGBT is supposed to be ON
   - If VCE > 8-10V (should be ~2V): IGBT is in saturation or failing
   - Indicates overcurrent or gate drive failure
   - Fast response: <500ns shutdown time
   ```

3. **Short Circuit Protection**:
   - Use gate driver with built-in short circuit detection (e.g., UCC21750)
   - Maximum allowed tSC = 10µs (per datasheet)
   - Implement soft turn-off to reduce voltage spike

### 5.4 dv/dt and di/dt Protection

**Issue**: Fast voltage and current transients can cause:
- False triggering (dv/dt induced gate current)
- EMI and radiated emissions
- Overvoltage due to parasitic inductance (V = L × di/dt)

**Mitigation:**

1. **Gate Resistor**: RG = 2.2-10Ω
   - Slows down switching slightly
   - Reduces di/dt to safe levels (~500-2000 A/µs)

2. **RC Snubber Across IGBT**:
   ```
   - R = 10-47Ω (2W rated)
   - C = 10-47nF (>1kV ceramic)
   - Limits dv/dt during turn-off
   ```

3. **Minimize Parasitic Inductance**:
   - Keep gate loop small (<50mm²)
   - Use wide, short power traces
   - Kelvin connection for emitter sense (separate power and signal grounds)

### 5.5 Insulation and Isolation

#### 5.5.1 High-Side IGBT

The high-side IGBT emitter is at **switching potential** (0-300V relative to ground). Its gate drive must float at this potential.

**Requirements:**
- **Isolated gate driver**: UCC21550 (5kVrms isolation) or optocoupler (FOD3182, 5kV isolation)
- **Isolated power supply for gate**: Bootstrap circuit or isolated DC-DC converter
- **Creepage/clearance**: Maintain >3mm spacing from high-voltage nodes to ground on PCB

#### 5.5.2 Heatsink Isolation

**Critical Safety Requirement:**

The IGBT backside tab is connected to the **Collector** (high voltage). Heatsink is typically grounded for safety.

**Mandatory Isolation:**
1. Use **insulating pad** (silicone or ceramic):
   - Dielectric strength: >3kV
   - Thermal resistance: <0.5 K/W
   - Examples: Sil-Pad, Bergquist Gap Pad

2. Use **insulating hardware**:
   - Nylon or ceramic shoulder washers for screws
   - Prevent metal screw from contacting both tab and heatsink

3. **Test isolation**:
   - Megohmmeter test: Tab to heatsink should measure >10MΩ @ 500V DC
   - Hipot test: 2× operating voltage + 1000V AC for 1 minute (optional, for production)

### 5.6 EMI and Electrical Noise

**Potential Issues:**
- Radiated EMI exceeding FCC/CE limits
- Conducted emissions on mains
- Crosstalk affecting control circuits

**Solutions:**
1. **Snubbers**: RC across IGBTs (reduces dv/dt)
2. **Common-mode choke**: On AC input
3. **Shielding**: Enclose coil in grounded metal shield
4. **PCB layout**: Ground plane, short high-current loops
5. **Gate resistors**: Slow down switching slightly

---

## 6. Design Considerations

### 6.1 Selecting IGBTs for Induction Cooker

| Power Level | VDC (Bus) | IC (Peak) | Recommended IGBT | Parallel Devices |
|-------------|----------|-----------|------------------|------------------|
| 1.0-1.5 kW | 300V | 15-20A | IKW30N120H3 or IKW40N120H3 | 1× per position |
| 1.5-2.5 kW | 300V | 20-30A | IKW40N120H3 | 1× per position |
| 2.5-3.5 kW | 300V | 30-45A | IKW40N120H3 or IKW50N120H3 | 1× or 2× parallel |
| 3.5-5.0 kW | 300V | 45-60A | IKW50N120H3 | 2× parallel per position |

**For 2-3kW induction cooker**: **IKW40N120H3** is ideal (sweet spot of cost and performance).

### 6.2 Gate Drive Design

#### 6.2.1 Gate Resistor Selection

The gate resistor (RG) is critical for controlling switching speed and losses.

| RG (Ω) | Turn-on Time | Turn-off Time | Switching Loss | EMI | Recommendation |
|--------|--------------|---------------|----------------|-----|----------------|
| 0-1 | Very fast (~50ns) | Very fast (~20ns) | Lowest | Highest | Too fast, excessive EMI |
| 2.2-3.3 | Fast (~60ns) | Fast (~30ns) | Low | Medium-High | **Good balance** ⭐ |
| 4.7-6.8 | Medium (~80ns) | Medium (~40ns) | Medium | Medium | Acceptable |
| 10-15 | Slow (~120ns) | Slow (~60ns) | Higher | Lower | Use if EMI is critical |
| >22 | Very slow (>150ns) | Very slow (>80ns) | High | Lowest | Not recommended (excessive loss) |

**Standard choice**: **RG = 3.3Ω (2W rated)** for both turn-on and turn-off.

#### 6.2.2 Gate Drive Power Supply

**Option 1: Bootstrap (for High-Side)**

```
                        VDD (+15V)
                          |
                       [Diode: Fast recovery, >600V]
                          |
                    [Cboot: 1-10µF]
                          |
                      HS Emitter (SW node)
```

**Advantages:**
- Simple, low cost
- No isolated supply needed

**Disadvantages:**
- Requires low-side to turn ON regularly to refresh Cboot
- Cboot must be sized for QG: Cboot > 20 × QG / ΔV = 20 × 185nC / 1V ≈ 3.7µF (use 10µF)
- Maximum duty cycle limited (~90%)

**Option 2: Isolated DC-DC Converter**

Use a small isolated DC-DC module (e.g., RECOM R1D-0505, 1W):
- Input: 5V (from logic supply)
- Output: 5V isolated (then regulate to 15V with LDO)
- Isolation: >1kV

**Advantages:**
- Works at 100% duty cycle
- More robust

**Disadvantages:**
- Higher cost
- More complex

**For induction cooker**: **Bootstrap is standard** (duty cycle <50% in half-bridge).

#### 6.2.3 Gate Driver Selection

Recommended drivers:

| Part Number | Type | Isolation | Output Current | Features | Cost |
|-------------|------|-----------|----------------|----------|------|
| UCC21550 | Dual isolated | 5kVrms | 4A/6A | Built-in UVLO, disable | $$$ |
| FOD3182 | Optocoupler | 5kV | 2.5A | Simple, proven | $ |
| SI8271 | Isolated | 5kVrms | 4A | Digital isolator based | $$ |
| 2ED020I12-F2 | Dual low-side | None (bootstrap) | 1.5A | Integrated driver for half-bridge | $$ |

**For this project**: **UCC21550** (already in design) is excellent choice.

### 6.3 Resonant Tank Design

The resonant LC tank is the "heart" of the induction cooker.

#### 6.3.1 Component Selection

**Resonant Capacitor (Cres)**:
- Type: Polypropylene film (PP) capacitor, rated for high AC current
- Voltage: >600V DC (1kV preferred for safety margin)
- Current rating: >1.5× RMS coil current
  - Example: For 30A RMS coil current, need Cres rated >45A RMS
- Typical value: 0.1-0.47µF
- ESR: <10mΩ (low ESR critical for efficiency)
- Recommendations: EPCOS/TDK B3292* series, KEMET C4AE series

**Induction Coil (Lcoil)**:
- Construction: Litz wire (many fine strands to reduce skin effect at 20-100kHz)
- Inductance: 50-150µH
- Wire gauge: AWG 12-16 Litz (hundreds of strands of AWG 38-42)
- Turns: Typically 10-20 turns in spiral shape
- Diameter: Matches cookware size (150-250mm outer diameter)
- DCR: <0.5Ω (minimize copper losses)

#### 6.3.2 Resonant Frequency Selection

**Formula**:
```
f_resonant = 1 / (2 × π × √(L × C))
```

**Example**:
- L = 100µH
- C = 0.22µF
- f_resonant = 1 / (2 × π × √(100µH × 0.22µF)) ≈ 33.9kHz

**Operating Frequency Selection**:

| Mode | fsw vs f_res | Load Characteristic | Switching | Current |
|------|--------------|---------------------|-----------|---------|
| Below resonance | fsw < f_res | Capacitive | Hard switching | Leading |
| At resonance | fsw = f_res | Resistive | Hard switching | In phase (max current) |
| **Above resonance** | **fsw > f_res** | **Inductive** | **Soft (ZVS)** | **Lagging** ⭐ |

**Recommended**: Operate **above resonance** (e.g., f_res = 30kHz, fsw = 50kHz).

**Benefits**:
1. **Zero-Voltage Switching (ZVS)**: Coil current is lagging, so it flows through freewheeling diode just before IGBT turns ON → VCE is pulled to ~0V before gate signal arrives → Turn-on loss greatly reduced
2. **Controlled current**: Current decreases as fsw increases (power control via frequency modulation)

#### 6.3.3 Power Control Methods

Induction cookers adjust power via one or both methods:

**Method 1: Frequency Modulation**
- Increase fsw → Move further above resonance → Current decreases → Power decreases
- Example: 25kHz (max power) to 80kHz (min power)
- Maintains ZVS across range

**Method 2: Duty Cycle Control (Pulse Skipping)**
- Turn ON at 50kHz for 1 second, OFF for 2 seconds → 33% average power
- Allows frequency to stay in optimal ZVS range
- Simpler control

**Hybrid**: Use frequency for fine control (80-100%), pulse skipping for coarse (0-80%).

### 6.4 Paralleling IGBTs for Higher Power

If single IKW40N120H3 is insufficient, parallel two devices per position.

**Critical Requirements**:

1. **Matched Devices**:
   - Use same part number, same production batch if possible
   - VGEth should match within 0.3V

2. **Equal Gate Drive**:
   - Separate gate resistors for each device (RG = 3.3Ω each)
   - Equal-length gate traces (within 10mm)

3. **Thermal Coupling**:
   - Mount on same heatsink, close together
   - Allows thermal load sharing (hotter device conducts less, cooler conducts more)

4. **Current Sharing Resistors (optional)**:
   - Small resistors in emitter path (0.01-0.05Ω) can improve current sharing
   - Adds loss, usually not needed if above steps followed

**Expected sharing**: 40-60% / 60-40% (acceptable). Perfect 50/50 not necessary.

---

## 7. Thermal Management

### 7.1 Heat Generation

**Power Dissipation Components**:

1. **Conduction Loss**:
   ```
   P_cond = VCEsat × IC(avg)

   For half-bridge, each IGBT conducts ~45% of time (duty cycle with dead time)
   IC(avg) ≈ IC(RMS) × duty_cycle / √2 (for resistive/inductive load)

   Example:
   - IC(RMS) = 25A
   - VCEsat = 2.5V @ 125°C
   - D = 0.45
   - P_cond ≈ 2.5V × 25A × 0.45 ≈ 28W per IGBT
   ```

2. **Switching Loss**:
   ```
   P_sw = (Eon + Eoff) × fsw

   Example (from datasheet @ 175°C):
   - Eon = 4.4mJ
   - Eoff = 2.6mJ
   - fsw = 50kHz
   - P_sw = (4.4 + 2.6)mJ × 50kHz = 350W 😱

   BUT: With ZVS (soft switching), Eon can reduce by 70-90%!
   - Eon_ZVS ≈ 0.5-1.0mJ (diode conducts before IGBT turn-on)
   - Eoff remains ~2.6mJ (hard turn-off unavoidable in half-bridge)
   - P_sw_ZVS ≈ (0.7 + 2.6)mJ × 50kHz ≈ 165W (still significant)
   ```

3. **Diode Loss**:
   ```
   P_diode = VF × IF(avg) + Qrr × VDC × fsw

   Conduction: VF × IF(avg) ≈ 2.5V × 5A ≈ 12.5W (during dead time + freewheeling)
   Reverse recovery: Qrr × VDC × fsw ≈ 4.3µC × 300V × 50kHz ≈ 64W

   Total diode: ~75W
   ```

**Total Loss per IGBT**: 28W (cond) + 165W (sw) + 75W (diode) ≈ **270W** (worst case, no ZVS)

With good ZVS design: ~28W + 50W + 75W ≈ **150W** per device

### 7.2 Heatsink Selection

**Target**:
- Tvj < 125°C
- Ta = 40°C (inside enclosure)
- P_total = 150W per IGBT

**Thermal Resistance Chain**:
```
Tvj → Tc → Heatsink → Ambient
 |      |       |
Rth_jc  Rth_interface  Rth_heatsink
```

**Required Rth_heatsink**:
```
Rth_total = (Tvj - Ta) / P = (125 - 40) / 150 = 0.57 K/W

Rth_heatsink = Rth_total - Rth_jc - Rth_interface
             = 0.57 - 0.31 - 0.5
             = -0.24 K/W ❌ IMPOSSIBLE!
```

**Conclusion**: Need **forced air cooling** or **reduce losses**.

**With 2 m/s airflow** (small fan):
- Rth_heatsink can reach ~0.3 K/W for a reasonable size (100×100mm extruded aluminum)

**Recalculate**:
```
Rth_total = 0.31 + 0.5 + 0.3 = 1.11 K/W
Tvj = Ta + P × Rth_total = 40 + 150 × 1.11 = 206°C ❌ STILL EXCEEDS!
```

**Better approach**: Use larger heatsink + fan, or accept lower power.

**For 100W per IGBT** (reduced power or better ZVS):
```
Tvj = 40 + 100 × 1.11 = 151°C ✅ Acceptable (with margin to 175°C limit)
```

### 7.3 Heatsink Mounting Best Practices

1. **Surface Preparation**:
   - Clean IGBT backside with isopropyl alcohol (remove oils, oxidation)
   - Clean heatsink surface (fine sandpaper if anodized, then clean)

2. **Thermal Compound**:
   - Apply thin layer (~0.05mm) of thermal grease (e.g., Arctic MX-4, Dow Corning 340)
   - Too much compound increases thermal resistance!

3. **Insulation Pad**:
   - Use pre-cut silicone pad (e.g., Bergquist Sil-Pad K10) matching TO-247 footprint
   - Place between IGBT and heatsink
   - Apply thermal grease on both sides of pad

4. **Mounting**:
   - Use M3 screw with insulating shoulder washer
   - Tighten to specified torque: **0.6 Nm** (use torque screwdriver or wrench)
   - DO NOT overtighten (cracks die) or undertighten (poor thermal contact)

5. **Verification**:
   - Measure resistance from IGBT collector tab to heatsink: Should be >1MΩ
   - If <100kΩ: Insulation failure, do not power on!

### 7.4 Thermal Monitoring

**Temperature Sensors**:

1. **NTC Thermistor on Heatsink**:
   - Place near IGBTs (or embed in heatsink)
   - Measures Tc (approximately)
   - Recommended: 10kΩ @ 25°C NTC (e.g., Vishay NTCLE100E3103JB0)
   - Curve: Use Steinhart-Hart equation or lookup table for temperature

2. **Software Tvj Estimation**:
   ```
   Tvj_estimated = Tc_measured + (Rth_jc × P_estimated)

   Where:
   - Tc_measured: From NTC thermistor
   - P_estimated: Calculate from IC_measured and known VCEsat
   ```

**Protection Logic**:
```
if (Tvj_estimated > 150°C):
    reduce_power_by_50_percent()  # Thermal foldback
if (Tvj_estimated > 170°C):
    emergency_shutdown()  # Prevent damage
```

---

## 8. Gate Drive Design

### 8.1 Gate Resistor Detailed Selection

The gate resistor affects:
- Switching speed (di/dt, dv/dt)
- EMI
- Gate drive power dissipation (usually negligible)
- Turn-on/off losses in IGBT

**Calculating Turn-On Time**:
```
t_on ≈ RG × Cies × ln((VGG - Vth) / (VGG - Vmiller))

Where:
- RG = Gate resistor
- Cies = Input capacitance (2330pF)
- VGG = Gate drive voltage (15V)
- Vth = Threshold (5.8V)
- Vmiller ≈ 7-8V (plateau voltage during Miller effect)

Example with RG = 3.3Ω:
t_on ≈ 3.3Ω × 2330pF × ln((15 - 5.8) / (15 - 7.5))
    ≈ 3.3 × 2330e-12 × ln(9.2 / 7.5)
    ≈ 7.7ns × 0.204
    ≈ 1.6ns (very simplified; actual is ~50-60ns due to Miller and other effects)
```

**More Accurate** (from datasheet):
- td(on) = 29ns
- tr = 49ns
- Total turn-on time ≈ 78ns @ RG = 12Ω

Scaling for RG = 3.3Ω:
- t_on ≈ 78ns × (3.3 / 12) ≈ 21ns (faster than with 12Ω)

**Trade-off**:
- **Smaller RG** (1-2Ω): Fastest switching, lowest Eon/Eoff, but highest EMI and di/dt stress
- **Larger RG** (10-15Ω): Slower, higher losses, but lower EMI

**Recommendation for induction cooker**: **RG = 3.3Ω** (1/4W or 1/2W resistor, metal film)

### 8.2 Gate Drive Loop Layout

**Critical**: The gate drive loop must have **low inductance** (<20nH).

**Poor Layout** (high inductance ~100nH):
```
Gate Driver IC
   |
   +--[long trace 50mm]--[RG]--[long trace 30mm]-- Gate
                                                      |
   +--[long trace 70mm]--[Emitter]--[trace]--------+
```
- Total loop area: Large
- Inductance: ~100nH
- Voltage spike during switching: V = L × di/dt = 100nH × (4A / 10ns) = 40V!

**Good Layout** (low inductance ~15nH):
```
Gate Driver IC placed close to IGBT (<20mm)
   |
   +--[short wide trace 10mm]--[RG]--[short 5mm]-- Gate
                                                      |
   +--[return trace directly below, ground plane]---Emitter
```
- Loop area: Minimal
- Inductance: ~15nH
- Spike: V = 15nH × (4A/10ns) = 6V (acceptable)

**Layout Rules**:
1. Place gate driver IC **within 20mm** of IGBT
2. Use **ground plane** for return path
3. Route gate and emitter traces **close together** (twisted pair or top/bottom of PCB)
4. Use **Kelvin connection** for emitter sense (separate high-current and sense paths)

### 8.3 Bootstrap Circuit Design

For high-side gate drive:

```
        VDD (+15V)
          |
        [D_boot: UF4007 or similar, >600V, fast]
          |
      +--[Cboot: 10µF / 50V ceramic]--+
      |                                 |
  Gate Driver                     HS IGBT Emitter (SW node)
      IC "VDD"                          (0-300V relative to GND)
```

**Component Selection**:

1. **Bootstrap Diode (D_boot)**:
   - Voltage rating: Must withstand VDC when HS IGBT is ON
     - Use >600V rated (e.g., UF4007: 1kV, 1A fast recovery)
   - Forward current: >100mA (charges Cboot during dead time)
   - Fast recovery: trr < 100ns (to minimize loss)

2. **Bootstrap Capacitor (Cboot)**:
   - Voltage rating: 25-50V (only sees VDD voltage, not VDC)
   - Capacitance sizing:
     ```
     Cboot > N × QG / ΔV

     Where:
     - N = Safety factor (10-20×)
     - QG = Gate charge (185nC for IKW40N120H3)
     - ΔV = Acceptable voltage droop (<1V)

     Cboot > 20 × 185nC / 1V = 3.7µF → Use 10µF for margin
     ```
   - Type: X7R or X5R ceramic (low ESR, compact)
   - Placement: **Very close to gate driver IC** (<10mm)

3. **Refresh Requirement**:
   - Low-side IGBT must turn ON periodically to pull SW node to GND
   - This allows D_boot to conduct and recharge Cboot
   - Maximum high-side duty cycle: ~95% (practically, <90% for margin)
   - For induction cooker half-bridge: Duty cycle <50%, so no issue

---

## 9. PCB Layout Guidelines

### 9.1 Critical Traces and Current Paths

**High-Current Paths** (require wide traces, low inductance):

1. **DC Bus** (VDC to IGBTs):
   - Current: Pulsed up to 40A peak
   - Trace width: >5mm (for 2oz copper), or use bus bars
   - Length: Minimize (<100mm if possible)
   - Decoupling: Place film capacitors (2.2µF) **very close** to IGBT collectors

2. **Resonant Tank** (SW node to Cres to Lcoil):
   - Current: 30-50A RMS AC at 50kHz
   - Trace width: >8mm (high-frequency current, skin effect)
   - Or use Litz wire soldered to PCB pads
   - Keep inductance <50nH

3. **Ground Return**:
   - Use ground plane (entire layer if possible)
   - Connect all low-side emitters to solid ground plane

**Low-Current Signal Paths** (require careful routing for noise immunity):

1. **Gate Drives**:
   - Route gate and emitter sense traces close together (differential pair)
   - Avoid crossing high dv/dt traces (SW node!)
   - Use ground plane cutout under high-voltage traces to prevent coupling

2. **Control Signals** (PWM inputs, sensors):
   - Use shielded twisted pair or differential signaling
   - Filter inputs with RC (100Ω + 100nF)
   - Galvanic isolation for signals crossing isolation barrier

### 9.2 Layer Stackup (4-Layer PCB Recommended)

```
Layer 1 (Top):    Components, signal traces, some power traces
Layer 2 (Inner):  Ground plane (solid copper, minimal breaks)
Layer 3 (Inner):  Power plane (VDC, VDD split planes)
Layer 4 (Bottom): High-current returns, additional components
```

**Benefits**:
- Layer 2/3 form low-inductance capacitance (~100pF per square inch)
- Ground plane provides return path for high-frequency currents
- Shields layer 1 signals from layer 4

**For Budget Design** (2-Layer):
- Use top layer for signals and components
- Use bottom layer as ground plane with power traces
- More challenging, but possible with careful layout

### 9.3 Component Placement

**Priority 1: Minimize High-Current Loop Area**

```
    VDC+
     |
   [Cbus film]---[Q1 HS Collector]
     |                |
     |            [Q1 HS Emitter] = SW node
     |                |
     |            [Q2 LS Collector] = SW node
     |                |
   [Cbus film]---[Q2 LS Emitter]
     |
    GND
```

- Place Cbus film capacitors **immediately adjacent** to IGBT pins (<5mm)
- Minimize loop formed by Cbus → Q1 → Q2 → Cbus

**Priority 2: Gate Drive Proximity**

- Place gate driver IC within 20mm of IGBT gate pins
- Place bootstrap components (Dboot, Cboot) within 10mm of driver IC
- Place RG resistor within 5mm of IGBT gate pin

**Priority 3: Thermal Considerations**

- Mount both half-bridge IGBTs on same heatsink
- Ensure adequate spacing for insulation pads (typically 5mm between devices)

### 9.4 Creepage and Clearance

For safety compliance (UL, IEC 60335):

| Voltage | Minimum Creepage | Minimum Clearance | Notes |
|---------|-----------------|-------------------|-------|
| <150V | 1.5mm | 1.0mm | Low-voltage circuits |
| 150-300V | 3.2mm | 2.0mm | DC bus to ground |
| 300-600V | 5.5mm | 3.0mm | High voltage |
| >600V | 8mm+ | 4mm+ | Requires special attention |

**For 300V DC bus**:
- Maintain **>3mm** spacing between high-voltage copper and ground plane
- Use **ground guard rings** around high-voltage traces
- Avoid sharp corners (use rounded traces to prevent corona discharge)

### 9.5 EMI Reduction Techniques

1. **Star Grounding**:
   - Connect all ground returns to single point (typically at DC bus capacitor)
   - Prevents ground loops

2. **Snubber Placement**:
   - Mount RC snubbers directly across IGBT pins (no long traces)

3. **Shielding**:
   - Ground plane acts as shield
   - Optional: Metal enclosure grounded to PCB ground

4. **Common-Mode Filtering**:
   - Common-mode choke on AC input
   - Y-capacitors (line to ground) for high-frequency noise suppression

---

## 10. Bill of Materials

### 10.1 Complete BOM for 3kW Induction Cooker (Half-Bridge)

| Ref Des | Component | Part Number | Specs | Qty | Unit Cost | Total | Notes |
|---------|-----------|-------------|-------|-----|-----------|-------|-------|
| **Power Stage** |
| Q1, Q2 | IGBT | IKW40N120H3 | 1200V, 40A, TO-247 | 2 | $3.50 | $7.00 | Main switching devices |
| C1 | DC Bus Cap (Electrolytic) | Panasonic EETHC2G101EA | 100µF, 450V | 1 | $3.00 | $3.00 | Bulk storage |
| C2, C3 | DC Bus Cap (Film) | EPCOS B32776G1225K | 2.2µF, 1kV, PP | 2 | $2.50 | $5.00 | High-frequency decoupling |
| C4 | Resonant Cap | TDK B32674D4224K | 0.22µF, 1kV, 50A RMS | 1 | $5.00 | $5.00 | Critical component |
| L1 | Induction Coil | Custom Litz wire | 100µH, 40A RMS, 250mm | 1 | $15.00 | $15.00 | Core of induction heating |
| R1, R2 | Snubber Resistor | Vishay PR02 | 47Ω, 2W | 2 | $0.30 | $0.60 | dv/dt reduction |
| C5, C6 | Snubber Cap | TDK C5750X7S2W223K | 22nF, 1.5kV, X7S | 2 | $0.80 | $1.60 | dv/dt reduction |
| **Gate Drive** |
| U1 | Gate Driver | UCC21550ADWR | Dual isolated, 5kVrms | 1 | $5.00 | $5.00 | Drives both IGBTs |
| R3, R4 | Gate Resistor | Yageo MFR-25FBF | 3.3Ω, 1/4W, 1% | 2 | $0.05 | $0.10 | Controls di/dt |
| R5, R6 | Gate-Emitter Resistor | Yageo CFR-25 | 10kΩ, 1/4W | 2 | $0.02 | $0.04 | Noise immunity |
| D1 | Bootstrap Diode | Vishay UF4007 | 1kV, 1A, fast | 1 | $0.15 | $0.15 | For high-side boot |
| C7 | Bootstrap Cap | Murata GRM31CR71H106K | 10µF, 50V, X7R | 1 | $0.30 | $0.30 | High-side supply |
| C8, C9 | VDD Bypass | Murata GRM188R71C104K | 100nF, 16V, X7R | 2 | $0.05 | $0.10 | Driver supply filtering |
| C10 | VCCI Bypass | Murata GRM188R71C104K | 100nF, 16V, X7R | 1 | $0.05 | $0.05 | Logic supply filtering |
| **Control & Interface** |
| U2 | Microcontroller | STM32F103C8T6 | 72MHz, PWM, ADC | 1 | $2.00 | $2.00 | Generates PWM, control logic |
| U3 | Isolated ADC | AMC1301 | Isolated current sense | 1 | $3.00 | $3.00 | DC bus current measurement |
| R7 | Current Shunt | Vishay WSL2512 | 0.01Ω, 2W | 1 | $0.50 | $0.50 | Current sensing |
| U4 | Temp Sensor | MCP9700 | Analog output, TO-92 | 1 | $0.50 | $0.50 | Heatsink temperature |
| **Power Supply** |
| U5 | 15V Regulator | LM7815 | 15V, 1A, TO-220 | 1 | $0.50 | $0.50 | Gate drive supply |
| U6 | 5V Regulator | LM7805 | 5V, 1A, TO-220 | 1 | $0.40 | $0.40 | Logic supply |
| C11-C14 | Supply Bypass Caps | Various | 100µF + 100nF each rail | 8 | $0.10 | $0.80 | Filtering |
| **Thermal & Mechanical** |
| HS1 | Heatsink | Aavid 577102B00 | 0.9 K/W @ 2m/s, 100mm | 1 | $8.00 | $8.00 | Aluminum extrusion |
| FAN1 | Cooling Fan | Sunon MF50101V | 50mm, 12V, 0.1A | 1 | $3.00 | $3.00 | Forced air cooling |
| - | Thermal Pad | Bergquist Sil-Pad K10 | TO-247 size, per device | 2 | $0.50 | $1.00 | Electrical insulation |
| - | Thermal Grease | Arctic MX-4 | (small amount per device) | - | $0.20 | $0.20 | Thermal interface |
| - | Mounting Hardware | M3 screws, washers, nuts | Insulating shoulder washers | 2 sets | $0.25 | $0.50 | IGBT mounting |
| **PCB** |
| - | Printed Circuit Board | Custom 4-layer | FR-4, 2oz copper, 160×100mm | 1 | $10.00 | $10.00 | Main board |
| **Total** | | | | | | **$73.34** | Approximate, bulk pricing |

**Notes**:
- Prices are approximate (bulk quantities, 2024 USD)
- Add ~30% for smaller quantities or distributor markup
- Excludes: Enclosure, AC input filtering, user interface, connectors
- Full induction cooker: Add ~$30 for AC input stage, safety, enclosure

### 10.2 Alternative/Equivalent Components

| Function | Primary Choice | Alternative 1 | Alternative 2 | Notes |
|----------|---------------|---------------|---------------|-------|
| IGBT | IKW40N120H3 (Infineon) | STGW40H120D (ST) | FGA40N120 (Fairchild) | Similar specs, verify pinout |
| Gate Driver | UCC21550 (TI) | FOD3182 (Onsemi) | SI8271 (Silicon Labs) | Isolation ratings vary |
| Resonant Cap | TDK B32674 | EPCOS B32778 | KEMET C4AESBN | Must be high AC current rated |
| DC Bus Cap | Panasonic EETHC2G | Nichicon LGU2G | Rubycon 450BXC | 450V, low ESR aluminum |

---

## 11. Troubleshooting

### 11.1 Common Issues and Solutions

| Symptom | Possible Cause | Diagnostic Steps | Solution |
|---------|---------------|------------------|----------|
| **IGBT doesn't turn ON** | No gate voltage | Measure VGE: Should be 15V when ON | Check gate driver output, supply voltage (VDD) |
| | Gate threshold not reached | Measure VGE, compare to Vth (5-6.5V) | Increase VGE to 15V |
| | Damaged IGBT | Measure VCE: Should be <3V when ON with load | Replace IGBT |
| **IGBT doesn't turn OFF** | Gate drive stuck high | Measure VGE: Should be 0V when OFF | Check microcontroller PWM output, driver input |
| | Shoot-through latch | Both Q1 and Q2 conducting (huge current) | Emergency shutdown! Add dead time (>0.5µs) |
| | Latch-up (internal NPN triggered) | Excessive dv/dt or di/dt during switching | Add snubbers, slow down switching (increase RG) |
| **Excessive heating** | High conduction loss | Measure VCEsat: Should be <2.5V @ rated current | Check VGE (ensure 15V), verify IGBT not degraded |
| | High switching loss | Calculate Eon/Eoff from current/voltage waveforms | Reduce fsw, optimize ZVS, add snubbers |
| | Poor heatsink contact | Measure Tc (heatsink temp): Should be <100°C | Reapply thermal compound, check mounting torque |
| | Insufficient cooling | Measure Tc, check fan operation | Verify fan running, increase airflow |
| **Overvoltage spikes** | Parasitic inductance | Scope: V(SW) shows >400V spikes during turn-off | Add snubbers, reduce trace inductance, check bus caps |
| | Inadequate snubber | Snubber not placed close to IGBT | Move snubber to IGBT pins, use shorter leads |
| **No resonant current** | Open circuit in tank | Measure V(SW): Should be square wave | Check Cres, Lcoil connections, look for broken traces |
| | Wrong resonant frequency | Coil current very low or distorted | Measure L and C, calculate f_res, adjust fsw |
| | Coil far from cookware | Current flows but no heating | Place ferromagnetic pot on coil |
| **Oscillation/instability** | Gate oscillation | Scope: VGE shows high-frequency ringing | Add ferrite bead on gate, check RG, reduce gate loop inductance |
| | Parasitic resonance in power stage | V(SW) or IC shows unexpected oscillations | Add damping (RC snubber), check PCB layout |
| **IGBT fails immediately** | Overvoltage | IGBT shorts after turn-on | Check VDC (should be <600V), add TVS protection |
| | Shoot-through | Both IGBTs ON simultaneously | Add/increase dead time, verify logic |
| | Overcurrent | No current limiting | Add current sense and fast shutdown |
| | Overtemperature | Junction exceeded 175°C | Improve cooling, reduce power |
| **High EMI** | Fast di/dt, dv/dt | EMI testing fails | Increase RG (slow down switching), add snubbers |
| | Poor grounding | Ground loops, inadequate filtering | Implement star grounding, add common-mode choke |
| | Inadequate shielding | Radiated emissions high | Shield coil, use metal enclosure |

### 11.2 Measurement and Testing Procedures

#### 11.2.1 Static Tests (Power OFF)

1. **Gate-Emitter Resistance**:
   ```
   - Set multimeter to diode test mode
   - Measure G to E: Should show ~1-2V forward drop in one direction (internal Zener/diode)
   - Reverse: Open circuit
   - If short (<1Ω) in both directions: IGBT failed
   ```

2. **Collector-Emitter Resistance**:
   ```
   - Measure C to E with VGE = 0V: Should be open circuit (>1MΩ)
   - If <100kΩ: IGBT likely shorted (failed)
   ```

3. **Diode Check**:
   ```
   - Measure E to C (forward): Should show ~0.6-0.8V (freewheeling diode)
   - Measure C to E (reverse): Open circuit
   ```

4. **Insulation Test**:
   ```
   - Measure Collector tab to heatsink: >1MΩ (preferably >10MΩ)
   - If <100kΩ: Insulation pad failed or missing
   ```

#### 11.2.2 Dynamic Tests (Power ON - Use Caution!)

**Safety First**:
- Use isolated oscilloscope probes (differential probes for high voltage)
- Wear safety glasses
- Have emergency power-off switch within reach
- Start at low power (reduced VDC or reduced duty cycle)

1. **Gate Drive Verification**:
   ```
   - Probe: VGE (gate to emitter)
   - Expected: Clean 0/15V square wave
   - Rise/fall time: 50-200ns (depending on RG)
   - No overshoot >20V, no undershoot <-2V
   ```

2. **Switch Node Waveform**:
   ```
   - Probe: V(SW) relative to ground
   - Expected: Square wave, 0V to VDC
   - Allowable overshoot: <10% above VDC (e.g., <330V for 300V bus)
   - Check for ringing (damped sinusoid OK if <50V amplitude)
   ```

3. **VCEsat Measurement**:
   ```
   - Probe: VCE while IGBT is ON (conducting)
   - Method: V(Collector) - V(Emitter) during ON state (zoom in on low voltage scale)
   - Expected: 1.8-2.5V @ 20-40A
   - If >3.5V: Insufficient gate drive or failing IGBT
   ```

4. **Coil Current**:
   ```
   - Method: Current probe (AC/DC type, >50A, >1MHz bandwidth)
   - Expected: Sinusoidal current, peak 20-50A
   - Phase: Lagging V(SW) if operating above resonance (ZVS condition)
   - Check for distortion, clipping, or excessive harmonics
   ```

5. **Power Measurement**:
   ```
   - DC Input: V(VDC) × I(DC_bus) averaged
   - AC Output: Measure with AC power meter on induction coil
   - Efficiency: η = P_out / P_in (typically 90-95%)
   ```

### 11.3 Failure Modes and Root Causes

| Failure Mode | Visual/Electrical Signs | Root Cause | Prevention |
|--------------|------------------------|------------|------------|
| **Junction Meltdown** | Package bulged, cracked, burned smell | Extreme overtemperature (>200°C) | Proper heatsinking, thermal monitoring |
| **Short Circuit Failure** | C-E shorted (0Ω resistance) | Excessive current, shoot-through, latch-up | Current limiting, dead time, soft turn-off |
| **Gate Oxide Breakdown** | G-E short or very low R | ESD, overvoltage on gate (>±20V) | Gate clamp diodes, careful handling (ESD precautions) |
| **Bond Wire Liftoff** | Intermittent conduction, rising RDS(on) | Thermal cycling, poor die attach | Avoid rapid temperature changes, proper power cycling |
| **Package Cracking** | Visible crack, loss of isolation | Mechanical stress (overtightening screw) | Correct mounting torque (0.6 Nm), even pressure |

---

## 12. Additional Resources

### 12.1 Datasheets and Application Notes

**IKW40N120H3 Specific**:
1. **Datasheet**: [IKW40N120H3 Datasheet (Infineon)](https://www.infineon.com/dgdl/Infineon-IKW40N120H3-DS-v01_20-EN.pdf?fileId=db3a30433fa9412f013fbe32b1031661)
2. **Application Note AN2010-07**: "Paralleling of IGBT Modules" - Infineon
3. **Application Note AN4382**: "Gate Resistor in IGBT Applications" - Infineon
4. **Application Note AN2012-10**: "Thermal Interface Materials for Power Semiconductors" - Infineon

**Induction Heating Design**:
1. **AN-1044**: "Induction Cooking with IGBTs" - Fairchild (now Onsemi)
2. **SLUA719**: "Designing Induction Cookers with IGBTs and Resonant Topologies" - Texas Instruments
3. **AN4067**: "Resonant LLC Converter Design" - STMicroelectronics (applicable principles)

**Gate Drive Design**:
1. **UCC21550 Datasheet**: [TI UCC21550 Datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf)
2. **SLUA618**: "Isolated Half-Bridge Gate Driver Design" - Texas Instruments
3. **AN608**: "Bootstrap Component Selection for Control IC" - Microchip

### 12.2 Standards and Compliance

**Safety Standards**:
- **IEC 60335-2-6**: Household and Similar Electrical Appliances - Part 2-6: Particular requirements for stationary cooking ranges, hobs, ovens and similar appliances
- **UL 858**: Household Electric Ranges (US safety standard)
- **EN 60335-2-6**: European version of IEC standard

**EMC Standards**:
- **FCC Part 15 Class B**: Electromagnetic compatibility for residential devices (US)
- **EN 55014**: Electromagnetic compatibility - Requirements for household appliances (EU)
- **CISPR 14-1**: Electromagnetic compatibility - Requirements for household appliances, electric tools and similar apparatus - Part 1: Emission

**Energy Efficiency**:
- **EU Regulation 66/2014**: Ecodesign requirements for domestic cooking appliances
- **Energy Star**: Residential Induction Ranges/Cooktops (voluntary, US)

### 12.3 Simulation Tools

**SPICE Simulators**:
1. **ngspice**: Open-source SPICE simulator ([ngspice.sourceforge.net](http://ngspice.sourceforge.net/))
   - Command-line and scripting
   - Powerful for batch simulations
   - Used in KiCad

2. **LTspice**: Free SPICE simulator from Analog Devices ([analog.com/ltspice](https://www.analog.com/en/design-center/design-tools-and-calculators/ltspice-simulator.html))
   - Windows/Mac/Linux
   - User-friendly GUI
   - Large component library

3. **KiCad + ngspice**: Integrated schematic capture and simulation
   - Open-source PCB design tool
   - Built-in SPICE engine
   - Visual waveform viewing

**Power Electronics Simulators**:
1. **PLECS**: Specialized power electronics simulator ([plexim.com](https://www.plexim.com/))
   - Accurate thermal and magnetic models
   - Fast simulation (compared to SPICE)
   - Commercial ($$$)

2. **PSIM**: Power simulation software ([powersimtech.com](https://powersimtech.com/))
   - Motor drive and power converter focus
   - Thermal module available
   - Commercial ($$)

### 12.4 Design Calculators and Tools

**Online Calculators**:
1. **Resonant Frequency Calculator**: [calculator.net/resonant-frequency-calculator](https://www.calculator.net/resonance-calculator.html)
2. **Thermal Resistance Calculator**: [heatsinkcalculator.com](https://www.heatsinkcalculator.com/)
3. **PCB Trace Width Calculator**: [4pcb.com/trace-width-calculator](https://www.4pcb.com/trace-width-calculator.html)

**Design Software**:
1. **MATLAB/Simulink**: System-level modeling and control design
2. **Ansys Maxwell**: Electromagnetic field simulation (for coil design)
3. **TI Webench**: Power supply design tool (includes gate driver selection)

### 12.5 Learning Resources

**Books**:
1. *"Power Electronics: Converters, Applications, and Design"* - Mohan, Undeland, Robbins
   - Comprehensive textbook, covers IGBT applications
2. *"IGBT Theory and Design"* - Baliga
   - Deep dive into IGBT physics and operation
3. *"Electromagnetic Induction Heating"* - Haimbaugh
   - Theory and practice of induction heating systems

**Online Courses**:
1. **Coursera: Power Electronics** - University of Colorado Boulder
2. **edX: Power Electronics Specialization** - CU Boulder (Prof. Robert Erickson)
3. **YouTube: Power Electronics Tutorials** - Sam Ben-Yaakov (Technion)

**Forums and Communities**:
1. **EEVblog Forum**: Electronics design discussion ([eevblog.com/forum](https://www.eevblog.com/forum/))
2. **EDA Board**: Electronics design and simulation ([edaboard.com](https://www.edaboard.com/))
3. **Stack Exchange - Electrical Engineering**: Q&A site ([electronics.stackexchange.com](https://electronics.stackexchange.com/))

---

## Appendix A: Quick Reference Formulas

### A.1 Resonant Tank Calculations

| Parameter | Formula | Example (L=100µH, C=0.22µF) |
|-----------|---------|----------------------------|
| Resonant Frequency | f₀ = 1 / (2π√(LC)) | f₀ = 1 / (2π√(100µH × 0.22µF)) ≈ 33.9kHz |
| Characteristic Impedance | Z₀ = √(L/C) | Z₀ = √(100µH / 0.22µF) ≈ 21.3Ω |
| Quality Factor | Q = Z₀ / R = (1/R)√(L/C) | Q = 21.3Ω / 0.5Ω ≈ 42.6 (high Q, narrow bandwidth) |
| Current at Resonance | I = V / R | I = 300V / 0.5Ω = 600A (theoretical, without load!) |
| Operating Above Resonance | fsw > f₀ → Inductive load | fsw = 50kHz > 33.9kHz ✓ |

### A.2 Power Dissipation

| Loss Type | Formula | Typical Value (IKW40N120H3 @ 3kW) |
|-----------|---------|-----------------------------------|
| Conduction Loss | Pcond = VCEsat × IC(avg) × D | ≈ 2.5V × 25A × 0.45 ≈ 28W |
| Turn-On Loss | Pon = Eon × fsw | ≈ 0.7mJ × 50kHz ≈ 35W (with ZVS) |
| Turn-Off Loss | Poff = Eoff × fsw | ≈ 2.6mJ × 50kHz ≈ 130W |
| Diode Conduction | PD_cond = VF × IF(avg) | ≈ 2.5V × 5A ≈ 12.5W |
| Diode Recovery | PD_rec = Qrr × VDC × fsw | ≈ 4.3µC × 300V × 50kHz ≈ 64.5W |
| **Total** | Ptot = Pcond + Pon + Poff + PD_cond + PD_rec | ≈ 270W (worst case, ~150W with good ZVS) |

### A.3 Thermal Management

| Calculation | Formula | Example |
|-------------|---------|---------|
| Junction Temperature | Tvj = Tc + (Rth(j-c) × Pdiss) | Tvj = 80°C + (0.31K/W × 150W) = 126.5°C |
| Case Temperature | Tc = Ta + [(Rth(interface) + Rth(heatsink)) × Pdiss] | Tc = 40°C + (1.3K/W × 150W) = 235°C (need better cooling!) |
| Required Heatsink Rth | Rth(sink) = [(Tvj(max) - Ta) / Pdiss] - Rth(j-c) - Rth(interface) | Rth = (125-40)/150 - 0.31 - 0.5 ≈ 0.06 K/W (challenging!) |

### A.4 Gate Drive

| Parameter | Formula | Value for IKW40N120H3 |
|-----------|---------|----------------------|
| Gate Charge Energy | Edrv = QG × VGE × fsw | E = 185nC × 15V × 50kHz = 0.14W (negligible) |
| Bootstrap Cap Size | Cboot ≥ N × QG / ΔV | Cboot ≥ 20 × 185nC / 1V ≈ 3.7µF (use 10µF) |
| Gate Resistor Power | PRG = (VGE²/RG) × D × fsw (simplified) | Typically <0.1W |
| Turn-On Time (est.) | ton ≈ RG × Cies × ln(VGG/(VGG-Vth)) | Simplified; see datasheet curves |

---

## Appendix B: Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-12-10 | Initial release - comprehensive design guide |

---

## Appendix C: Disclaimer and Warranty

**IMPORTANT NOTICE**:

This documentation is provided for **educational and reference purposes only**. The information is believed to be accurate, but **no warranty of any kind** is provided, either expressed or implied, including but not limited to:
- Fitness for a particular purpose
- Merchantability
- Non-infringement

**User Responsibilities**:
- Verify all specifications against official datasheets before finalizing designs
- Perform thorough testing and validation of any circuits based on this guide
- Ensure compliance with all applicable safety standards and regulations
- Use proper engineering practices and safety precautions

**High Voltage Warning**:
The circuits described in this document operate at **potentially lethal voltages** (>300V DC). Improper design, construction, or operation can result in:
- Electric shock causing serious injury or death
- Fire hazard
- Equipment damage

Only qualified personnel with appropriate training and equipment should work with these circuits.

**Liability**:
The author(s) and contributors assume **no liability** for any damages, injuries, or losses resulting from the use or misuse of this information.

---

**END OF DOCUMENT**
