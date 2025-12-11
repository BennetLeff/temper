# LMR51430 SPICE Model Documentation for Induction Cooker Applications

## Table of Contents

1. [High-Level Summary](#1-high-level-summary)
2. [How to Use This Chip](#2-how-to-use-this-chip)
3. [Simulation Guide and Validation](#3-simulation-guide-and-validation)
4. [Safety Information](#4-safety-information)
5. [Additional Technical Details](#5-additional-technical-details)
6. [Quick Reference](#6-quick-reference)

---

## 1. High-Level Summary

### 1.1 What is the LMR51430?

The **LMR51430** is a synchronous buck (step-down) DC-DC converter from Texas Instruments' SIMPLE SWITCHER® family. It converts a higher input voltage (4.5V to 36V) to a lower, regulated output voltage while delivering up to 3A of continuous current. Key features include:

- **Wide input range**: 4.5V to 36V
- **High efficiency**: Up to 98% at optimal conditions
- **Integrated MOSFETs**: Both high-side and low-side switches are internal
- **Fixed frequency**: 500kHz or 1.1MHz options
- **Small package**: SOT-23-6 (2.9mm × 1.6mm)
- **Internal compensation**: Minimal external components required
- **Protection features**: Overcurrent, thermal shutdown, UVLO

### 1.2 Role in an Induction Cooker

In an induction cooker, the LMR51430 serves as the **auxiliary power supply** for the control electronics. Here's how it fits into the system architecture:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INDUCTION COOKER SYSTEM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────────┐   │
│  │ AC MAINS    │────▶│ RECTIFIER +     │────▶│ HALF-BRIDGE INVERTER    │   │
│  │ 120/240VAC  │     │ PFC (Optional)  │     │ (IGBT/MOSFET)           │   │
│  └─────────────┘     │ 300-400VDC      │     │ 20-50kHz switching      │   │
│                      └────────┬────────┘     └───────────┬─────────────┘   │
│                               │                          │                  │
│                               │                          ▼                  │
│                               │              ┌─────────────────────────┐   │
│                               │              │ RESONANT TANK           │   │
│                               │              │ (Inductor + Capacitor)  │   │
│                               │              └───────────┬─────────────┘   │
│                               │                          │                  │
│                               │                          ▼                  │
│                               │              ┌─────────────────────────┐   │
│                               │              │ INDUCTION COIL          │   │
│                               │              │ (Heats cookware)        │   │
│                               │              └─────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │                    AUXILIARY POWER SUPPLY SECTION                       ││
│  │                                                                         ││
│  │  ┌─────────────────┐     ┌───────────────┐     ┌───────────────────┐  ││
│  │  │ AUX WINDING     │────▶│  LMR51430     │────▶│ CONTROL SYSTEMS   │  ││
│  │  │ or              │     │  BUCK         │     │                   │  ││
│  │  │ STANDBY SMPS    │     │  CONVERTER    │     │ • MCU (3.3V/5V)   │  ││
│  │  │ 12-24VDC        │     │  ────────▶5V  │     │ • Gate Drivers    │  ││
│  │  └─────────────────┘     └───────────────┘     │ • Display         │  ││
│  │                                                │ • Touch Sensors   │  ││
│  │                                                │ • Fan Control     │  ││
│  │                                                │ • Safety Relays   │  ││
│  │                                                └───────────────────┘  ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Why Use the LMR51430 for Induction Cookers?

| Requirement | LMR51430 Capability |
|-------------|---------------------|
| **Wide input voltage** | Handles 4.5-36V from aux winding variations |
| **Rugged operation** | Designed for industrial/appliance applications |
| **High efficiency** | Reduces heat in enclosed enclosures |
| **Current capability** | 3A supports MCU + gate drivers + peripherals |
| **Protection** | OCP and TSD protect during fault conditions |
| **Temperature range** | -40°C to 150°C junction (handles hot environments) |
| **Cost effective** | Low component count, small footprint |

### 1.4 Typical Load Budget for Induction Cooker

| Subsystem | Typical Current @ 5V |
|-----------|---------------------|
| MCU (e.g., STM32, ESP32) | 50-150mA |
| Gate driver ICs (×2) | 100-300mA |
| Isolated gate driver power | 200-500mA |
| Display (LCD/LED) | 50-200mA |
| Touch controller | 20-50mA |
| Sensors (thermistors, current) | 10-30mA |
| Cooling fan PWM circuit | 50-100mA |
| Relay drivers | 100-200mA |
| Safety margin | 500mA |
| **Total** | **~1.5-2A typical, 3A max** |

---

## 2. How to Use This Chip

### 2.1 Basic Application Circuit

```
                              L1
        ┌────────────────────[===]────────────────┬──────────● VOUT (5V)
        │                    6.8µH                │          
        │                                         │          
        │    ┌──────────────────────┐            │ ┌───┐    
        │    │      LMR51430        │            ├─┤   │    
        │    │                      │            │ │C5 │22µF
   VIN ─┼────┤VIN (3)      SW (2)├────────────┘ │   │    
  12-24V│    │                      │              └─┬─┘    
        │    │                      │                │      
   ┌────┤    │                 CB (6)├────┬─────────│──────┐
   │    │    │                      │    │         │      │
  ─┴─   │    │                      │   ─┴─        │    ┌─┴─┐
  CIN   │    │                      │   CBOOT     ─┴─   │   │
  4.7µF │    │                      │   0.1µF     C6    │R1 │
  ─┬─   │    │                 FB (4)├─────┬──────┬─    │   │100k
   │    │    │                      │     │      │     └─┬─┘
   │    │    │                      │     │     ─┴─      │
   │    │    │                 EN (5)├──┐  │     R2      ├────● FB
   │    │    │                      │  │  │     13.7k   │
   │    │    │                GND (1)├──┼──┼──────┼──────┘
   │    │    └──────────────────────┘  │  │      │
   │    │                              │  │      │
   └────┴──────────────────────────────┴──┴──────┴────────────● GND
```

### 2.2 Component Selection Guide

#### Output Voltage Setting

The output voltage is set by the resistor divider on the FB pin:

```
VOUT = VREF × (1 + RFBT/RFBB)

where VREF = 0.6V
```

**Common configurations:**

| VOUT | RFBT | RFBB |
|------|------|------|
| 3.3V | 100kΩ | 22.1kΩ |
| 5.0V | 100kΩ | 13.7kΩ |
| 12V | 100kΩ | 5.23kΩ |

#### Inductor Selection

For 500kHz switching frequency:

```
L_MIN = (VIN_MAX - VOUT) × VOUT / (VIN_MAX × FSW × KIND × IOUT_MAX)

where KIND = 0.3 (30% ripple ratio, recommended)
```

**Recommended inductors for 5V output:**

| Switching Freq | Inductance | Saturation Current | Example Part |
|----------------|------------|-------------------|--------------|
| 500kHz | 6.8µH | >5A | Würth 744314068 |
| 1.1MHz | 3.3µH | >5A | Würth 744311330 |

#### Capacitor Selection

**Input capacitors:**
- Minimum: 4.7µF ceramic (X7R, 50V rating)
- Recommended: 2× 4.7µF in parallel
- Place as close as possible to VIN and GND pins

**Output capacitors:**
- Minimum: 22µF ceramic (X7R, 25V rating)
- Recommended: 2× 22µF in parallel for lower ripple
- Consider voltage derating of ceramics

**Bootstrap capacitor:**
- Required: 0.1µF ceramic (X7R, 16V minimum)
- Place close to CB and SW pins

### 2.3 Enable Pin Configuration

#### Option 1: Always On (Simple)
```
VIN ────● EN
```
Converter starts when VIN exceeds UVLO threshold (~4.5V).

#### Option 2: External UVLO Setting
```
VIN ───[RENT]───┬───● EN
                │
               [RENB]
                │
               GND

VIN_START = VEN_TH × (RENT + RENB) / RENB

where VEN_TH = 1.227V (typical)
```

**Example for 6V start threshold:**
- RENB = 200kΩ
- RENT = (6V/1.227V - 1) × 200kΩ = 778kΩ → use 768kΩ

### 2.4 PCB Layout Guidelines

Critical layout considerations for EMI and thermal performance:

1. **Input capacitor placement**: Directly at VIN and GND pins
2. **SW trace**: Keep short and wide, avoid running under IC
3. **Ground plane**: Solid copper pour under and around device
4. **Feedback trace**: Route away from SW node, keep short
5. **Thermal vias**: Array of vias under GND pin to inner/bottom copper

```
       ┌────────────────────────────────────────────┐
       │  ┌─────────────────────────────────────┐   │
       │  │           GND COPPER POUR           │   │
       │  │    ┌───┐                            │   │
       │  │    │CIN│◄── Input cap close to VIN  │   │
       │  │    └───┘                            │   │
       │  │         ┌────────┐                  │   │
  VIN ─┼──┼────────►│LMR51430│──SW──────►[L1]──┼───┼──► VOUT
       │  │         └────────┘    ▲             │   │
       │  │              │        │ Keep short  │   │
       │  │    ○ ○ ○ ○ ○ │        │             │   │
       │  │    Thermal   │                      │   │
       │  │    vias      ▼                      │   │
       │  │           ┌───┐                     │   │
       │  │           │CB │ Bootstrap cap       │   │
       │  │           └───┘                     │   │
       │  └─────────────────────────────────────┘   │
       └────────────────────────────────────────────┘
```

---

## 3. Simulation Guide and Validation

### 3.1 Files Included in This Package

| File | Description |
|------|-------------|
| `LMR51430.lib` | Full behavioral SPICE model with switching |
| `LMR51430_simple.lib` | Averaged model for fast simulation |
| `LMR51430_test.cir` | Test netlist with multiple scenarios |
| `LMR51430.kicad_sym` | KiCad symbol with SPICE integration |

### 3.2 Running Simulations

#### Using ngspice (Command Line)

```bash
# Navigate to the model directory
cd /path/to/lmr51430_spice

# Run the test netlist
ngspice LMR51430_test.cir

# In ngspice interactive mode:
ngspice> source LMR51430_test.cir
ngspice> run
ngspice> plot v(vout_node)
```

#### Using KiCad with ngspice

1. Add the symbol library: `Preferences → Manage Symbol Libraries → Add LMR51430.kicad_sym`
2. Add the SPICE library path: `Simulation → Settings → Add path to LMR51430.lib`
3. Place the LMR51430X symbol in your schematic
4. Run simulation: `Inspect → Simulator`

### 3.3 What to Expect from Simulations

#### Startup Transient (0-15ms)

You should observe:

1. **Enable delay** (~100µs): Small delay before switching starts
2. **Soft-start ramp** (~4ms): Output voltage rises linearly
3. **Overshoot** (<5%): Small overshoot at end of soft-start
4. **Settling time** (~1ms): Voltage settles to final value

**Expected waveforms:**

```
VOUT
  5V ─────────────────────────────────────────────
                      ╱─────────────────────────
                    ╱
                  ╱
                ╱
  0V ────────╱
      0    2ms   4ms   6ms   8ms   10ms  12ms  14ms
           └─soft-start─┘
```

#### Steady-State Operation

At full load (3A), expect:

| Parameter | Expected Value | Acceptable Range |
|-----------|---------------|------------------|
| VOUT average | 5.00V | 4.925V - 5.075V (±1.5%) |
| VOUT ripple (p-p) | 20-50mV | <100mV |
| Inductor current ripple | 0.6-1.0A | 20-40% of IOUT |
| Switching frequency | 500kHz | 450-560kHz |

#### Load Transient Response

For a 1A to 2.5A step:

| Parameter | Expected Value |
|-----------|---------------|
| Undershoot | 150-250mV |
| Recovery time | 100-200µs |
| Overshoot (on unload) | 100-200mV |

### 3.4 Validating the SPICE Model

#### Checklist for Model Validation

| Test | Pass Criteria | How to Verify |
|------|--------------|---------------|
| **DC accuracy** | VOUT within ±3% of target | `.MEAS TRAN VOUT_AVG` |
| **Startup time** | 4-6ms to 90% | `.MEAS TRAN T_STARTUP` |
| **Switching frequency** | Within ±12% of spec | FFT of SW node |
| **Efficiency** | >85% at full load | `POUT/PIN` measurement |
| **Current limit** | Triggers at ~4.5A | Apply overload |
| **UVLO** | Shuts down <3.58V | Ramp VIN down |
| **Enable threshold** | Starts at 1.2V EN | Ramp EN voltage |

#### Sample Validation Script

```spice
* Validation measurements
.MEAS TRAN VOUT_AVG AVG V(VOUT_NODE) FROM=10M TO=15M
.MEAS TRAN VOUT_RIPPLE PP V(VOUT_NODE) FROM=10M TO=15M
.MEAS TRAN FSW_PERIOD TRIG V(SW_NODE) VAL=2.5 RISE=10 
+                       TARG V(SW_NODE) VAL=2.5 RISE=11

* Expected results:
* VOUT_AVG ≈ 5.0V (within ±3%)
* VOUT_RIPPLE < 100mV
* FSW_PERIOD ≈ 2µs (500kHz)
```

#### Red Flags (Model Issues)

If you observe any of these, the simulation may not be accurate:

- [ ] Output voltage oscillating or unstable
- [ ] Switching frequency far from 500kHz/1.1MHz
- [ ] Extremely high/low efficiency (<70% or >100%)
- [ ] Inductor current doesn't match load current average
- [ ] Protection features not triggering at specified thresholds

### 3.5 Model Limitations

**This behavioral model does NOT accurately represent:**

1. **EMI/EMC behavior**: Switch node ringing, conducted emissions
2. **Sub-nanosecond timing**: Exact rise/fall times, dead-time details
3. **Temperature effects**: Only nominal 25°C behavior modeled
4. **Package parasitics**: Bond wire inductance, pin capacitance
5. **PFM mode details**: Simplified light-load behavior

**For production design, always:**
- Build and test prototype hardware
- Perform thermal testing at maximum load
- Conduct EMC pre-compliance testing
- Verify protection features with actual fault conditions

---

## 4. Safety Information

### 4.1 Absolute Maximum Ratings

**Exceeding these values will cause permanent damage:**

| Parameter | Maximum Value | Notes |
|-----------|--------------|-------|
| VIN to GND | -0.3V to 38V | Never reverse polarity |
| EN to GND | -0.3V to VIN+0.3V | Never exceed VIN |
| FB to GND | -0.3V to 5.5V | Do not short to high voltage |
| SW DC | -0.3V to 38V | Inductive spikes can exceed |
| SW transient (<20ns) | -3.0V to 38V | Clamp with snubber if needed |
| Junction temperature | 150°C | Derate above 85°C ambient |
| Storage temperature | -65°C to 150°C | |

### 4.2 ESD Handling Precautions

The LMR51430 is sensitive to electrostatic discharge:

| Parameter | Rating |
|-----------|--------|
| HBM (Human Body Model) | ±1000V |
| CDM (Charged Device Model) | ±500V |

**Required precautions:**

1. ✓ Use grounded wrist straps when handling
2. ✓ Store in ESD-safe packaging
3. ✓ Use ESD-safe workstations
4. ✓ Ground soldering equipment
5. ✗ Do NOT touch pins directly
6. ✗ Do NOT slide across surfaces

### 4.3 Induction Cooker-Specific Safety Considerations

#### 4.3.1 High Voltage Isolation

```
╔══════════════════════════════════════════════════════════════════╗
║                    DANGER: HIGH VOLTAGE                          ║
║                                                                   ║
║  The main power stage operates at 300-400VDC.                    ║
║  The LMR51430 auxiliary supply MUST be properly isolated.        ║
║                                                                   ║
║  Required isolation methods:                                      ║
║  • Isolated auxiliary transformer winding                        ║
║  • Optocouplers for control signals crossing isolation           ║
║  • Minimum 3kV isolation barrier to mains-referenced circuits    ║
║  • Proper creepage and clearance per IEC 60335-2-6               ║
║                                                                   ║
╚══════════════════════════════════════════════════════════════════╝
```

#### 4.3.2 Thermal Management

Induction cookers generate significant heat. Design considerations:

```
Maximum power dissipation in LMR51430:

P_LOSS = I²OUT × (D×RDS_HS + (1-D)×RDS_LS) + switching losses

Example at 3A, 12V input, 5V output:
• D = 5V/12V = 0.42
• Conduction loss ≈ 9 × (0.42×0.12 + 0.58×0.07) = 0.82W
• Switching loss ≈ 0.2W (estimated)
• Total ≈ 1.0W

Temperature rise: ΔT = P × RθJA = 1.0W × 80°C/W = 80°C

If ambient = 70°C (inside cooker enclosure):
TJ = 70°C + 80°C = 150°C ← AT LIMIT!
```

**Thermal derating is essential:**

| Ambient Temperature | Maximum Safe Current |
|--------------------|--------------------|
| 25°C | 3.0A |
| 50°C | 2.5A |
| 70°C | 2.0A |
| 85°C | 1.5A |

**Mitigation strategies:**

1. Use copper pours for heat spreading
2. Add thermal vias to inner layers
3. Consider airflow from cooker fan
4. Position away from hot components
5. Use 1.1MHz variant for lower inductor losses

#### 4.3.3 Fault Conditions

The LMR51430 includes protection, but additional system-level protection is recommended:

| Fault Condition | LMR51430 Response | System-Level Protection |
|-----------------|-------------------|------------------------|
| Output short circuit | Hiccup mode (135ms cycle) | Fuse or PTC thermistor |
| Overcurrent | Cycle-by-cycle limiting | Current sense + MCU shutdown |
| Overtemperature | Thermal shutdown @163°C | NTC on PCB + MCU monitoring |
| Input overvoltage | None (clamp at 38V abs max) | TVS diode on VIN |
| Reverse polarity | Damage possible | Series Schottky or P-FET |

#### 4.3.4 Input Protection Circuit

Recommended input protection for induction cooker application:

```
AUX          D1           F1           TVS
SUPPLY   ────┤◄├────────[FUSE]────────┤>├────┬──── VIN
             │           250mA        │     │
         Reverse     (optional)   SMBJ36A  CIN
         polarity                          4.7µF
         protection                         │
                                           GND
```

### 4.4 Functional Safety Considerations

For IEC 61508/ISO 26262 applications, note:

| Parameter | Value | Reference |
|-----------|-------|-----------|
| Component FIT rate | 13 FIT | IEC TR 62380 |
| Die FIT rate | 11 FIT | Safety documentation |
| Package FIT rate | 2 FIT | Safety documentation |

**Failure Mode Distribution (per TI safety documentation):**

| Failure Mode | Probability |
|--------------|-------------|
| No output | 50% |
| Output not in spec | 40% |
| SW FET stuck on | 5% |
| Protection fails | 5% |

**For safety-critical applications:**

- Consider redundant power supplies
- Add output voltage monitoring with independent comparator
- Use watchdog to detect control system failure
- Implement fail-safe state for heating elements

---

## 5. Additional Technical Details

### 5.1 Operating Mode Selection

| Part Number | Frequency | Mode | Best For |
|-------------|-----------|------|----------|
| LMR51430XDDCR | 500kHz | PFM | General use, high light-load efficiency |
| LMR51430XFDDCR | 500kHz | FPWM | Noise-sensitive applications, constant frequency |
| LMR51430YDDCR | 1.1MHz | PFM | Smallest solution size |
| LMR51430YFDDCR | 1.1MHz | FPWM | High frequency + constant switching |

**PFM vs FPWM:**

- **PFM (Pulse Frequency Modulation)**: Better efficiency at light load (standby mode). Frequency varies with load.
- **FPWM (Forced PWM)**: Constant frequency at all loads. Lower output ripple. Easier EMI filtering.

### 5.2 Frequency Selection Guidelines

| Consideration | 500kHz | 1.1MHz |
|---------------|--------|--------|
| Solution size | Larger inductor | Smaller inductor |
| Efficiency at full load | Slightly better | Slightly worse |
| EMI spectrum | Lower harmonics | Higher harmonics |
| Transient response | Slower | Faster |
| Minimum VIN (for 5V out) | ~6V | ~6.5V |
| Maximum VIN (for 5V out) | ~35V | ~25V (freq foldback) |

### 5.3 Compensation and Stability

The LMR51430 uses internal compensation optimized for:

- Output capacitance: 20µF - 200µF ceramic
- Inductor range: 2.2µH - 15µH (depending on frequency)
- Load capacitance type: Ceramic (low ESR)

**If using electrolytic output capacitors:**

Electrolytic caps have higher ESR, which can affect loop stability. Add a ceramic capacitor in parallel:

```
VOUT ──┬────┬──────● Output
       │    │
      ─┴─  ─┴─
      C1   C2
     100µF 22µF
     Elec  Cer
      ─┬─  ─┬─
       │    │
      GND  GND
```

### 5.4 Power Dissipation Calculation

Total power loss in the LMR51430:

```
P_TOTAL = P_COND_HS + P_COND_LS + P_SW + P_GATE + P_QUIESCENT

Where:
P_COND_HS = IOUT² × RDS_HS × D
P_COND_LS = IOUT² × RDS_LS × (1-D)
P_SW = 0.5 × VIN × IOUT × (tRISE + tFALL) × FSW
P_GATE ≈ QG × VGS × FSW (typically small)
P_QUIESCENT = VIN × IQ (40µA typical, negligible)
```

### 5.5 Input Voltage Transient Handling

In induction cookers, the auxiliary winding voltage can vary significantly:

| Condition | Effect on Aux Voltage | LMR51430 Response |
|-----------|----------------------|-------------------|
| Startup | Slow ramp-up | Wait in UVLO until >4.5V |
| Full power | Slight droop | Maintains regulation |
| Power burst | Spike possible | Clamp with TVS if >36V |
| Shutdown | Decay to 0V | Controlled shutdown |
| Load dump | Transient spike | Protected to 38V abs max |

**Recommended input transient protection:**

```
VIN ────────┬──────[10Ω]──────┬─────── To LMR51430 VIN
            │                 │
           ─┴─              ─┴─
           TVS              CIN
           36V              4.7µF
           ─┬─              ─┬─
            │                │
           GND              GND
```

---

## 6. Quick Reference

### 6.1 Design Checklist

#### Schematic Design
- [ ] VIN and GND pins have decoupling capacitor (≥4.7µF)
- [ ] Bootstrap capacitor (0.1µF) connected between CB and SW
- [ ] Feedback resistor divider correctly calculated for VOUT
- [ ] EN pin connected (to VIN directly or via divider for UVLO)
- [ ] Output capacitance ≥44µF for 5V/3A application
- [ ] Inductor correctly sized for frequency and current

#### Layout Design
- [ ] Input capacitor placed within 3mm of VIN/GND pins
- [ ] Solid ground plane under device
- [ ] SW trace short and wide (≥40 mil for 3A)
- [ ] Bootstrap cap close to CB pin
- [ ] FB trace routed away from SW node
- [ ] Thermal vias under device GND
- [ ] Output capacitors near inductor output

#### Protection
- [ ] Input fuse or PTC (if required)
- [ ] TVS on input (if transients expected)
- [ ] Reverse polarity protection (if applicable)
- [ ] Output current monitoring (for safety-critical)

### 6.2 Typical BOM for 5V/3A Output

| Reference | Value | Package | Part Number |
|-----------|-------|---------|-------------|
| U1 | LMR51430 | SOT-23-6 | LMR51430XDDCR |
| CIN | 4.7µF × 2 | 1210 | GRM32ER71H475KA88L |
| COUT | 22µF × 2 | 1210 | GRM32ER71E226KE15L |
| CBOOT | 0.1µF | 0603 | GRM188R71H104KA93D |
| L1 | 6.8µH | 7×7mm | Würth 744314068 |
| RFBT | 100kΩ | 0603 | CRCW0603100KFKEA |
| RFBB | 13.7kΩ | 0603 | CRCW060313K7FKEA |

### 6.3 Troubleshooting Guide

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| No output | EN below threshold | Check EN divider or VIN |
| Low output voltage | FB divider error | Recalculate resistors |
| High output ripple | Insufficient COUT | Add more capacitance |
| Overheating | Excessive load or poor layout | Improve thermal design |
| Oscillation | ESR too high or too low | Add/remove ceramic caps |
| Startup failure | Large COUT or pre-load | Check soft-start timing |
| Audible noise | PFM mode + piezo caps | Use FPWM variant |

### 6.4 Key Equations Summary

```
Output Voltage:         VOUT = 0.6V × (1 + RFBT/RFBB)

Duty Cycle:             D = VOUT / VIN

Inductor Ripple:        ΔIL = (VIN - VOUT) × D / (L × FSW)

Output Ripple:          ΔVOUT ≈ ΔIL × ESR + ΔIL / (8 × FSW × COUT)

Power Loss:             PLOSS ≈ IOUT² × (D×0.12 + (1-D)×0.07) + PSW

Junction Temperature:   TJ = TA + PLOSS × RθJA
```

---

## Appendix A: Model File Reference

### LMR51430.lib
Main behavioral model with full switching simulation. Includes:
- VIN UVLO with hysteresis
- Precision enable
- Soft-start ramp
- Peak current mode control
- Cycle-by-cycle current limiting
- Hiccup mode short circuit protection
- Gate drive with dead time

### LMR51430_simple.lib
Simplified averaged model for fast simulation. Use for:
- Initial design exploration
- Component value optimization
- Stability analysis (with modifications)

### LMR51430_test.cir
Complete test netlist including:
- Proper component models
- Multiple test scenarios
- Measurement statements
- Interactive ngspice control section

### LMR51430.kicad_sym
KiCad symbol library with:
- All four device variants
- SPICE model integration
- Correct pin mapping

---

## Document Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024 | Initial release |

---

*This documentation is provided for educational and design reference purposes. Always refer to the official Texas Instruments datasheet for the most current specifications and application guidelines.*
