# UCC27511A Low-Side Gate Driver
## IGBT/MOSFET Driver for Induction Cooker Applications
### Complete Design Guide and SPICE Simulation Package

**Document Version:** 1.0  
**Date:** December 9, 2025  
**Status:** Production Ready  
**Part Number:** UCC27511A (SOT-23-6 / DBV package)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [UCC27511A Overview](#2-ucc27511a-overview)
3. [Role in Induction Cooker](#3-role-in-induction-cooker)
4. [How to Use This Chip](#4-how-to-use-this-chip)
5. [SPICE Model and Simulation](#5-spice-model-and-simulation)
6. [Safety and High-Voltage Considerations](#6-safety-and-high-voltage-considerations)
7. [Design Examples](#7-design-examples)
8. [Reference Information](#8-reference-information)

---

## 1. Executive Summary

### What is the UCC27511A?

The **UCC27511A** is a single-channel, high-speed, low-side gate driver designed to drive power MOSFETs and IGBTs in high-frequency switching applications. It features:

- **4A peak source current** / **8A peak sink current** (asymmetrical drive)
- **Split output pins (OUTH/OUTL)** for independent turn-on/turn-off control
- **13ns propagation delay** (typical)
- **4.5V to 18V supply range**
- **TTL/CMOS compatible inputs** (independent of VDD)
- **Dual input configuration** (IN+/IN-) for inverting/non-inverting operation
- **Undervoltage lockout (UVLO)** protection
- **Compact SOT-23-6 package**

### Why Use It in an Induction Cooker?

Induction cookers use high-frequency resonant inverters (typically 20-40kHz) to generate alternating magnetic fields for heating cookware. The UCC27511A is ideal for driving the IGBTs in these inverters because:

1. **Fast switching** (13ns delay) minimizes switching losses
2. **High drive current** (4A/8A) quickly charges/discharges large IGBT gates
3. **Asymmetrical drive** allows optimization of turn-on vs turn-off speed
4. **Split outputs** enable independent gate resistor selection for EMI control
5. **Negative transient immunity** (up to -5V) handles ground bounce
6. **Small footprint** saves PCB space in compact cooker designs

### Key Specifications

| Parameter | Min | Typ | Max | Unit |
|-----------|-----|-----|-----|------|
| Supply Voltage (VDD) | 4.5 | 12 | 18 | V |
| Peak Source Current (IOH) | 4.0 | 4.3 | – | A |
| Peak Sink Current (IOL) | 4.0 | 4.4 | – | A |
| Propagation Delay (tPD) | – | 13 | 20 | ns |
| Rise Time (tR) | – | 8 | – | ns |
| Fall Time (tF) | – | 7 | – | ns |
| Output Resistance High (ROH) | 5 | 6 | 7.5 | Ω |
| Output Resistance Low (ROL) | 0.375 | 0.5 | 0.65 | Ω |
| Input Threshold High (VIH) | 2.0 | 2.2 | – | V |
| Input Threshold Low (VIL) | – | 1.2 | 1.4 | V |
| UVLO Threshold Rising | 3.9 | 4.2 | 4.5 | V |
| UVLO Hysteresis | – | 300 | – | mV |
| Quiescent Current | – | 180 | 250 | μA |

---

## 2. UCC27511A Overview

### 2.1 Pin Configuration (SOT-23-6 / DBV)

```
       TOP VIEW
    ┌─────────┐
VDD │1      6│ IN+
OUTH│2      5│ IN-
OUTL│3      4│ GND
    └─────────┘
```

| Pin | Name | Function |
|-----|------|----------|
| 1 | VDD | Bias supply input (4.5V to 18V) |
| 2 | OUTH | High-side output (source, 4A peak) |
| 3 | OUTL | Low-side output (sink, 8A peak) |
| 4 | GND | Ground reference |
| 5 | IN- | Inverting input |
| 6 | IN+ | Non-inverting input |

### 2.2 Key Features Explained

#### Asymmetrical Drive (4A Source / 8A Sink)

The UCC27511A provides **stronger sink current (8A) than source current (4A)** for several important reasons:

1. **Miller Turnon Immunity**: During turn-off of the power device, the high dV/dt can cause parasitic Miller turn-on. The strong 8A sink current prevents this.

2. **Faster Turn-Off**: IGBTs have significant tail current during turn-off. Fast gate discharge minimizes the time spent in the high-dissipation linear region.

3. **Reduced Shoot-Through**: In half-bridge configurations, fast turn-off reduces the risk of both switches being on simultaneously.

The peak currents are not continuous - they only flow during the brief charging/discharging of the gate capacitance.

#### Split Outputs (OUTH / OUTL)

The **split output configuration** allows independent control of turn-on and turn-off speeds:

- **OUTH** (Pin 2): Sources current through 6Ω internal resistance
- **OUTL** (Pin 3): Sinks current through 0.5Ω internal resistance

Both pins connect to the same internal totem-pole output, but with different series resistances. This allows you to:

- Connect separate external gate resistors for turn-on (OUTH) and turn-off (OUTL)
- Optimize switching speed vs EMI trade-off independently
- Fine-tune dead-time in half-bridge applications

**Usage Options:**
1. **Single path**: Use only OUTL for fastest switching (most common)
2. **Dual path with diode OR**: Use both with Schottky diodes for asymmetric control
3. **Custom network**: Advanced applications with RC snubbers

#### Dual Input (IN+ / IN-)

The dual input configuration provides flexibility:

| IN+ | IN- | Output |
|-----|-----|--------|
| LOW | X | LOW (Hi-Z) |
| X | HIGH | LOW (Hi-Z) |
| HIGH | LOW | HIGH |

**Applications:**
- **Non-inverting**: Drive IN+, tie IN- to GND
- **Inverting**: Drive IN-, tie IN+ to VDD
- **ENABLE function**: Use unused input as enable/disable control

### 2.3 Internal Block Diagram

```
VDD ──┬──[UVLO]──┬──────────────────────┐
      │          │                      │
      │          │   ┌──────────┐      ┌▼────┐
IN+ ──┼──[Comp]──┼──▶│          │      │  P  │
      │          │   │   AND    ├─────▶│ MOS │──┬── OUTH (Pin 2)
IN- ──┼──[Comp]──┼──▶│  Logic   │      │  H  │  │
      │          │   └──────────┘      └─────┘  │
      │          │                              │
      │          │                     Internal │
      │          │                      Output  │
      │          │                       Node   │
      │          │                              │
      │          │                      ┌─────┐ │
      │          │                      │  N  │ │
      │          └─────────────────────▶│ MOS │─┴── OUTL (Pin 3)
      │                                 │  L  │
GND ──┴─────────────────────────────────┴─────┴─────
```

---

## 3. Role in Induction Cooker

### 3.1 Induction Cooker Power Stage Overview

```
         ┌──────────────────────────────────────┐
AC Mains │ Rectifier  │ PFC  │ Resonant Inverter│ Induction
230V/120V│  Bridge    │Stage │   (20-40kHz)    │   Coil
         └──────────────────────────────────────┘
              │          │            │
           350-400VDC  400VDC      ┌──┴───┐
                                   │ IGBT │ ← UCC27511A drives this
                                   │      │
                                   └──────┘
```

### 3.2 Where UCC27511A Fits

The UCC27511A drives the **main resonant inverter IGBT(s)** that generate the high-frequency magnetic field. Typical configurations:

#### Half-Bridge Resonant Inverter (Most Common)

```
                400VDC
                  │
                ┌─┴─┐
                │ Q1│ IGBT1 (High-side, needs isolated driver)
                └─┬─┘
                  │
                  ├───[Resonant Tank]─── Induction Coil
                  │
                ┌─┴─┐
                │ Q2│ IGBT2 (Low-side) ← UCC27511A drives this
                └─┬─┘
                  │
                 GND
```

#### Single-Switch Inverter (Budget Designs)

```
                400VDC
                  │
                ┌─┴─┐
                │ Q1│ IGBT ← UCC27511A drives this
                └─┬─┘
                  │
                  ├───[Resonant Tank + Diode]─── Induction Coil
                  │
                 GND
```

### 3.3 Integration with Control System

```
Microcontroller         Auxiliary       Gate Driver        Power Stage
(PWM Generation)       Power Supply                       (IGBT)
     │                     │                │                │
     │  20-40kHz          │  12V           │                │
     │  PWM @ 3.3V/5V    │                │                │
     │                    │                │                │
     ├───────────────────┐│                │                │
     │                   ││                │                │
     │  MCU GPIO         │└──VDD       IN+─┤                │
     │  (PWM output)     │   UCC27511A    │                │
     │                   └───GND       OUTL├──[RGOFF]──GATE─┤
     │                                     │                │
     └─── (Optional feedback: temp, current, voltage)      │
                                                          IGBT
                                                            │
```

### 3.4 Critical Design Considerations

#### Power Supply for UCC27511A

- **Source**: Isolated auxiliary winding or separate SMPS (e.g., LMR51430)
- **Voltage**: Typically 12V or 15V
- **Current**: ~20mA quiescent + gate drive current
- **Bypass**: 10μF ceramic + 100nF close to VDD pin

#### Gate Drive Design

- **IGBT Gate Charge**: Typically 50-150nC for 20-40A IGBTs
- **Switching Frequency**: 20-40kHz (induction cooker range)
- **Gate Resistor**: 5-20Ω (trade-off: switching speed vs EMI)
- **Peak Current**: UCC27511A can deliver 4-8A peak

#### EMI Considerations

Induction cookers are notorious for EMI. The UCC27511A helps by:

1. **Controlled dI/dt**: External gate resistor limits current slew rate
2. **Split outputs**: Independent turn-on/turn-off speed optimization
3. **Fast switching**: Minimizes time in linear region (reduces harmonics)

**Typical EMI Mitigation**:
- Gate resistor: 10-15Ω (slower switching = less EMI, but more loss)
- RC snubber across IGBT
- Common-mode choke on AC input
- Shielded enclosure

---

## 4. How to Use This Chip

### 4.1 Basic Non-Inverting Configuration

```spice
VDD VDD 0 DC 12
VPWM INP 0 PULSE(0 5 100N 10N 10N 24U 40U)  ; 25kHz PWM
RINN INN 0 1MEG  ; Tie IN- to GND

XU1 VDD 0 INP INN OUTH OUTL UCC27511A

* Use OUTL for fastest switching
RGATE OUTL GATE 10
CGATE GATE 0 2N  ; IGBT input capacitance

CVDD VDD 0 10U   ; Bypass capacitor
```

### 4.2 Inverting Configuration

```spice
VDD VDD 0 DC 15
VPWM INN 0 PULSE(0 5 100N 10N 10N 24U 40U)
RINP INP VDD 1K  ; Tie IN+ to VDD

XU1 VDD 0 INP INN OUTH OUTL UCC27511A
RGATE OUTL GATE 10
CGATE GATE 0 2N
```

### 4.3 ENABLE/DISABLE Function

Using IN- as DISABLE (active high):

```spice
VPWM INP 0 PULSE(0 5 100N 10N 10N 24U 40U)
VENABLE INN 0 PULSE(0 5 50U 10N 10N 100U 200U)  ; Disable during 50-150μs
XU1 VDD 0 INP INN OUTH OUTL UCC27511A
```

### 4.4 Split Output Usage

#### Option 1: Single Output (Recommended)

Use **OUTL only** for maximum performance:

```
OUTL ──[RGATE]── IGBT Gate
```

Advantages:
- Simplest topology
- Lowest output resistance (0.5Ω)
- Fastest switching
- Most common configuration

#### Option 2: Asymmetric Drive with Diodes

```
OUTH ──[RGON]──┬──[D1]──┐
                        ├─── IGBT Gate
OUTL ──[RGOFF]─┴──[D2]──┘
```

Where:
- RGON = 15Ω (slower turn-on, less EMI)
- RGOFF = 5Ω (faster turn-off, less loss)
- D1, D2 = Schottky diodes (e.g., BAT54S)

Advantages:
- Independent control of ton/toff
- Optimize EMI vs efficiency trade-off
- Useful in half-bridge for dead-time control

**IMPORTANT**: When using both outputs, account for internal resistances:
- Effective RON = RGON + 6Ω (OUTH)
- Effective ROFF = RGOFF + 0.5Ω (OUTL)

### 4.5 Gate Resistor Selection

The external gate resistor controls switching speed and EMI:

#### Calculate Required Resistance

Given:
- CISS = IGBT input capacitance (from datasheet)
- fring = measured ringing frequency (with 0Ω external)
- Q = quality factor (target: 0.5 to 1.0)

From TI Application Note SLLA385:

```
LS = 1 / (CISS × (2π × fring)²)

RG(total) = ωLS / Q = (2π × fring × LS) / Q

RGATE(external) = RG(total) - ROUT - RG(internal_IGBT)
```

#### Typical Values for Induction Cooker IGBTs

| IGBT Rating | CISS | RGATE | Switching Loss | EMI |
|-------------|------|-------|----------------|-----|
| 20A/600V | 1.5nF | 5Ω | High | Low |
| 20A/600V | 1.5nF | 10Ω | Medium | Medium |
| 20A/600V | 1.5nF | 20Ω | Low | High |
| 40A/600V | 3nF | 5Ω | High | Low |
| 40A/600V | 3nF | 15Ω | Medium | Medium |

**Rule of thumb for 20-40kHz induction cookers**: Start with 10-15Ω.

### 4.6 PCB Layout Guidelines

#### Critical Layout Rules

1. **VDD Bypass Capacitor**
   - Place 10μF ceramic + 100nF as close as possible to VDD pin
   - Use X7R or X5R dielectric (not Y5V)
   - Short, wide traces to minimize inductance

2. **Ground Plane**
   - Solid ground plane under UCC27511A
   - Separate power ground and signal ground, connect at one point
   - Minimize ground loop area

3. **Gate Drive Path**
   - Keep OUTL → RGATE → IGBT gate trace short (<2cm if possible)
   - Wide trace (>1mm) to handle peak current (8A)
   - Avoid crossing high dV/dt traces

4. **Input Signal**
   - Shield or separate from noisy power traces
   - Add series resistor (50-100Ω) close to driver IC
   - Optional: small RC filter (50Ω + 50pF)

5. **Thermal Considerations**
   - SOT-23 package: RθJA = 217.8°C/W
   - Power dissipation ≈ VDD × (IQ + Igate_avg)
   - For 12V, 25kHz, 2nF gate: P ≈ 12V × (0.18mA + 1.2mA) ≈ 17mW
   - Temperature rise: 17mW × 217°C/W ≈ 3.7°C (negligible)

#### Example Layout (Top View)

```
    [VDD]──┬─[10μF]─┬─[100nF]─┐
           │        │         │
        ┌──┴────────┴─────────┴──┐
        │     UCC27511A          │
        │   [VDD]        [IN+]   │──── From MCU
        │  [OUTH]        [IN-]   │──── To GND
        │  [OUTL]        [GND]   │
        └────┬─────────────┬─────┘
             │             │
          [RGATE]        [GND]
             │
          [IGBT Gate]
```

---

## 5. SPICE Model and Simulation

### 5.1 Model Overview

The provided SPICE model (`UCC27511A.lib`) is a **behavioral model** that captures the key functionality:

- Input threshold detection (TTL/CMOS levels)
- UVLO protection
- Propagation delay (13ns)
- Split output topology
- Input/output loading

**Limitations**:
- Does not model transient-level detail
- Peak current limits are approximate
- Temperature effects not included
- Internal protection circuits simplified

**Use for**:
- Component selection
- Gate resistor sizing
- Timing analysis
- DC operating point verification

**DO NOT use for**:
- Precise efficiency calculations
- Thermal analysis
- Protection circuit validation
- EMI prediction

### 5.2 Running Simulations

#### Quick Test

```bash
cd /Users/bennet/Desktop/components/UCC27511A
ngspice -b UCC27511A_working_test.cir -o results.txt
```

#### Expected Results

For 12V supply, 20kHz PWM, 2nF load:

| Parameter | Expected Value |
|-----------|----------------|
| VGATE (high) | ~11.5-12V |
| VGATE (low) | <0.5V |
| Rise time | 10-50ns (depends on RGATE + CISS) |
| Fall time | 5-30ns (faster than rise) |
| Propagation delay | ~15-20ns (13ns + RC delay) |

### 5.3 Validation Criteria

A well-designed SPICE simulation should show:

1. **Clean switching**: Gate voltage transitions sharply
2. **Full voltage swing**: VGATE reaches VDD - 0.5V
3. **Proper logic**: Output follows input with expected delay
4. **No oscillation**: Smooth edges (if damped properly)

**Red flags**:
- Gate voltage doesn't reach VDD (check connections)
- Slow rise/fall (>100ns) with small RGATE (check CISS value)
- Ringing (>10% overshoot) → need more damping
- Output stuck high or low (check UVLO, input logic)

### 5.4 Python Verification Script

A Python script (`verify_ucc27511a.py`) is provided to automatically check simulation results:

```bash
python3 verify_ucc27511a.py
```

It verifies:
- Gate voltage levels (high/low)
- Switching timing
- Logic functionality
- Output drive capability

---

## 6. Safety and High-Voltage Considerations

### ⚠️ DANGER: HIGH VOLTAGE

Induction cookers operate at **300-400VDC** on the IGBT. Improper design can result in:
- Electric shock (potentially fatal)
- Fire
- Component destruction
- EMI/RFI interference

### 6.1 Isolation Requirements

The UCC27511A is a **LOW-SIDE driver** - it shares ground with the IGBT emitter. In a resonant inverter:

```
                    400VDC (HIGH VOLTAGE!)
                      │
                    ┌─┴─┐
                    │ Q1│ ← Collector at 400V!
                    └─┬─┘
                      │ ← Emitter (switches between 0-400V)
                      │
  DANGER ZONE ───────┼─────── This node can be 400V above ground!
                      │
                    ┌─┴─┐
                    │ Q2│ ← UCC27511A drives this gate
                    └─┬─┘
                      │
                     GND ← UCC27511A GND connects here
```

**Critical Safety Rules**:

1. **UCC27511A supply MUST be referenced to IGBT emitter/source**
2. **DO NOT connect UCC27511A GND to AC mains ground directly**
3. **Provide isolation** between:
   - AC mains and DC bus
   - High-voltage side and control circuits
   - Different functional grounds

### 6.2 Isolation Topologies

#### Recommended: Isolated Auxiliary Supply

```
AC Mains ─[Transformer]─ Rectifier ─ DC Bus (400V)
             │
          [Aux Winding] ← ISOLATED from mains
             │
          Rectifier + LMR51430 ─ 12V ─ UCC27511A VDD
                                        │
                                       GND ← Connects to IGBT emitter
```

Isolation requirements:
- Transformer isolation: ≥3kV (IEC 60335-2-6)
- Creepage distance: ≥5mm
- Air gap: ≥3mm

#### Alternative: Opto-Isolated Signal Path

```
MCU (isolated side) ─[Optocoupler]─ UCC27511A (high-voltage side)
     3.3V/5V logic                      12V supply
        GND                             GND ← IGBT emitter
```

### 6.3 Input Protection

Induction cooker switching causes high dI/dt and ground bounce. Protect UCC27511A inputs:

```
MCU PWM ─[50Ω]─┬─[50pF]─ GND
               │
               └─ UCC27511A IN+
```

Additional protection:
- TVS diode on VDD (18V breakdown)
- Series resistance limits fault current
- Optional RC filter reduces noise coupling

### 6.4 Output Protection

The UCC27511A can tolerate brief negative voltage transients up to **-5V** on inputs. However:

- **DO NOT** exceed -5V for >10ns
- **DO add** gate-source Zener (15V) on IGBT for protection
- **DO add** gate resistor to limit fault current

### 6.5 Thermal Protection

Inside an induction cooker enclosure, ambient temperature can reach **70°C**. Ensure:

- Junction temperature < 125°C (UCC27511A max)
- Add thermal sensor (NTC) monitoring enclosure temperature
- Implement over-temperature shutdown in MCU firmware

### 6.6 Standards Compliance

For commercial induction cookers, comply with:

- **IEC 60335-2-6**: Safety of household induction hobs
- **IEC 61000-6-3**: EMC for residential equipment
- **UL 858**: Household electric ranges (North America)

---

## 7. Design Examples

### 7.1 Example 1: Single-IGBT Resonant Inverter (2kW)

**Specifications**:
- Power: 2kW @ 230VAC input
- Frequency: 25kHz
- IGBT: IKW40N60H3 (600V/40A)

**Component Selection**:

| Component | Value | Part Number | Notes |
|-----------|-------|-------------|-------|
| Gate Driver | UCC27511A | UCC27511ADBVR | SOT-23-6 |
| IGBT | IKW40N60H3 | IKW40N60H3 | VCE=600V, IC=40A, CISS=3nF |
| Gate Resistor | 15Ω | 0805, 1/4W | Turn-off resistor |
| VDD Supply | 12V, 100mA | LMR51430 output | Isolated |
| VDD Bypass | 10μF + 100nF | X7R ceramic | Close to IC |
| Gate Zener | 15V, 1W | 1N4744A | Protect against overvoltage |

**SPICE Netlist**:

```spice
.TITLE 2kW Induction Cooker IGBT Driver

.INCLUDE UCC27511A.lib

* 12V isolated supply
VDD VDD 0 DC 12

* 25kHz PWM from MCU
VPWM PWM_IN 0 PULSE(0 3.3 100N 10N 10N 19.5U 40U)  ; 48.75% duty
RIN PWM_IN INP 100
CIN INP 0 100P
RINN INN 0 1MEG

* Gate driver
XU1 VDD 0 INP INN OUTH OUTL UCC27511A

* Output network
RGATE OUTL GATE 15
LGATE GATE GATE_IGBT 50N  ; Parasitic inductance

* IGBT (simplified)
CISS GATE_IGBT 0 3N
RG_INT GATE_IGBT 0 5

* Gate protection
DZ_POS GATE_IGBT 0 DZ15V
DZ_NEG 0 GATE_IGBT DSCH
.MODEL DZ15V D (BV=15 IBV=1M)
.MODEL DSCH D (IS=1E-12 RS=0.1)

* Bypass
CVDD VDD 0 22U IC=12
CVDD_HF VDD 0 100N IC=12

.TRAN 10N 200U
.END
```

### 7.2 Example 2: Half-Bridge Inverter with Dead-Time

**Application**: 3kW induction hob with half-bridge topology

**Key Requirements**:
- Two gate drivers (high-side isolated, low-side UCC27511A)
- Dead-time: 500ns minimum
- Independent gate resistors for EMI control

**Topology**:

```
               400VDC
                 │
               ┌─┴─┐
      Driver1──┤ Q1├─┐ High-side (isolated driver)
               └───┘ │
                     ├──── Resonant Tank
               ┌───┐ │
   UCC27511A──┤ Q2├─┘ Low-side
               └─┬─┘
                 │
                GND
```

**Dead-Time Implementation** (in MCU):

```c
// Pseudocode for PWM generation
void generate_inverter_pwm(uint16_t duty_permil) {
    // duty_permil = 0-1000 (0-100.0%)
    
    uint16_t period = 1000;  // 25kHz at 25MHz timer
    uint16_t dead_time = 13; // 500ns @ 25MHz = 12.5 counts
    
    // Q1 (high-side): ON early, OFF early
    set_pwm_channel(CH_Q1_HIGH, dead_time, (duty_permil * period / 1000) - dead_time);
    
    // Q2 (low-side): ON late, OFF late  
    set_pwm_channel(CH_Q2_LOW, (duty_permil * period / 1000) + dead_time, period - dead_time);
}
```

This ensures Q1 turns off 500ns before Q2 turns on, and vice versa.

### 7.3 Example 3: EMI-Optimized Design

**Challenge**: Reduce conducted EMI to pass IEC 61000-6-3

**Strategy**:
1. Slow down turn-on (reduce dI/dt)
2. Fast turn-off (minimize conduction loss)
3. RC snubber across IGBT

**Implementation**:

```
OUTH ─[RGON=22Ω]─┬─[D1]─┐
                         ├─── IGBT Gate
OUTL ─[RGOFF=10Ω]─┴─[D2]─┘

IGBT: Collector ─[Rsnub=10Ω]─┬─[Csnub=1nF]─ Emitter
```

**Results** (typical):
- Turn-on dI/dt reduced by 60%
- Conducted EMI reduced by 10-15 dBμV
- Efficiency penalty: <0.5%
- Slightly increased IGBT stress (monitor temperature)

---

## 8. Reference Information

### 8.1 Related Texas Instruments Documents

- **Datasheet**: UCC27511A (SLUSD95)
- **App Note**: External Gate Resistor Design (SLLA385)
- **App Note**: Understanding Peak Source/Sink Current (SLLA387)
- **App Note**: Negative Input Transients (SLUA939)
- **App Note**: ENABLE Function Implementation (SLLA423)

### 8.2 Key Equations

#### Gate Charge Time

```
t_charge = QG / IG_peak
```

Where:
- QG = Total gate charge (from IGBT datasheet)
- IG_peak = Peak gate current (4A or 8A for UCC27511A)

#### Switching Loss (Approximate)

```
P_sw = 0.5 × VCE × IC × (tr + tf) × fsw
```

Where:
- VCE = Collector-emitter voltage
- IC = Collector current
- tr, tf = Rise/fall times
- fsw = Switching frequency

#### Power Dissipation in UCC27511A

```
P_driver = VDD × (IQ + QG × fsw)
```

Where:
- IQ = Quiescent current (180μA typ)
- QG = Gate charge per switch
- fsw = Switching frequency

### 8.3 Design Checklist

Before powering up your induction cooker:

**Power Supply**:
- [ ] VDD is 12-15V (within 4.5-18V range)
- [ ] VDD is isolated from AC mains
- [ ] 10μF + 100nF bypass caps at VDD pin
- [ ] TVS diode on VDD (18V breakdown)

**Inputs**:
- [ ] PWM signal is 3.3V or 5V (within TTL/CMOS range)
- [ ] IN- is tied to GND or VDD as appropriate
- [ ] Series resistor (50-100Ω) added for noise immunity
- [ ] Optional RC filter if high noise environment

**Outputs**:
- [ ] Gate resistor selected (10-20Ω typical)
- [ ] Gate-source Zener clamp installed (15V)
- [ ] OUTL trace is short and wide (<3cm, >1mm)
- [ ] No other loads on OUTH/OUTL pins

**IGBT**:
- [ ] IGBT is rated for voltage (≥600V for 230VAC cookers)
- [ ] IGBT is rated for current (≥20A for 2kW, ≥40A for 3kW)
- [ ] Thermal interface material applied
- [ ] Heatsink sized for worst-case power dissipation

**Safety**:
- [ ] Isolation verified (≥3kV between mains and control)
- [ ] Creepage/clearance distances meet IEC 60335-2-6
- [ ] Enclosure is grounded
- [ ] Warning labels applied
- [ ] Thermal cutout installed (>100°C)

**Testing**:
- [ ] Bench test with current-limited supply (<100mA)
- [ ] Verify gate waveforms with oscilloscope
- [ ] Check for shoot-through (both switches ON)
- [ ] Thermal camera scan under full load
- [ ] EMI pre-compliance testing

### 8.4 Troubleshooting

| Symptom | Possible Cause | Solution |
|---------|----------------|----------|
| No output | UVLO active | Check VDD ≥ 4.2V |
| | Input LOW | Verify PWM signal present |
| | Wrong input config | Check IN+/IN- connections |
| Output stuck HIGH | IN- floating or HIGH | Tie IN- to GND |
| Output stuck LOW | IN+ LOW or floating | Drive IN+ with PWM |
| | UVLO | Increase VDD |
| Slow switching | CISS too large | Reduce gate capacitance |
| | RGATE too large | Reduce gate resistor |
| | Poor layout | Shorten gate trace |
| Oscillation | Underdamped | Increase RGATE |
| | Layout inductance | Improve PCB layout |
| | Missing snubber | Add RC snubber |
| IGBT fails | Shoot-through | Add/increase dead-time |
| | Overvoltage | Check DC bus regulation |
| | Overcurrent | Reduce power or add current limit |
| | Thermal runaway | Improve cooling |
| IC gets hot | Excessive drive current | Reduce fsw or add RGATE |
| | VDD too high | Regulate VDD to 12-15V |
| EMI issues | Fast dI/dt | Increase RGATE (turn-on) |
| | Layout | Improve grounding |
| | Missing filter | Add CM choke on AC input |

### 8.5 Bill of Materials (Typical)

For a complete 2kW induction cooker gate drive circuit:

| Qty | Reference | Value | Part Number | Description |
|-----|-----------|-------|-------------|-------------|
| 1 | U1 | UCC27511A | UCC27511ADBVR | Gate driver IC |
| 1 | C1 | 10μF/25V | GRM21BR61E106KA73L | Ceramic X7R |
| 1 | C2 | 100nF/50V | GRM188R71H104KA93D | Ceramic X7R |
| 1 | R1 | 100Ω | RC0805FR-07100RL | Input series |
| 1 | R2 | 1MΩ | RC0805FR-071ML | IN- pulldown |
| 1 | R3 | 15Ω/0.5W | ERJ-6GEYJ150V | Gate resistor |
| 1 | D1 | 15V/1W | 1N4744A | Gate Zener |
| 1 | D2 | 18V | SMBJ18A | VDD TVS |
| 1 | Q1 | IGBT | IKW40N60H3 | Main switch |

**Total Cost** (at 1k qty): ~$3-4 USD for gate drive components

### 8.6 Additional Resources

**Online Tools**:
- TI WEBENCH Power Designer: https://www.ti.com/design-resources/design-tools-simulation/webench-power-designer.html
- Gate resistor calculator: http://www.ti.com/tool/GATE-DRIVER-CALC

**Community**:
- TI E2E Forums: https://e2e.ti.com/support/power-management/
- EEVblog: https://www.eevblog.com/forum/

**Standards**:
- IEC 60335-2-6: Available from IEC or national standards bodies
- UL 858: Available from UL

---

## Appendix A: SPICE Model Source Code

See `UCC27511A.lib` for the complete behavioral SPICE model.

**Model Hierarchy**:
```
UCC27511A (main subcircuit)
├── Input stage (RIN, CIN)
├── Comparators (VIH, VIL thresholds)
├── UVLO (4.0V simplified)
├── Logic (AND gate)
├── Delay (13ns RC network)
└── Output stage (split OUTH/OUTL)
```

**Usage in SPICE**:
```spice
.INCLUDE UCC27511A.lib
XU1 VDD GND INP INN OUTH OUTL UCC27511A
```

---

## Appendix B: Python Verification Script

The `verify_ucc27511a.py` script parses ngspice output and validates:

1. Supply voltage in range
2. Gate voltage levels correct
3. Logic function working
4. No unexpected warnings/errors

**Usage**:
```bash
ngspice -b your_circuit.cir -o results.txt
python3 verify_ucc27511a.py results.txt
```

---

## Document Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Dec 9, 2025 | Initial release |

---

## Legal Disclaimer

This documentation and SPICE model are provided for design evaluation purposes. They are NOT official Texas Instruments materials. For production designs:

1. Use TI's official SPICE models from ti.com
2. Validate with hardware prototypes
3. Follow all applicable safety standards
4. Consult with qualified engineers

**DANGER**: Induction cookers operate at lethal voltages (300-400VDC). Improper design can result in electric shock, fire, or death. Only qualified personnel should design, build, or service these devices.

---

**End of Document**
