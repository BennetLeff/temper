# UCC21550 Isolated Dual-Channel Gate Driver
## Documentation for Induction Cooker Application

---

## Table of Contents
1. [High-Level Summary](#high-level-summary)
2. [Role in Induction Cooker](#role-in-induction-cooker)
3. [How to Use This Chip](#how-to-use-this-chip)
4. [SPICE Simulation Guide](#spice-simulation-guide)
5. [Safety Information](#safety-information)
6. [Design Considerations](#design-considerations)
7. [Bill of Materials](#bill-of-materials)
8. [PCB Layout Guidelines](#pcb-layout-guidelines)
9. [Troubleshooting](#troubleshooting)
10. [Additional Resources](#additional-resources)

---

## 1. High-Level Summary

### What is the UCC21550?

The **UCC21550** is a reinforced isolated dual-channel gate driver IC from Texas Instruments designed to drive power MOSFETs, IGBTs, SiC MOSFETs, and GaN transistors in high-voltage power conversion applications.

### Key Specifications

| Parameter | Specification |
|-----------|---------------|
| **Peak Source Current** | 4A |
| **Peak Sink Current** | 6A |
| **Isolation Voltage** | 5kVRMS (reinforced) |
| **Common-Mode Transient Immunity (CMTI)** | >125V/ns |
| **Propagation Delay** | 33ns (typical) |
| **Pulse Width Distortion** | 5ns (max) |
| **Operating Temperature** | -40°C to +150°C |
| **Primary Side Supply (VCCI)** | 3.0V to 5.5V |
| **Secondary Side Supply (VDD)** | 6.5V to 25V (A variant)<br>9.2V to 25V (B variant)<br>13.5V to 25V (C variant) |
| **Package Options** | SOIC-16 (DW), SOIC-14 (DWK) |

### Key Features

1. **Reinforced Isolation**: 5kVRMS isolation barrier with >125V/ns CMTI for robust noise immunity
2. **Dual Channel Configuration**: Can be configured as:
   - Dual low-side drivers
   - Dual high-side drivers
   - Half-bridge driver (1 high-side + 1 low-side)
3. **High Drive Strength**: 4A source / 6A sink capability for fast switching
4. **Programmable Dead Time**: Resistor-programmable dead time control
5. **Protection Features**:
   - UVLO on all power supplies
   - Fast disable function
   - Integrated de-glitch filter (5ns)
6. **TTL/CMOS Compatible Inputs**: Direct interface with 3.3V or 5V microcontrollers

---

## 2. Role in Induction Cooker

### Induction Cooker Topology

An induction cooker uses a high-frequency (20-100 kHz) resonant inverter to generate an alternating magnetic field that induces eddy currents in ferromagnetic cookware, producing heat.

```
[AC Mains] → [Rectifier] → [PFC] → [DC Bus (300V)] → [Resonant Inverter] → [Induction Coil]
                                                              ↑
                                                         UCC21550
                                                         Gate Driver
```

### UCC21550 Function in Induction Cooker

The UCC21550 serves as the **isolated gate driver** for the resonant inverter stage, performing these critical functions:

#### 1. **Galvanic Isolation**
- Provides 5kVRMS isolation between low-voltage control circuitry (microcontroller) and high-voltage power stage (300V DC bus)
- Protects sensitive control electronics from high-voltage transients
- Meets safety requirements for line-connected appliances

#### 2. **High-Speed Gate Drive**
- Delivers 4A/6A peak currents to rapidly charge/discharge IGBT or MOSFET gates
- Achieves fast switching transitions to:
  - Minimize switching losses
  - Maintain precise frequency control (critical for resonant operation)
  - Reduce electromagnetic interference (EMI)

#### 3. **Half-Bridge Control**
- Drives both high-side and low-side transistors in the half-bridge inverter
- Generates the alternating voltage across the resonant LC tank (coil + capacitor)
- Ensures proper dead time between switches to prevent shoot-through

#### 4. **Protection and Control**
- Implements UVLO to prevent operation with insufficient supply voltage
- Provides disable function for rapid shutdown in fault conditions
- De-glitch filter prevents false triggering from noise

### Typical Induction Cooker Power Stage

```
                          +VDC (300V)
                               |
                               |
                        ┌──────┴──────┐
                        │             │
                    [Q_HS]          [C_DC]
               ╔════╝ IGBT ╚════╗     │
           VDDA│    High-Side   │     │
      ┌────────┤                │     │
      │  CH A  │   UCC21550     │     │
      │ OUTA───┤                ├─────┤──── SW (Switch Node)
      │        │                │     │
      │  CH B  │                │     │
      │ OUTB───┤   Gate Driver  │     │
      │        │                │     │
      │        │                │     │
      └────────┤                │     │
           VDDB│                │     │
               ╚════╗ IGBT ╔════╝     │
                    [Q_LS]          [C_RES]──[L_COIL]──[GND]
                        │     Low-Side   │      Resonant Tank
                        └──────┬──────┘
                               │
                              GND
```

### Power Flow

1. **Microcontroller** generates complementary PWM signals (INA, INB)
2. **UCC21550** isolates and buffers these signals to drive the power transistors
3. **High-side IGBT (Q_HS)** and **Low-side IGBT (Q_LS)** alternate switching
4. **Switch node voltage** alternates between +VDC and GND
5. **Resonant tank** (C_RES + L_COIL) generates high-frequency AC current
6. **Induction coil** creates alternating magnetic field
7. **Cookware** absorbs energy through eddy current heating

### Why UCC21550 is Ideal for Induction Cookers

| Requirement | UCC21550 Solution |
|-------------|-------------------|
| **High voltage isolation** | 5kVRMS reinforced isolation |
| **Noise immunity** | >125V/ns CMTI handles harsh switching environment |
| **Fast switching (20-100 kHz)** | 4A/6A drive current, 33ns propagation delay |
| **Safety compliance** | UL1577, VDE, CSA certified isolation |
| **Temperature tolerance** | -40°C to +150°C operation near hot cookware |
| **Compact size** | SOIC-16/14 package saves PCB space |
| **Cost effective** | Single IC replaces optocoupler + discrete driver |

---

## 3. How to Use This Chip

### Pin Configuration (16-pin DW Package)

```
         UCC21550
        ┌─────┴─────┐
   INA  │1       16│ VDDA
   INB  │2       15│ OUTA
  VCCI  │3       14│ VSSA
   GND  │4    ═══  │ ← Isolation Barrier
   DIS  │5    ═══  │
    DT  │6    ═══  │
    NC  │7       13│ NC
  VCCI  │8       12│ NC
  VSSB  │9       11│ VDDB
  OUTB  │10───────┘
        └───────────┘
           (Top View)
```

### Pin Descriptions

| Pin | Name | Type | Description |
|-----|------|------|-------------|
| 1 | INA | Input | Input signal for Channel A (TTL/CMOS compatible) |
| 2 | INB | Input | Input signal for Channel B (TTL/CMOS compatible) |
| 3, 8 | VCCI | Power | Primary-side supply (3.0-5.5V), pins tied together |
| 4 | GND | Ground | Primary-side ground reference |
| 5 | DIS | Input | Disable both outputs when HIGH (active high) |
| 6 | DT | Input | Dead time programming resistor connection |
| 7, 12, 13 | NC | - | No connection |
| 9 | VSSB | Ground | Channel B ground reference (isolated) |
| 10 | OUTB | Output | Channel B gate drive output |
| 11 | VDDB | Power | Channel B supply (6.5-25V for A variant) |
| 14 | VSSA | Ground | Channel A ground reference (isolated) |
| 15 | OUTA | Output | Channel A gate drive output |
| 16 | VDDA | Power | Channel A supply (6.5-25V for A variant) |

### Selecting the Right Variant

Three variants with different UVLO thresholds:

| Variant | UVLO Rising | UVLO Falling | Best For |
|---------|-------------|--------------|----------|
| **UCC21550A** | 6.0V | 5.7V | 5V gate drive, general purpose |
| **UCC21550B** | 8.5V | 7.9V | 8-12V gate drive systems |
| **UCC21550C** | 12.5V | 11.5V | 12-15V gate drive systems |

**For induction cookers**: UCC21550A or UCC21550B are most common (12-15V gate drive).

### Basic Half-Bridge Configuration

#### Step 1: Power Supply Design

**Primary Side (VCCI):**
```
[5V Supply] ──┬── 100nF (ceramic, X7R) ──┐
               │                          ├── VCCI (pins 3, 8)
               └─────────────────────────┬── GND (pin 4)
                                         │
                                        GND
```

**Secondary Side (VDD):**

For **high-side** channel (bootstrap supply):
```
[VDD 15V] ──┬── 2.2Ω ──┬──|<|── DBOOT (SiC Schottky, 1200V) ──┬── VDDA (pin 16)
            │           │                                      │
            │           └── 1µF (ceramic, 50V, X7R) ──────────┤
            │                                                  │
            └── 10µF ────────────────────────────────── VSSA (pin 14) ── SW Node
```

For **low-side** channel:
```
[VDD 15V] ──┬── 10µF (ceramic, 50V, X7R) ──┬── VDDB (pin 11)
            │                               │
            │                               │
            └── 220nF (ceramic) ────────────┼── VSSB (pin 9) ── GND
                                            │
                                           GND
```

#### Step 2: Input Signal Conditioning

```
[MCU PWM A] ──┬── 51Ω ──┬── 33pF ──┬── INA (pin 1)
              │          │          │
              └──────────┴──────────┘

[MCU PWM B] ──┬── 51Ω ──┬── 33pF ──┬── INB (pin 2)
              │          │          │
              └──────────┴──────────┘

[MCU DIS] ───────────────────────────── DIS (pin 5)
(tie to GND if not used)
```

**RC Filter values:**
- R = 51Ω (limits current, dampens reflections)
- C = 33pF (filters high-frequency noise)
- Corner frequency ≈ 100 MHz

#### Step 3: Dead Time Programming

**Option 1: No Dead Time** (rely on input signal dead time)
```
DT (pin 6) ── Float or connect to VCCI
```

**Option 2: Interlock Only** (prevent overlap)
```
DT (pin 6) ── 0-150Ω ── GND
```

**Option 3: Programmable Dead Time**
```
DT (pin 6) ── RDT ── GND

Dead Time (ns) = 8.6 × RDT (kΩ) + 13
```

**Example calculations:**
| RDT | Dead Time |
|-----|-----------|
| 10 kΩ | ~100 ns |
| 20 kΩ | ~185 ns |
| 50 kΩ | ~443 ns |
| 100 kΩ | ~873 ns |

**Recommended range:** 1.7kΩ to 100kΩ

#### Step 4: Gate Drive Output Stage

```
OUTA (pin 15) ──┬── ROFF (0Ω) ──┬──|<|── MSS1P4 ──┬── IGBT Gate (HS)
                │                │                 │
                └── RON (2.2Ω) ──┴─────────────────┤
                                                   │
                                      10kΩ ────────┴── IGBT Source (HS)

OUTB (pin 10) ──┬── ROFF (0Ω) ──┬──|<|── MSS1P4 ──┬── IGBT Gate (LS)
                │                │                 │
                └── RON (2.2Ω) ──┴─────────────────┤
                                                   │
                                      10kΩ ────────┴── IGBT Source (LS)
```

**Component selection:**
- **RON** (turn-on resistor): 2.2Ω (limits inrush, controls di/dt)
- **ROFF** (turn-off resistor): 0-1Ω (fast turn-off)
- **Anti-parallel diode**: Schottky (e.g., MSS1P4) for fast turn-off path
- **RGS** (gate-to-source): 10kΩ (holds gate low when driver unpowered)

### Input Signal Requirements

**Logic Levels:**
- VIH (High): >2.0V (typ 2.3V)
- VIL (Low): <1.0V (typ 0.8V)
- Compatible with 3.3V and 5V logic

**Timing:**
- Minimum pulse width: 12ns (typical)
- Maximum frequency: Limited by power dissipation and dead time
- Typical induction cooker: 20-100 kHz

**Dead Time Calculation:**

For half-bridge, ensure sufficient dead time to prevent shoot-through:

```
DT_required = t_fall(Q_HS) + t_off_delay + margin
```

Where:
- t_fall(Q_HS) = High-side IGBT fall time (100-500ns typical)
- t_off_delay = Gate driver turn-off delay (~33ns)
- margin = Safety factor (2-3×)

**Example:** For IGBT with 200ns fall time:
```
DT_required = 200ns + 33ns + (2 × 233ns) = ~700ns minimum
```

### Disable Function

The DIS pin provides fast shutdown:

```
DIS = LOW  (or tied to GND): Normal operation
DIS = HIGH (>2.0V):          Both outputs forced LOW
```

**Response time:** ~48ns typical

**Common uses:**
1. **Overcurrent protection**: Microcontroller detects overcurrent and asserts DIS
2. **Thermal shutdown**: Comparator monitors temperature and asserts DIS
3. **Interlock**: External switch for safety interlock

**RC filter recommended** if DIS connected to MCU:
```
[MCU] ── 51Ω ──┬── 1nF ── DIS (pin 5)
               │
              GND
```

---

## 4. SPICE Simulation Guide

### File Overview

The provided SPICE files include:

1. **UCC21550.lib** - SPICE subcircuit model
2. **UCC21550_test.cir** - Example test netlist for half-bridge induction cooker

### Running Simulations in ngspice

#### Installation

**Linux/macOS:**
```bash
# Ubuntu/Debian
sudo apt-get install ngspice

# macOS (Homebrew)
brew install ngspice
```

**Windows:**
Download from: http://ngspice.sourceforge.net/download.html

#### Running the Test Circuit

```bash
cd /path/to/UCC21550/
ngspice UCC21550_test.cir
```

This will:
1. Load the model and test circuit
2. Run transient simulation for 100µs (5 switching cycles at 50kHz)
3. Generate plots of key waveforms
4. Measure propagation delay and dead time

#### Expected Simulation Results

**Waveform: Input Signals (INA, INB)**
```
INA: __|‾‾‾‾‾‾‾‾‾|________|‾‾‾‾‾‾‾‾‾|________|
INB: ‾‾‾‾‾‾‾‾|________|‾‾‾‾‾‾‾‾|________|‾‾‾‾‾
     ←─ DT ──→
```
- Frequency: 50 kHz (20µs period)
- Duty cycle: 45% each (9µs on, 11µs off)
- Dead time: 1µs between transitions

**Waveform: Gate Drive Signals (GATE_HS, GATE_LS)**
```
         15V ┤     ┌────┐     ┌────┐
GATE_HS   0V ┤─────┘    └─────┘    └─────
              ←33ns→ Propagation delay

         15V ┤──┐    ┌──┐    ┌──┐
GATE_LS   0V ┤  └────┘  └────┘  └────
```
- Amplitude: 0-15V (VDD level)
- Propagation delay: ~33ns from input edge to output 50% point
- Rise/fall time: ~20-50ns (depends on gate load)

**Waveform: Switch Node (SW)**
```
       300V ┤  ┌──┐  ┌──┐  ┌──┐
         SW ┤──┘  └──┘  └──┘  └──
          0V
```
- Alternates between 0V (LS on) and 300V (HS on)
- Rise/fall time: 50-200ns (depends on IGBT characteristics)
- Ringing may occur due to parasitics

**Waveform: Inductor Current (I_COIL)**
```
        +10A ┤    ╱╲    ╱╲    ╱╲
             ┤   ╱  ╲  ╱  ╲  ╱  ╲
 I_COIL    0A ┤──╯    ╲╱    ╲╱    ╲─
             ┤
        -10A ┤
```
- Sinusoidal (resonant operation)
- Frequency: ~50 kHz (same as switching)
- Amplitude: Depends on DC bus voltage, load Q-factor

#### Key Measurements

The simulation automatically measures:

1. **Propagation Delay:**
   ```
   prop_delay_hs = 33ns (typical)
   ```
   Time from INA rising edge to GATE_HS reaching 50%

2. **Dead Time:**
   ```
   dead_time = 1.0us (as programmed in input signals)
   ```
   Time between GATE_LS falling to 50% and GATE_HS rising to 50%

3. **Output Current:**
   - Peak source current: ~4A
   - Peak sink current: ~6A

### Validating the SPICE Model

#### Verification Checklist

| Parameter | Expected | How to Verify | Pass Criteria |
|-----------|----------|---------------|---------------|
| **Propagation Delay** | 26-45ns | Measure INA→OUTA delay | Within datasheet limits |
| **Pulse Width Distortion** | <5ns | Compare input/output pulse widths | PWD < 5ns |
| **Output Drive Strength** | 4A source, 6A sink | Measure peak gate current | Currents achieved |
| **UVLO Function** | Outputs low when VCC<2.7V or VDD<6.0V | Step supply voltages | Outputs held low |
| **Rise/Fall Time** | ~8ns (1.8nF load) | Measure 20%-80% transition | Matches typical curves |
| **Dead Time Programming** | DT(ns) = 8.6×RDT(kΩ)+13 | Sweep RDT values | Linear relationship |
| **Disable Function** | Outputs low when DIS>2.0V | Assert DIS high | Both outputs go low |
| **CMTI** | >125V/ns | Apply fast dV/dt to VSSx | Outputs remain stable |

#### Verification Tests

**Test 1: Propagation Delay**

```spice
* Measure on rising edge
.meas tran t_in WHEN V(INA)=1.65 RISE=1
.meas tran t_out WHEN V(OUTA)=7.5 RISE=1
.meas tran tPD PARAM='t_out - t_in'
.print tPD

* Expected: 26ns < tPD < 45ns
```

**Test 2: UVLO Functionality**

```spice
* Ramp VCC from 0 to 5V
VCC VCCI 0 PWL(0 0 100u 5)

* Verify outputs remain low until VCC > 2.7V
.meas tran t_uvlo WHEN V(VCCI)=2.7 CROSS=1
.meas tran v_out_before FIND V(OUTA) AT='t_uvlo-1n'
.meas tran v_out_after FIND V(OUTA) AT='t_uvlo+10u'

* Expected: v_out_before ≈ 0V, v_out_after > 10V (if input HIGH)
```

**Test 3: Drive Strength**

Add scope probe to measure gate current:
```spice
* Insert current measurement resistor
R_SENSE OUTA N_GATE 0.01

* Measure peak current
.meas tran i_peak_source MAX I(R_SENSE) FROM=0 TO=100u
.meas tran i_peak_sink MIN I(R_SENSE) FROM=0 TO=100u

* Expected: i_peak_source > 3A, i_peak_sink < -5A
```

#### Model Limitations and Assumptions

The provided behavioral model simplifies certain aspects:

**Included:**
- ✓ Propagation delay (33ns typical)
- ✓ Output drive strength (4A/6A)
- ✓ UVLO thresholds and hysteresis
- ✓ Input thresholds (TTL/CMOS)
- ✓ Pull-up/pull-down resistors
- ✓ Disable function
- ✓ Output impedance (ROH, ROL)

**Simplified/Omitted:**
- ✗ Temperature dependence (model uses 25°C values)
- ✗ Dead time programming (not fully implemented in behavioral model)
- ✗ Propagation delay matching between channels (assumed identical)
- ✗ CMTI effects (isolation barrier idealized)
- ✗ Internal power dissipation (no thermal modeling)
- ✗ Pulse width distortion variations
- ✗ EMI/noise coupling

**Recommendations for accurate simulation:**
1. Use model for functional verification and timing analysis
2. Validate critical parameters with hardware testing
3. Add external parasitics (PCB traces, package inductance) for realistic waveforms
4. Use temperature sweeps cautiously (model parameters are constant)

### Modifying the Test Circuit

#### Changing Switching Frequency

Edit the PULSE sources:
```spice
* For 100 kHz (10us period):
VIN_HS INA 0 PULSE(0 3.3 0 10n 10n 4.5u 10u)
*                                    ↑      ↑
*                                  T_ON  PERIOD
```

#### Adding Different Dead Time

Adjust the phase offset between INA and INB:
```spice
* For 500ns dead time at 50kHz:
VIN_HS INA 0 PULSE(0 3.3 0    10n 10n 9.0u  20u)
VIN_LS INB 0 PULSE(0 3.3 10.5u 10n 10n 9.0u 20u)
*                        ↑
*                  Offset creates dead time
```

#### Using Different Transistor Models

Replace the simplified IGBT model with a vendor-specific model:
```spice
* Include Infineon IKW40N120H3 model (example)
.include IKW40N120H3.lib

* Replace generic IGBT
Q_HS VDC HS_GATE SW IKW40N120H3
Q_LS SW LS_GATE 0 IKW40N120H3
```

#### Varying Gate Resistance

Change R_G values to see effect on switching speed:
```spice
R_G_HS_ON GATE_HS HS_GATE 5.0  ; Slower switching
R_G_HS_ON GATE_HS HS_GATE 1.0  ; Faster switching
```

**Trade-off:**
- Lower resistance → Faster switching, more ringing, higher EMI
- Higher resistance → Slower switching, less ringing, higher switching loss

### Using in KiCad

#### Adding Model to KiCad

1. **Copy library file:**
   ```bash
   cp UCC21550.lib ~/kicad/spice/
   ```

2. **In KiCad Schematic Editor:**
   - Right-click UCC21550 symbol → Properties → Simulation Model
   - Select "Subcircuit" type
   - Browse to `UCC21550.lib`
   - Select subcircuit: `UCC21550A`, `UCC21550B`, or `UCC21550C`
   - Map symbol pins to model pins

3. **Run simulation:**
   - Tools → Simulator
   - Configure transient analysis
   - Run and plot signals

#### Expected KiCad Simulation Results

Should match ngspice results:
- Propagation delay: 26-45ns
- Output swing: 0 to VDD
- Drive current capability visible in gate charging waveform

---

## 5. Safety Information

### ⚠️ WARNING: High Voltage Device

The UCC21550 is used in applications with **lethal voltages** (>300V DC in induction cookers). Improper use can result in:
- **Electric shock** (potentially fatal)
- **Fire hazard** (component failure, PCB arcing)
- **Equipment damage**

### Critical Safety Requirements

#### 1. Isolation Barrier Integrity

**DO NOT compromise the isolation barrier:**

✗ **NEVER:**
- Place copper traces across the isolation barrier
- Drill holes or create slots in isolation region
- Allow solder bridging across barrier
- Place components straddling the barrier

✓ **ALWAYS:**
- Maintain ≥8mm creepage distance (air path)
- Maintain ≥8mm clearance distance (surface path)
- Use PCB cutout or keep-out zone under IC
- Follow PCB layout guidelines (see Section 8)

**Minimum Distances:**
| Specification | Minimum | Recommended |
|---------------|---------|-------------|
| Clearance (through air) | 8mm | 10mm |
| Creepage (over surface) | 8mm | 10mm |
| PCB slot width | Not required | 3mm (optional) |

#### 2. Voltage Ratings - Absolute Maximum

**DO NOT EXCEED:**

| Pin | Absolute Maximum | Notes |
|-----|------------------|-------|
| VCCI to GND | 6V | Primary side supply |
| VDDA, VDDB to VSSx | 30V | Output side supply |
| OUTA to VSSA, OUTB to VSSB (DC) | VDDA/B + 0.3V | Steady state |
| OUTA to VSSA, OUTB to VSSB (transient) | VDDA/B + 0.3V | For 200ns |
| INA, INB, DIS to GND | VCCI + 0.3V (max 6V) | Input pins |
| VSSA to VSSB (DWK package) | 1850V | Channel isolation |
| Isolation voltage | 5000VRMS (1 min test) | Primary to secondary |

**Overvoltage Protection:**
- Add TVS diodes on OUTA/OUTB if gate voltage can exceed VDDx
- Use gate-to-source clamping diodes for ringing suppression
- Never exceed 30V on VDDx pins

#### 3. Temperature Limits

| Parameter | Min | Max | Notes |
|-----------|-----|-----|-------|
| Operating Junction Temp (TJ) | -40°C | +150°C | Continuous |
| Storage Temp (Tstg) | -65°C | +150°C | Non-operating |
| Lead Temperature (Soldering) | - | 260°C | 10 seconds max |

**Thermal Management:**
- Calculate power dissipation (see datasheet Section 8.2.2.5)
- Ensure TJ < 150°C under worst-case conditions
- Use thermal relief if necessary (heatsink, airflow)
- **For induction cooker:** Mount away from hot areas near cookware

**Power Dissipation Estimation:**
```
P_GD ≈ 2 × VDD × QG × fSW

Where:
- VDD = Gate drive voltage (e.g., 15V)
- QG = Total gate charge of power transistor (e.g., 200nC)
- fSW = Switching frequency (e.g., 50kHz)

Example:
P_GD = 2 × 15V × 200nC × 50kHz = 300mW
```

Add quiescent current contribution (~100-200mW).

**If P_GD > 500mW:** Review thermal design carefully.

#### 4. ESD Protection

**ESD Ratings:**
- Human Body Model (HBM): ±2000V (all pins)
- Charged Device Model (CDM): ±1000V (all pins)

**Handling Precautions:**
- Use ESD wrist strap when handling PCBs
- Store in ESD-safe packaging
- Ground soldering iron tip
- Avoid touching pins

#### 5. Gate Drive Safety

**Shoot-Through Prevention:**

Ensure adequate dead time to prevent high-side and low-side transistors conducting simultaneously (shoot-through):

```
Dead Time > t_fall(Q1) + t_off(driver) + 2×(t_rise(Q2) + t_on(driver))

Where:
- t_fall(Q1) = Turn-off falling time of first transistor
- t_off(driver) = Driver turn-off propagation delay (33ns typ)
- t_rise(Q2) = Turn-on rising time of second transistor
- t_on(driver) = Driver turn-on propagation delay (33ns typ)
```

**Minimum safe dead time: 500ns for typical IGBTs**

**Consequences of shoot-through:**
- Extremely high current through transistors (DC bus shorted)
- Transistor destruction (junction overheating)
- Potential explosion of power devices
- Fire hazard

**Protection measures:**
1. Program adequate dead time (DT pin or input signals)
2. Use hardware interlock (DT pin with resistor)
3. Monitor DC bus current (crowbar detection)
4. Implement fast disable (DIS pin)

#### 6. Bootstrap Supply Safety

For high-side gate drive, bootstrap capacitor (CBOOT) charges from VDD through bootstrap diode:

**⚠️ WARNING: Bootstrap Supply Failures**

**Symptom:** VDDA-VSSA voltage drops below UVLO during operation

**Causes:**
1. CBOOT too small (insufficient charge)
2. High duty cycle (>95%) - insufficient refresh time
3. Bootstrap diode failure (open or high leakage)
4. Excessive load (gate drive frequency too high)

**Consequences:**
- High-side transistor turns off unexpectedly (hard switching)
- Low-side transistor turns on with inductor current flowing
- Voltage spike on switch node (L×di/dt)
- Potential transistor avalanche breakdown
- EMI generation

**Prevention:**
1. Use CBOOT ≥ 1µF (ceramic, X7R, 50V)
2. Ensure duty cycle < 90% (allow bootstrap refresh)
3. Use quality bootstrap diode (SiC Schottky, 1200V, <10ns trr)
4. Add series resistor (2.2Ω) to limit inrush
5. Monitor VDDA voltage in critical applications

#### 7. Input Signal Integrity

**⚠️ WARNING: Noise on Input Pins**

False triggering of INA/INB can cause unexpected switching:

**Causes:**
- EMI coupling from switch node or resonant tank
- Ground bounce from high di/dt switching
- Power supply noise

**Prevention:**
1. Use RC filters on INA, INB (51Ω + 33pF recommended)
2. Route input traces away from high-voltage/high-current areas
3. Use ground plane under input pins
4. Add ferrite bead on input traces if needed
5. Keep VCCI decoupling capacitor close (<5mm)

**De-glitch Filter:**
- UCC21550 has built-in 5ns de-glitch filter
- Pulses shorter than 5ns are rejected
- Not sufficient for severe EMI environment - add external filter

#### 8. Regulatory Compliance

The UCC21550 is certified for isolated applications:

| Standard | Certification | Notes |
|----------|---------------|-------|
| UL 1577 | 5000VRMS isolation | Component recognition |
| VDE 0884-17 | Reinforced isolation | 1500VRMS working voltage |
| CSA | Component acceptance | Canadian safety |
| CQC | GB4943.1-2011 | Chinese certification |

**For induction cooker end product:**
- UCC21550 certification is at **component level**
- **System-level certification required:**
  - IEC 60335-2-6 (Household cooking appliances)
  - IEC 60335-1 (General safety)
  - FCC Part 15 (EMI)
  - CISPR 11 (Industrial EMI)
- **PCB design must maintain isolation specs**
- Additional insulation may be required at system level

#### 9. Fault Conditions

**Overcurrent Event:**

1. **Detection:** Current sense resistor + comparator
2. **Action:** Assert DIS pin HIGH
3. **Response time:** ~48ns to outputs OFF
4. **Recovery:** Microcontroller removes DIS after fault cleared

**Overvoltage Event:**

1. **Detection:** Voltage monitor on DC bus
2. **Action:** Stop PWM signals (INA=INB=LOW)
3. **Response time:** Depends on MCU, typically <1µs
4. **Backup:** Crowbar circuit (thyristor) for catastrophic overvoltage

**Overtemperature Event:**

1. **Detection:** NTC thermistor near power transistors
2. **Action:** Reduce PWM duty cycle or shutdown
3. **Recovery:** Hysteretic control with sufficient margin

**Bootstrap Failure:**

1. **Detection:** Monitor VDDA-VSSA voltage with ADC
2. **Action:** Reduce frequency or duty cycle
3. **Alert:** Indicator LED or user warning

---

## 6. Design Considerations

### Power Transistor Selection

For induction cooker application:

| Parameter | Requirement | Example Device |
|-----------|-------------|----------------|
| Type | IGBT (preferred for 300V) or SiC MOSFET | IKW40N120H3 (IGBT) |
| Voltage rating | ≥1200V (4× DC bus for margin) | 1200V |
| Current rating | ≥40A continuous (depends on power) | 40A @ 100°C |
| Switching speed | fSW < 100kHz | tON/tOFF < 200ns |
| Gate charge | QG < 500nC (lower is better) | 240nC typical |
| Gate voltage | VGS(th) = 4-6V, VGS(max) = ±20V | ±20V |

**Trade-offs:**

**IGBT vs. SiC MOSFET:**

| Aspect | IGBT | SiC MOSFET |
|--------|------|------------|
| **Cost** | Lower ($2-5) | Higher ($10-30) |
| **Switching loss** | Moderate (tail current) | Lower (no tail) |
| **Conduction loss** | Lower (VCE(sat) ~1.7V) | Slightly higher (RDS(on)) |
| **Frequency** | Best <100kHz | Good up to 500kHz+ |
| **Ruggedness** | Robust | More susceptible to overvoltage |
| **Gate drive** | 15V (±15V split preferred) | 15-20V |

**For induction cooker (20-50 kHz):** **IGBT is typically preferred** (lower cost, good enough switching speed)

**For high-frequency (>100 kHz):** SiC MOSFET may offer better efficiency

### Bootstrap vs. Isolated Supply

Two options for high-side gate drive:

#### Option 1: Bootstrap Supply (Common)

**Advantages:**
- Simple, low cost
- Single VDD supply for both channels
- Minimal external components

**Disadvantages:**
- Duty cycle limited to <95% (needs refresh time)
- Not suitable for 100% duty cycle or DC applications
- CBOOT voltage drops during on-time

**Best for:** Induction cooker (AC waveform, typically 45-50% duty cycle)

#### Option 2: Isolated DC-DC Converter

**Advantages:**
- No duty cycle limitation (100% possible)
- Stable VDDA voltage regardless of switching
- Can be used for other isolated drivers

**Disadvantages:**
- Higher cost (isolated DC-DC module)
- More complex design
- Additional board space

**Best for:** Motor drives, PFC stages, or applications requiring >95% duty cycle

**Recommended isolated DC-DC modules:**
- RECOM RKZ-0505S (5V input, 5V isolated output, 1W)
- Murata MGJ3 series (3W isolated)
- Custom design using transformer + rectifier

### Gate Resistance Optimization

Gate drive resistors control switching speed vs. EMI trade-off:

**Turn-On Resistor (RON):**

| Value | Effect | Application |
|-------|--------|-------------|
| 0Ω | Fastest switching, max EMI | Lab testing only |
| 1-2.2Ω | Fast, moderate EMI | **Induction cooker typical** |
| 5-10Ω | Slower, reduced EMI | High EMI sensitivity |

**Turn-Off Resistor (ROFF):**

| Value | Effect | Application |
|-------|--------|-------------|
| 0Ω | **Fastest turn-off (recommended)** | Most applications |
| 0Ω + diode | Fast turn-off, controlled turn-on | Asymmetric control |

**Gate-to-Source Resistor (RGS):**

| Value | Effect | Application |
|-------|--------|-------------|
| Open | Gate floating (BAD - dV/dt induced turn-on) | Never use |
| 10kΩ | Good pull-down, minimal power loss | **Recommended** |
| 5.1kΩ | Stronger pull-down (high dV/dt environment) | High EMI |

**EMI Suppression:**

If ringing persists, add **ferrite bead** in series with gate:

```
OUTA ── RON ── Ferrite Bead ── IGBT Gate
           └── ROFF + Diode ──┘
```

**Ferrite bead selection:**
- Impedance @ 100 MHz: 50-300Ω
- DC resistance: <1Ω
- Current rating: >1A
- Example: Murata BLM18PG121SN1D

### PCB Parasitics

**Gate Drive Loop Inductance:**

Minimize the loop area:
```
VDD → OUTA → Gate → Source → VSS → VDD
```

**Target: <20nH loop inductance**

**Techniques:**
1. Place UCC21550 close to power transistors (<2cm)
2. Use wide traces for OUTA/OUTB (≥20 mil / 0.5mm)
3. Route OUTA/OUTB on same layer as VDD/VSS return
4. Use ground plane underneath driver circuit
5. Add local decoupling capacitor (100nF) near UCC21550

**Switch Node Parasitic Capacitance:**

The switch node (VSSA for high-side) has high dV/dt:

```
dV/dt = 300V / 50ns = 6 V/ns = 6000 V/µs
```

**Capacitive displacement current:**
```
I = C × dV/dt
```

For C=100pF:
```
I = 100pF × 6V/ns = 600mA
```

**Mitigation:**
- Minimize copper area on switch node
- Keep switch node traces short
- Avoid parallel routing of switch node near sensitive signals
- Use ground plane shielding

### Dead Time Tuning

Optimal dead time balances:
- **Too short:** Risk of shoot-through (catastrophic failure)
- **Too long:** Body diode conduction (increased loss, reduced efficiency)

**Iterative Process:**

1. **Start conservative:** DT = 1µs (very safe)
2. **Measure body diode conduction:**
   - Observe switch node voltage during dead time
   - If VSSA drops below GND (high-side body diode conducts): **DT too long**
   - If VSSB rises above VDC (low-side body diode conducts): **DT too long**
3. **Reduce dead time incrementally:** DT = 800ns, 600ns, 500ns, ...
4. **Monitor DC bus current:**
   - Sudden increase indicates shoot-through (STOP, increase DT)
5. **Final value:** Minimum DT without shoot-through + 30% margin

**Typical induction cooker:** DT = 500-1000ns

### Snubber Circuit

Snubber reduces voltage ringing on switch node:

```
         SW Node
            │
            ├── R_SNUB (10-47Ω) ── C_SNUB (1-10nF) ── GND
            │
       (Power Stage)
```

**Design procedure:**

1. **Measure ringing frequency** (oscilloscope):
   ```
   f_ring ≈ 1 / (2π√(L_parasitic × C_parasitic))
   ```
   Typical: 10-50 MHz

2. **Select C_SNUB:**
   ```
   C_SNUB ≈ 2 × C_parasitic
   ```
   Typical: 1-10nF (ceramic, C0G/NP0, 1kV)

3. **Select R_SNUB:**
   ```
   R_SNUB = √(L_parasitic / C_SNUB)
   ```
   Typical: 10-47Ω (metal film, 1-2W)

4. **Verify power dissipation:**
   ```
   P_SNUB ≈ 0.5 × C_SNUB × VDC² × fSW
   ```
   Must be less than R_SNUB power rating.

**Example:**
- VDC = 300V, fSW = 50kHz, C_SNUB = 4.7nF
- P_SNUB ≈ 0.5 × 4.7nF × (300V)² × 50kHz ≈ 21W

**This is too high!** Reduce C_SNUB or use active snubber.

**Practical induction cooker:** R_SNUB = 10-22Ω, C_SNUB = 1-4.7nF, P_SNUB < 5W

### Resonant Tank Design

The resonant LC tank determines induction cooker performance:

**Series Resonant Tank:**
```
SW ── C_RES ── L_COIL ── GND
```

**Resonant frequency:**
```
f0 = 1 / (2π√(L_COIL × C_RES))
```

**Typical values:**
- L_COIL = 50-150µH (includes leakage inductance with cookware)
- C_RES = 0.1-0.5µF (polypropylene film, 1200V)
- f0 = 20-50 kHz

**Design guidelines:**

1. **Switching frequency relative to resonance:**
   ```
   fSW ≈ 0.9 × f0  (slightly below resonance)
   ```
   This ensures inductive operation (ZVS possible).

2. **Quality factor:**
   ```
   Q = 2πf0 × L_COIL / R_COIL
   ```
   Target: Q = 5-20 (affects current magnification)

3. **Peak current estimation:**
   ```
   I_peak ≈ Q × (VDC / (2 × √(L_COIL / C_RES)))
   ```

4. **Power transfer:**
   Depends on coupling coefficient with cookware (typically 0.1-0.3).

**C_RES selection:**
- **Material:** Polypropylene film (low loss, high current)
- **Voltage rating:** ≥1.5× VDC (e.g., 630V for 300V DC bus, 1000V safer)
- **Current rating:** Must handle RMS current (typically 10-30A)
- **Example:** WIMA MKP4 series, 0.22µF, 1000V

---

## 7. Bill of Materials

### Core Components (Per Half-Bridge)

| Ref | Part Number | Description | Qty | Notes |
|-----|-------------|-------------|-----|-------|
| U1 | UCC21550ADWR | Isolated gate driver IC, SOIC-16 | 1 | Or UCC21550BDWR |
| Q1 | IKW40N120H3 | IGBT, 1200V, 40A, TO-247 | 1 | High-side switch |
| Q2 | IKW40N120H3 | IGBT, 1200V, 40A, TO-247 | 1 | Low-side switch |
| D1 | C4D10120E | SiC diode, 1200V, 10A, TO-220 | 1 | Bootstrap diode |
| D2, D3 | MSS1P4 | Schottky diode, 40V, 1A, SMA | 2 | Gate drive diodes |
| C1, C2 | 1µF, 50V, X7R | Ceramic cap, 0805 or 1206 | 2 | VDD bypass (VDDA, VDDB) |
| C3, C4 | 100nF, 50V, X7R | Ceramic cap, 0603 | 2 | VDD local bypass |
| C5 | 1µF, 50V, X7R | Ceramic cap, 0805 or 1206 | 1 | Bootstrap capacitor (CBOOT) |
| C6, C7 | 100nF, 50V, X7R | Ceramic cap, 0603 | 2 | VCCI bypass |
| R1, R2 | 2.2Ω, 0.5W | Thick film, 1206 | 2 | Gate drive turn-on resistors |
| R3 | 2.2Ω, 0.5W | Thick film, 1206 | 1 | Bootstrap current limit |
| R4, R5 | 10kΩ, 0.1W | Thick film, 0603 | 2 | Gate-source pull-down |
| R6, R7 | 51Ω, 0.1W | Thick film, 0603 | 2 | Input series resistors |
| C8, C9 | 33pF, 50V, C0G | Ceramic cap, 0603 | 2 | Input filter capacitors |

### Resonant Tank (Example)

| Ref | Part Number | Description | Qty | Notes |
|-----|-------------|-------------|-----|-------|
| C_RES | MKP4 series | Film capacitor, 0.22µF, 1000V | 1 | WIMA or equivalent |
| L_COIL | Custom | Litz wire coil, 100µH, 30A RMS | 1 | Cookware-dependent |

### Snubber (Optional)

| Ref | Part Number | Description | Qty | Notes |
|-----|-------------|-------------|-----|-------|
| R_SNUB | 22Ω, 2W | Metal film, axial | 1 | Or 10Ω depending on C_SNUB |
| C_SNUB | 4.7nF, 1kV, C0G | Ceramic cap, 1206 or 1210 | 1 | High voltage rating |

### Cost Estimate (USD, 1000 pcs)

| Component | Unit Cost | Total |
|-----------|-----------|-------|
| UCC21550ADWR | $2.50 | $2.50 |
| IGBTs (2×) | $3.00 | $6.00 |
| Bootstrap diode | $1.50 | $1.50 |
| Passive components | - | $2.00 |
| **Subtotal per half-bridge** | | **$12.00** |

Additional costs:
- PCB (4-layer, FR-4): ~$5.00
- Heatsink + isolation pad: ~$3.00
- Resonant capacitor: ~$2.00
- Induction coil: ~$5.00

**Total gate driver + power stage BOM: ~$27/channel**

---

## 8. PCB Layout Guidelines

### Critical Layout Rules

#### Rule 1: Isolation Barrier

**8mm minimum creepage/clearance:**

```
  Primary Side          |         Secondary Side
                        |
  [VCCI] [GND]          |  [VDDA] [VSSA] [OUTA]
     ●     ●            |     ●     ●      ●
                        |
        <── 8mm min ──> |
                        |
    ─────────────       |       ─────────────
     No copper          |         No copper
     underneath         |       underneath
    ─────────────       |       ─────────────
                        |
                     PCB cutout
                    (recommended,
                      not required)
```

**Slot/cutout guidelines:**
- Width: ≥3mm (if used)
- Extends beyond IC body by ≥2mm each side
- Not strictly required, but improves isolation margin

#### Rule 2: High-Current Loops

**Minimize gate drive loop:**

```
      VDD
       │
       ├──── [UCC21550]
       │          │
     [COUT]    OUTA/OUTB
       │          │
       ├────── [R_G] ──── IGBT Gate
       │          │
      VSS ───── IGBT Source/Emitter
       │
      ─┴─
```

**Techniques:**
- Keep UCC21550 within 2cm of IGBTs
- Use 0.5mm (20 mil) minimum width for OUTA/OUTB traces
- Place decoupling capacitors (100nF) within 5mm of VDD/VSS pins
- Use ground plane on layer 2 (or adjacent layer) underneath driver

#### Rule 3: Power Stage Layout

**Minimize DC bus loop (critical for EMI):**

```
        VDC+
         │
       [CDC]  <── Large bulk capacitor
         │         (close to IGBTs)
         ├──── Q_HS (High-side IGBT)
         │       │
         │      SW (Switch node)
         │       │
         └──── Q_LS (Low-side IGBT)
                │
               GND
```

**DC bus loop area:** <5 cm² target

**Techniques:**
- Use wide power traces (≥3mm / 118 mil)
- Place CDC (DC bus capacitor) close to IGBTs (<3cm)
- Use internal power plane layers if possible
- Add multiple vias for high-current connections (>5 vias per connection)

#### Rule 4: Switch Node Routing

**Switch node (SW) has high dV/dt:**

✗ **AVOID:**
- Long traces (inductance causes ringing)
- Parallel routing near sensitive signals (capacitive coupling)
- Large copper areas (unnecessary parasitic capacitance)

✓ **BEST PRACTICE:**
- Keep SW trace as short as possible
- Use minimal width needed for current (1-2mm)
- Route away from input signals (INA, INB, DIS)
- Add local ground plane shielding between SW and sensitive traces

#### Rule 5: Thermal Management

**Connect thermal pads to copper pour:**

For DW/DWK packages, expose pins have thermal relief:

```
        ┌───────────────┐
        │   UCC21550    │
        │               │
        │  VSS pins     │
        └───┬───┬───┬───┘
            │   │   │
        ════╧═══╧═══╧════  <── Copper plane
           (multiple vias
           to inner layer)
```

**Guidelines:**
- Connect VSS pins (14, 9) to ground plane with ≥5 vias each
- Use thermal relief for VDD pins (16, 11) if on power plane
- Add copper pour around IC for heat dissipation

### 4-Layer PCB Stackup (Recommended)

```
Layer 1 (Top):        Signal traces, component placement
                      [VCCI/GND region] | [VDD/VSS regions]

Layer 2 (Inner):      Ground plane (solid pour)
                      [Split at isolation barrier]

Layer 3 (Inner):      Power plane (VDD distribution)
                      [Split at isolation barrier]

Layer 4 (Bottom):     Signal traces, return paths
```

**Split planes at isolation barrier** to maintain creepage.

### 2-Layer PCB Layout (Cost-Optimized)

```
Layer 1 (Top):        Components, signals, power traces
                      Ground plane pour (split at barrier)

Layer 2 (Bottom):     Ground plane + return paths
                      (split at isolation barrier)
```

**Notes for 2-layer:**
- Requires more careful routing (limited space)
- Use wider traces to compensate for higher DC resistance
- Place decoupling caps on bottom side if top is crowded

### Example Layout

```
                      Primary Side  |  Secondary Side
                                    |
     ┌────────────┐                 |
     │ MCU / DSP  │                 |
     └─┬────┬─────┘                 |
       │INA │INB                    |
       │    │                       |
       ▼    ▼                       |
      [R][C][R][C] Input filters    |
              │   │                 |
              │   │    [C]          |  [CBOOT]
       ┌──────┴───┴─────┴───────┐  |   [DBOOT]──────┐
       │                         │  |       │        │
       │   VCC  INA  INB  GND    │  |   [VDD]    [COUT]
       │    │    │    │    │     │  |     │         │
       │  ┌─────────────────┐    │  |  ┌──┴─────────┴──┐
       │  │   UCC21550      │    │  |  │                │
       │  │                 │════╪══╪══│  (Isolation)   │
       │  └─────────────────┘    │  |  │                │
       │    │         │      │   │  |  └──┬─────────┬──┘
       │  VSSA      OUTA   VDDA  │  |     │         │
       └────┬─────────┬──────┬───┘  |  [VSSA]    [VDDA]
            │         │      │      |     │         │
            │         │      │      |     │         │
         ═══╧═════════╧══════╧═══   |     │         │
         Ground plane (split)       |     │         │
                                    |     │         │
                                    |  ┌──┴─────────┴──┐
                                    |  │   Q_HS (IGBT)  │
                                    |  │    High-side   │
                                    |  └──┬─────────────┘
                                    |     │ SW node
                                    |  ┌──┴─────────────┐
                                    |  │   Q_LS (IGBT)  │
                                    |  │    Low-side    │
                                    |  └──┬─────────────┘
                                    |     │
                                    |    GND
```

### Design Rule Check (DRC) Settings

**Minimum trace widths:**
- Signal traces: 0.15mm (6 mil)
- Power traces (VCCI, VDD): 0.4mm (16 mil)
- High-current (IGBT connections): 3mm (118 mil) or use planes

**Minimum clearances:**
- Signal-to-signal: 0.15mm (6 mil)
- Signal-to-plane: 0.2mm (8 mil)
- High-voltage (>100V): 0.5mm (20 mil)
- Isolation barrier: **8mm (315 mil)** <-- Critical!

**Via specifications:**
- Finished hole size: 0.3mm (12 mil) minimum
- Pad diameter: 0.6mm (24 mil) minimum
- High-current vias: Use multiple in parallel (5-10 vias)

---

## 9. Troubleshooting

### Common Issues and Solutions

#### Issue 1: Output Not Switching

**Symptoms:**
- OUTA/OUTB remain low regardless of input

**Possible causes:**

1. **UVLO active:**
   - Check VCCI: Must be >2.7V
   - Check VDDA/VDDB: Must be >6.0V (A variant), >8.5V (B), or >12.5V (C)
   - Measure with oscilloscope (not just multimeter - ripple may drop below UVLO)

2. **DIS pin asserted:**
   - Check DIS voltage: Must be <1.0V for normal operation
   - If floating, internal pull-up holds DIS HIGH (disabled)
   - **Solution:** Connect DIS to GND through 10kΩ if not used

3. **Input signals missing:**
   - Verify INA/INB receive proper PWM (0-3.3V or 0-5V)
   - Check with oscilloscope (noise may appear as "logic level" to multimeter)
   - Ensure input pulse width >12ns (typical minimum)

4. **Power supply issue:**
   - Verify VCCI current draw: Should be 1-5mA
   - Verify VDD current draw: Should be 1-5mA quiescent
   - If current is 0mA, check for solder bridges, shorts

**Debug procedure:**
1. Measure VCCI-GND: Should be 3.0-5.5V DC
2. Measure VDDA-VSSA and VDDB-VSSB: Should match selected variant UVLO
3. Measure DIS-GND: Should be <0.5V
4. Probe INA/INB with scope: Verify PWM signal present
5. Probe OUTA/OUTB with scope: Check for output activity

#### Issue 2: Bootstrap Supply Not Working (High-Side)

**Symptoms:**
- OUTB (low-side) switches normally
- OUTA (high-side) does not switch or switches briefly then stops

**Root cause:** VDDA-VSSA voltage drops below UVLO during high-side on-time

**Possible causes:**

1. **Insufficient bootstrap capacitor:**
   - CBOOT too small (minimum 1µF recommended)
   - **Solution:** Increase to 1-2µF ceramic, X7R, 50V

2. **Bootstrap diode failure:**
   - Check DBOOT for short/open
   - Measure forward voltage: Should be 0.4-0.8V when conducting
   - **Solution:** Replace with SiC Schottky (e.g., C4D10120E)

3. **Duty cycle too high:**
   - Bootstrap needs refresh time when low-side ON
   - If duty cycle >95%, insufficient time to recharge CBOOT
   - **Solution:** Limit duty cycle to <90% or use isolated supply

4. **Excessive gate drive frequency:**
   - High frequency → more charge drawn from CBOOT
   - **Solution:** Reduce switching frequency or increase CBOOT

5. **Bootstrap resistor too large:**
   - Limits charging current to CBOOT
   - **Solution:** Use 2.2Ω or lower (1Ω typical)

**Debug procedure:**
1. Measure VDDA-VSSA with scope during operation:
   - Should be ~15V when LS on (charging phase)
   - Should drop slightly when HS on (discharging)
   - If drops below 6V, UVLO triggers (bad)
2. Check ripple on VDDA: <0.5V acceptable, >2V indicates problem
3. Measure current through DBOOT: Should pulse when LS turns on
4. Verify low-side transistor is actually turning on (bootstrap won't charge if not)

#### Issue 3: Excessive Ringing on Gate Drive

**Symptoms:**
- Gate voltage oscillates at turn-on/turn-off
- Overshoot/undershoot >20% of VDD
- High-frequency noise on gate waveform (10-100 MHz)

**Causes:**
- Parasitic inductance in gate drive loop
- Resonance between loop inductance and gate capacitance

**Solutions:**

1. **Reduce gate drive loop inductance:**
   - Place UCC21550 closer to IGBT (<2cm target)
   - Use wider PCB traces for OUTA/OUTB (≥0.5mm)
   - Add local ground plane under driver circuit

2. **Add gate series resistor:**
   - Increase RON from 2.2Ω to 5-10Ω
   - Trade-off: Slower switching, lower EMI

3. **Add ferrite bead in gate path:**
   - Place between OUTA and IGBT gate
   - Select: 50-300Ω @ 100MHz, <1Ω DC resistance
   - Example: Murata BLM18PG121SN1D

4. **Add gate-to-source RC snubber:**
   ```
   IGBT Gate ── 10Ω ── 100pF ── IGBT Source
   ```

**Debug procedure:**
1. Measure gate voltage with oscilloscope (use short ground lead <2cm!)
2. Identify ringing frequency: Typically 10-50 MHz
3. Add damping resistor incrementally: 1Ω, 2.2Ω, 5Ω, 10Ω
4. Verify ringing reduced to acceptable level (<10% overshoot)

#### Issue 4: Shoot-Through / Overcurrent

**Symptoms:**
- DC bus current spikes immediately when switching starts
- Transistors fail (shorted or open)
- Loud "pop" sound or visible flash
- Blown fuse on DC bus supply

**Cause:** Both transistors conducting simultaneously (shoot-through)

**Root causes:**

1. **Insufficient dead time:**
   - Dead time < turn-off delay + safety margin
   - **Solution:** Increase dead time (DT pin programming or input signals)

2. **Propagation delay mismatch:**
   - If INA and INB have different delays
   - **Solution:** Match input trace lengths, use same drive strength

3. **Gate drive false turn-on:**
   - dV/dt on switch node induces current through CGD (Miller capacitance)
   - **Solution:** Add negative gate voltage (-5V to -8V) during off-state

4. **Transistor not fully off before other turns on:**
   - Slow turn-off due to high gate resistance
   - **Solution:** Use anti-parallel diode for fast turn-off path

**Prevention (CRITICAL):**

1. **Program adequate dead time:**
   ```
   DT > t_fall(Q1) + t_delay + 2×(t_rise(Q2) + t_delay) + margin
   DT > 500ns minimum for typical IGBTs
   ```

2. **Monitor DC bus current:**
   - Add shunt resistor (0.01Ω, 5W) in series with DC bus
   - Implement hardware overcurrent protection (<1µs response)

3. **Add interlocking dead time:**
   - Use DT pin: Connect 10-20kΩ resistor from DT to GND
   - Hardware ensures outputs never overlap

4. **Test with current limiting:**
   - During initial testing, limit DC bus current to 1A with power supply
   - Gradually increase as you verify correct operation

**Debug procedure (SAFE METHOD):**
1. **DO NOT POWER UP if shoot-through suspected!**
2. Remove DC bus voltage (use VDC = 0V initially)
3. Apply only gate drive supplies (VCCI, VDD)
4. Verify with scope:
   - GATE_HS and GATE_LS never overlap
   - Dead time present and sufficient
5. Apply low DC voltage (VDC = 50V) with current limit (0.5A)
6. Monitor DC bus current: Should be <100mA average
7. Gradually increase voltage and monitor

#### Issue 5: High-Frequency Noise on Inputs

**Symptoms:**
- Inputs (INA/INB) show noise/glitches on scope
- Unpredictable switching behavior
- EMI-related false triggering

**Causes:**
- Capacitive coupling from switch node (high dV/dt)
- Ground bounce from IGBT switching (high di/dt)
- Power supply noise

**Solutions:**

1. **Add/increase input RC filter:**
   ```
   Current: R=51Ω, C=33pF
   Increase to: R=100Ω, C=100pF
   ```

2. **Route input traces away from SW node:**
   - Maintain >1cm separation
   - Use ground plane shielding between

3. **Add ferrite bead on input traces:**
   - Close to UCC21550 input pins
   - Example: Murata BLM15AG102SN1

4. **Improve VCCI decoupling:**
   - Add 10µF tantalum in parallel with 100nF ceramic
   - Place within 5mm of VCCI pin

5. **Use twisted pair or shielded cable:**
   - If INA/INB come from external connector
   - Connect shield to GND at UCC21550 end only

#### Issue 6: IC Gets Hot / Thermal Shutdown

**Symptoms:**
- UCC21550 package temperature >100°C (too hot to touch)
- Intermittent operation (thermal cycling)
- Eventual device failure

**Causes:**
- Excessive power dissipation
- Inadequate thermal management

**Power dissipation sources:**

1. **Gate drive loss (dominant):**
   ```
   P_GATE = 2 × VDD × QG × fSW

   Example: VDD=15V, QG=200nC, fSW=50kHz
   P_GATE = 2 × 15V × 200nC × 50kHz = 300mW
   ```

2. **Quiescent loss:**
   ```
   P_Q = VCCI × IVCCI + VDDA × IDDA + VDDB × IDDB

   Typical: P_Q ≈ 100-200mW
   ```

3. **Total loss:**
   ```
   P_TOTAL = P_GATE + P_Q
   Example: P_TOTAL = 300mW + 150mW = 450mW
   ```

**Thermal calculation:**

```
TJ = TA + (θJA × P_TOTAL)

Where:
- TA = Ambient temperature (e.g., 50°C near induction coil)
- θJA = Junction-to-ambient thermal resistance
  - DW package: 69.8°C/W
  - DWK package: 74.1°C/W
- P_TOTAL = Total power dissipation (W)

Example:
TJ = 50°C + (69.8°C/W × 0.450W) = 50°C + 31.4°C = 81.4°C
```

**Maximum TJ = 150°C**, so this example has margin.

**If TJ > 120°C, take action:**

**Solutions:**

1. **Reduce switching frequency:**
   - Lower fSW reduces gate drive loss linearly
   - Example: 50kHz → 25kHz halves P_GATE

2. **Reduce gate drive voltage:**
   - Lower VDD if IGBT allows (check VGE(th) margin)
   - Example: 15V → 12V reduces P_GATE by 20%

3. **Select transistor with lower QG:**
   - Example: 200nC → 100nC halves P_GATE
   - Trade-off: Higher RDS(on) or slower switching

4. **Improve PCB thermal design:**
   - Add copper pour connected to VSS pins (9, 14)
   - Use thermal vias to inner/bottom layers (5-10 vias per pin)
   - Increase copper thickness (2oz vs. 1oz)

5. **Add airflow:**
   - Small fan near driver circuit
   - Even 0.5 m/s airflow significantly reduces θJA

6. **Use DWK package instead of DW:**
   - Wait, DWK actually has worse θJA (74.1 vs 69.8)
   - This is not a solution!

7. **Consider using two UCC21550 in parallel:**
   - Each drives one transistor (not half-bridge)
   - Distributes power dissipation across two ICs

---

## 10. Additional Resources

### Texas Instruments Resources

1. **UCC21550 Product Page:**
   - https://www.ti.com/product/UCC21550
   - Latest datasheet revisions, application notes, design tools

2. **Application Notes:**
   - SLUSEC9: "Isolated Gate Drivers for SiC MOSFETs"
   - SLUA874: "Bootstrap Design for Gate Driver ICs"
   - SLUA618: "Gate Drive Optimization for SiC MOSFETs"

3. **Reference Designs:**
   - TIDA-010053: "3.5kW Bidirectional On-Board Charger"
   - TIDA-010062: "High-Voltage DC-DC Converter"

4. **Design Tools:**
   - WEBENCH Power Designer: Online simulation and BOM generation
   - PSPICE for TI: Free circuit simulation tool

### Technical Papers and Standards

1. **Gate Driver Design:**
   - "Optimizing Gate Driver Design for SiC MOSFETs" - TI Analog Applications Journal
   - "EMI Considerations for Gate Drivers" - IEEE APEC

2. **Induction Heating:**
   - "Design of Induction Cooker with Maximum Power Transfer" - IEEE Trans. on Industrial Electronics
   - "Resonant Inverter Topologies for Induction Heating" - IEEE Power Electronics

3. **Safety Standards:**
   - IEC 60335-2-6: "Safety of Household Appliances - Cooking Appliances"
   - IEC 60664-1: "Insulation Coordination for Equipment Within Low-Voltage Systems"
   - UL 1577: "Standard for Isolated Components"

### Component Suppliers

| Component | Suppliers | Part Numbers |
|-----------|-----------|--------------|
| **UCC21550** | Digi-Key, Mouser, Arrow | UCC21550ADWR, UCC21550BDWR |
| **IGBTs** | Infineon, Fairchild, Toshiba | IKW40N120H3, FGA40N120FD, GT40W120 |
| **Bootstrap Diode** | Wolfspeed (Cree), Infineon | C4D10120E, IDH10G120C5 |
| **Film Capacitors** | WIMA, KEMET, Vishay | MKP4 series, C4AE series, PHE450 |

### Online Communities

1. **TI E2E Forums:**
   - https://e2e.ti.com/
   - Active community for TI product support
   - Search "UCC21550" for existing discussions

2. **EEVBlog Forum:**
   - https://www.eevblog.com/forum/
   - Power electronics section for general discussion

3. **Power Electronics Society:**
   - https://www.pels.org/
   - Technical conferences, publications, webinars

### Simulation Resources

1. **ngspice:**
   - http://ngspice.sourceforge.net/
   - Open-source SPICE simulator
   - User manual: http://ngspice.sourceforge.net/docs/ngspice-html-manual/manual.xhtml

2. **KiCad:**
   - https://www.kicad.org/
   - Open-source PCB design and simulation
   - SPICE integration tutorial: https://docs.kicad.org/6.0/en/eeschema/eeschema.html#spice-simulation

3. **LTspice:**
   - https://www.analog.com/en/design-center/design-tools-and-calculators/ltspice-simulator.html
   - Free SPICE simulator from Analog Devices
   - Can import subcircuits with modification

### Recommended Books

1. **"Power Electronics: Converters, Applications, and Design" by Mohan, Undeland, Robbins**
   - Comprehensive power electronics textbook
   - Chapters on gate drivers, resonant converters

2. **"Fundamentals of Power Electronics" by Erickson and Maksimović**
   - Advanced treatment of converter design
   - Chapter 19: Resonant Conversion

3. **"Designing Control Loops for Linear and Switching Power Supplies" by Christophe Basso**
   - Practical design techniques
   - Includes resonant converter control

### Test Equipment Recommendations

| Equipment | Specification | Example Model |
|-----------|---------------|---------------|
| **Oscilloscope** | ≥200 MHz, 4 ch, isolated inputs | Tektronix TBS2074, Rigol DS1054Z |
| **Differential Probe** | 100 MHz, 1000V rated | Tektronix TDP1000 |
| **Current Probe** | 30A, 20 MHz | Tektronix TCP0030A |
| **Function Generator** | 50 MHz, 2 ch, arb waveform | Siglent SDG2042X |
| **Power Supply** | 0-50V, 5A, programmable | Rigol DP832 |
| **Multimeter** | 6.5 digit, true RMS | Keysight 34461A |
| **Isolation Tester** | 5kV AC, 10 GΩ | Megger MIT515 |

---

## Conclusion

The **UCC21550 isolated gate driver** is a robust, feature-rich solution for driving power transistors in induction cooker applications. Key takeaways:

✓ **Reinforced isolation** (5kVRMS) ensures safety and noise immunity
✓ **High drive current** (4A/6A) enables fast switching of IGBTs and MOSFETs
✓ **Programmable dead time** and disable function add flexibility and protection
✓ **TTL/CMOS inputs** simplify interfacing with 3.3V/5V microcontrollers
✓ **Wide temperature range** (-40 to +150°C) suits demanding environments

**Critical Success Factors:**

1. **Maintain isolation barrier integrity:** 8mm minimum creepage/clearance
2. **Program adequate dead time:** >500ns for typical IGBTs to prevent shoot-through
3. **Design robust bootstrap supply:** 1-2µF capacitor, quality SiC diode, <90% duty cycle
4. **Optimize PCB layout:** Minimize gate drive loop, separate noisy from quiet traces
5. **Monitor thermal performance:** Calculate power dissipation, ensure TJ < 120°C
6. **Implement protection:** Overcurrent detection, thermal monitoring, disable functionality

**Simulation validates basic functionality, but hardware testing is essential** to verify real-world performance, EMI compliance, and safety.

**Design responsibly:** Induction cookers operate at lethal voltages. Follow safety standards, use proper isolation techniques, and thoroughly test before deployment.

---

**Document Version:** 1.0
**Last Updated:** 2024
**Author:** Design Engineer
**For questions or clarifications, contact:** [Your contact information]

---

## Appendix: Quick Reference

### Pin Assignments (16-pin DW)

| Pin | Name | Pin | Name |
|-----|------|-----|------|
| 1 | INA | 9 | VSSB |
| 2 | INB | 10 | OUTB |
| 3 | VCCI | 11 | VDDB |
| 4 | GND | 12 | NC |
| 5 | DIS | 13 | NC |
| 6 | DT | 14 | VSSA |
| 7 | NC | 15 | OUTA |
| 8 | VCCI | 16 | VDDA |

### Typical Operating Values

| Parameter | Value |
|-----------|-------|
| VCCI | 5.0V |
| VDD | 15V (for IGBT gate drive) |
| Input signal | 3.3V logic (0-3.3V) |
| Gate resistor (RON) | 2.2Ω |
| Gate resistor (ROFF) | 0Ω (with anti-parallel diode) |
| Gate-source resistor (RGS) | 10kΩ |
| Bootstrap capacitor | 1µF, 50V, X7R |
| Dead time | 500-1000ns |
| Switching frequency | 20-50 kHz |

### Formula Quick Reference

| Parameter | Formula |
|-----------|---------|
| Dead time programming | DT (ns) = 8.6 × RDT (kΩ) + 13 |
| Gate drive power loss | P_GATE = 2 × VDD × QG × fSW |
| Junction temperature | TJ = TA + (θJA × P_TOTAL) |
| Resonant frequency | f0 = 1 / (2π√(L × C)) |
| Bootstrap cap min | CBOOT > (QG + IVDD/fSW) / (0.5V) |

### Safety Checklist

- [ ] Isolation barrier maintained (8mm minimum)
- [ ] Dead time programmed correctly (>500ns)
- [ ] Shoot-through protection tested
- [ ] Bootstrap supply validated (VDDA monitored)
- [ ] Overcurrent protection implemented
- [ ] Thermal design verified (TJ < 120°C worst-case)
- [ ] PCB layout reviewed (creepage, clearance, loop inductance)
- [ ] Input signals filtered (RC network)
- [ ] Gate-source resistors installed (10kΩ)
- [ ] Initial testing with current-limited supply
- [ ] EMI compliance tested (FCC/CISPR standards)

---

**END OF DOCUMENT**
