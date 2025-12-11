# MAX31865 RTD-to-Digital Converter - Comprehensive Documentation

## Table of Contents
1. [High-Level Summary](#high-level-summary)
2. [Role in Induction Cooker](#role-in-induction-cooker)
3. [How to Use This Chip](#how-to-use-this-chip)
4. [SPICE Simulation Guide](#spice-simulation-guide)
5. [Safety Information](#safety-information)
6. [Design Considerations](#design-considerations)
7. [PCB Layout Guidelines](#pcb-layout-guidelines)
8. [Bill of Materials](#bill-of-materials)
9. [Troubleshooting](#troubleshooting)
10. [References and Resources](#references-and-resources)

---

## High-Level Summary

### Overview
The **MAX31865** is an easy-to-use resistance-to-digital converter from Maxim Integrated (now part of Analog Devices) optimized for platinum resistance temperature detectors (RTDs). This precision IC converts RTD resistance into a digital value with excellent linearity and accuracy, making it ideal for high-precision temperature measurement applications.

### Key Features

| Feature | Specification |
|---------|--------------|
| **ADC Resolution** | 15 bits (no missing codes) |
| **Conversion Type** | Ratiometric (RTD/Reference) |
| **RTD Support** | PT100, PT1000 (100Ω to 1kΩ @ 0°C) |
| **Temperature Range** | -200°C to +850°C (sensor dependent) |
| **Accuracy** | 0.5°C max (0.05% of full scale) |
| **Supply Voltage** | VDD: 3.0 V to 3.6 V<br>DVDD: 3.0 V to 3.6 V |
| **Supply Current** | 2.0 mA typ (VDD active)<br>100 µA typ (DVDD idle) |
| **Wiring Modes** | 2-wire, 3-wire, 4-wire RTD connections |
| **Conversion Time** | 52 ms (60Hz notch) / 62.5 ms (50Hz notch) |
| **Interface** | SPI (up to 5 MHz, modes 1 & 3) |
| **Input Protection** | ±45 V on RTD pins |
| **Fault Detection** | Open RTD, shorted RTD, over/under voltage |
| **Package** | 20-pin SSOP |
| **Temperature Range** | -40°C to +125°C (ambient) |

### Technology: Precision Ratiometric Measurement

The MAX31865 uses a **ratiometric measurement technique**:

```
ADC_CODE = (RTD_Resistance / Reference_Resistance) × 2^15
```

This approach provides several advantages:
- **Eliminates absolute voltage reference errors** - only ratio matters
- **Cancels supply voltage variations** - both measurements use same supply
- **High resolution** - 15-bit ADC provides 0.003% resolution (1/32768)
- **Linear output** - directly proportional to RTD resistance

### Pin Configuration (20-pin SSOP)

```
          ┌──────────┐
    DRDY  │1      20│ N.C.
    DVDD  │2      19│ GND1
     VDD  │3      18│ DGND
    BIAS  │4      17│ SDO
  REFIN+  │5      16│ CS
  REFIN-  │6      15│ SCLK
 ISENSOR  │7      14│ SDI
  FORCE+  │8      13│ GND2
  FORCE2  │9      12│ FORCE-
  RTDIN+  │10     11│ RTDIN-
          └──────────┘
```

**Pin Descriptions:**
- **Pin 1 (DRDY):** Data ready output (active low, push-pull)
- **Pin 2 (DVDD):** Digital supply voltage (3.0-3.6V)
- **Pin 3 (VDD):** Analog supply voltage (3.0-3.6V)
- **Pin 4 (BIAS):** Bias voltage output (2.0V typ, up to 5.75mA)
- **Pin 5 (REFIN+):** Positive reference voltage input
- **Pin 6 (REFIN-):** Negative reference voltage input
- **Pin 7 (ISENSOR):** Low side of reference resistor
- **Pin 8 (FORCE+):** High-side RTD drive (excitation current source)
- **Pin 9 (FORCE2):** 3-wire positive input (connect to FORCE+ for 3-wire)
- **Pin 10 (RTDIN+):** Positive RTD input (high-impedance ADC input)
- **Pin 11 (RTDIN-):** Negative RTD input (high-impedance ADC input)
- **Pin 12 (FORCE-):** Low-side RTD return (excitation current sink)
- **Pin 13 (GND2):** Analog ground
- **Pin 14 (SDI):** Serial data input (SPI MOSI)
- **Pin 15 (SCLK):** Serial clock input (SPI CLK)
- **Pin 16 (CS):** Chip select input (active low, SPI CS)
- **Pin 17 (SDO):** Serial data output (SPI MISO, tri-state)
- **Pin 18 (DGND):** Digital ground
- **Pin 19 (GND1):** Analog ground
- **Pin 20 (N.C.):** No connect

### RTD Wiring Configurations

The MAX31865 supports three RTD connection methods:

#### 4-Wire RTD (Most Accurate)
```
        FORCE+  ──────┐
                      │
        RTDIN+  ──────┼──── RTD High ──── RTD
                      │                   │
                                         │
        RTDIN-  ──────┼──── RTD Low  ─────┘
                      │
        FORCE-  ──────┘
        FORCE2  ────  GND
```
**Advantages:**
- Eliminates lead wire resistance errors completely
- Best accuracy (±0.05% typical)
- Recommended for precision applications

**Applications:**
- Laboratory instrumentation
- Precision industrial control
- High-accuracy temperature measurement

#### 3-Wire RTD (Compensated)
```
        FORCE+ ───┬───── RTD High ──── RTD
        FORCE2 ───┘                    │
                                       │
        RTDIN+ ────────── RTD High     │
                                       │
        RTDIN- ────────── RTD Low  ─────┘
        FORCE-  ───────── RTD Low
```
**Advantages:**
- Compensates for lead resistance (if leads matched)
- Good accuracy (±0.2% typical with matched cables)
- Widely used in industrial applications

**Applications:**
- Industrial process control
- HVAC systems
- Building automation

#### 2-Wire RTD (Simplest)
```
        FORCE+ ───┬───── RTD High ──── RTD
        RTDIN+ ───┘                    │
                                       │
        RTDIN- ───┬───── RTD Low  ─────┘
        FORCE-  ──┘
        FORCE2  ──  GND
```
**Advantages:**
- Simplest wiring
- Lowest cost (fewer wires)

**Disadvantages:**
- Lead wire resistance adds to measurement
- Lower accuracy (±0.5°C typical)

**Applications:**
- Non-critical temperature monitoring
- Short cable runs (<1 meter)
- Cost-sensitive applications

---

## Role in Induction Cooker

### System Architecture

In an induction cooker, the MAX31865 provides **precision temperature monitoring** for critical thermal management:

```
AC Mains → Rectifier → PFC → Resonant Inverter → Induction Coil
                         │                              │
                         │                              ├─ Cookware
                         ├─ IGBTs (generate heat)       │
                         │                              └─ Heat to food
                         │
                    Heatsink
                         │
                    [PT100/PT1000 RTD]
                         │
                    MAX31865 → Microcontroller
```

### Critical Monitoring Points

#### 1. IGBT Temperature Monitoring
**Purpose:** Prevent thermal runaway and destruction

```
IGBT Heatsink → PT100 RTD → MAX31865 → MCU
                                         │
                                         ├─ Reduce power if >85°C
                                         ├─ Shutdown if >100°C
                                         └─ Resume when <70°C
```

**Typical Operating Range:**
- Normal operation: 40-70°C
- Warning threshold: 85°C (reduce power to 50%)
- Critical shutdown: 100°C (full shutdown)
- Hysteresis: Resume at 70°C

#### 2. Induction Coil Temperature
**Purpose:** Detect overheating from blocked airflow or cookware issues

```
Induction Coil → PT100 RTD → MAX31865 → MCU
                                          │
                                          ├─ Warning if >120°C
                                          └─ Shutdown if >150°C
```

**Typical Operating Range:**
- Normal operation: 50-90°C
- Warning threshold: 120°C (display warning)
- Critical shutdown: 150°C (coil damage risk)

#### 3. Ambient/Enclosure Temperature
**Purpose:** Monitor overall thermal management

**Typical Operating Range:**
- Normal operation: 25-50°C
- Warning threshold: 60°C (check ventilation)
- Critical shutdown: 70°C (thermal management failure)

### Why MAX31865 for Induction Cookers?

| Requirement | MAX31865 Advantage |
|-------------|-------------------|
| **High Accuracy** | 0.5°C accuracy protects expensive IGBTs |
| **Wide Range** | -40°C to +125°C covers all operating conditions |
| **Noise Immunity** | 50/60Hz notch filter rejects AC line interference |
| **Fault Detection** | Detects open RTD (sensor failure) before damage occurs |
| **Low Power** | 2mA typical doesn't burden auxiliary supply |
| **Isolation Friendly** | SPI interface easily isolated with ADUM1250 |
| **Ratiometric** | Immune to supply voltage fluctuations from switching noise |

### Integration with Control System

```
┌──────────────────────────────────────────────────────────────┐
│                    Induction Cooker System                    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  [PT100 RTD] → MAX31865 → [ADUM1250] → Microcontroller      │
│   (IGBT         (3.3V)      (I2C        (3.3V/5V)            │
│   Heatsink)                 Isolator)                        │
│                                                               │
│                                          ↓                    │
│                                    [Control Logic]            │
│                                          ↓                    │
│                                    ┌────────────┐            │
│                                    │ If T>100°C │            │
│                                    │ Shutdown   │            │
│                                    └────────────┘            │
│                                          ↓                    │
│                                    Gate Driver → IGBT        │
└──────────────────────────────────────────────────────────────┘
```

**Typical Sampling Rate:**
- 1-2 measurements per second (adequate for thermal time constants)
- Faster sampling during active cooking (4-5 Hz)
- Slower during standby (0.5 Hz)

**Safety Features:**
- Redundant temperature sensors (two MAX31865 devices)
- Hardware over-temperature comparator (independent of MCU)
- Watchdog timer (resets MCU if temperature monitoring fails)

---

## How to Use This Chip

### Step 1: Select Reference Resistor

The reference resistor (RREF) sets the full-scale range:

| RTD Type | RTD @ 0°C | Recommended RREF | Full Scale Range |
|----------|-----------|------------------|------------------|
| **PT100** | 100Ω | **400Ω** | 0-400Ω (-200°C to +850°C) |
| **PT100** | 100Ω | 430Ω | 0-430Ω (extended range) |
| **PT1000** | 1000Ω | **4.3kΩ** | 0-4.3kΩ (-200°C to +850°C) |

**Selection Formula:**
```
RREF = 4 × RTD_nominal
```

**Example for PT100:**
```
RREF = 4 × 100Ω = 400Ω
```

**Reference Resistor Requirements:**
- **Tolerance:** 0.1% or better (0.05% recommended)
- **Temperature Coefficient:** 25 ppm/°C or better
- **Power Rating:** 0.125W minimum (0.25W recommended)
- **Type:** Metal film or wirewound precision resistor

**Recommended Parts:**
- Vishay Dale RN55D (0.1%, 10 ppm/°C, through-hole)
- Vishay TNPW0805 (0.1%, 25 ppm/°C, SMD)
- Susumu RG Series (0.05%, 10 ppm/°C, SMD)

### Step 2: Connect Reference Resistor

```
   BIAS (Pin 4) ────┬──── REFIN+ (Pin 5)
                    │
                 [RREF]
                  400Ω
                    │
      REFIN- (Pin 6) ──── ISENSOR (Pin 7) ──── GND1
```

**Critical:**
- BIAS must connect to REFIN+ (provides excitation current)
- REFIN- must connect to ISENSOR (current sensing)
- Keep traces short and equal length
- Use Kelvin connections for high accuracy

### Step 3: Connect RTD Sensor

**4-Wire Configuration (Recommended):**

```
MAX31865                          RTD Sensor
                                  PT100/PT1000
   FORCE+ (8)  ──[100Ω cable]──┐
                                ├─── RTD+
   RTDIN+ (10) ──[1Ω sense]────┘      │
                                      RTD
   RTDIN- (11) ──[1Ω sense]────┐      │
                                ├─── RTD-
   FORCE- (12) ──[100Ω cable]──┘

   FORCE2 (9)  ──── GND
```

**3-Wire Configuration:**

```
MAX31865                          RTD Sensor
                                  PT100/PT1000
   FORCE+ (8)  ──┐
                 ├──[cable]────┬─── RTD+
   FORCE2 (9)  ──┘             │     │
                               │    RTD
   RTDIN+ (10) ──[cable]───────┘     │
                                     │
   RTDIN- (11) ──[cable]───────┬─── RTD-
                               │
   FORCE- (12) ──[cable]───────┘
```

### Step 4: Add Filter Capacitor

**Purpose:** Filter noise on RTD inputs

```
   RTDIN+ ────┬──────── RTDIN-
              │
           [C_FILTER]
```

**Recommended Values:**

| RTD Type | Capacitance | Settling Time |
|----------|-------------|---------------|
| PT100 (100Ω) | **100 nF** | 50 µs (5τ) |
| PT1000 (1kΩ) | **10 nF** | 50 µs (5τ) |

**Capacitor Requirements:**
- **Type:** C0G/NP0 ceramic (best stability) or X7R
- **Voltage Rating:** 50V minimum
- **Tolerance:** 10% or better

**Critical:**
- Place capacitor close to MAX31865 pins
- Ensure conversion delay > 5× RC time constant
- Larger capacitors reduce noise but increase settling time

### Step 5: Power Supply Decoupling

```
   VDD (3) ───┬─── 10 µF (bulk) ──┬─── GND1 (19)
              │                   │
              └─── 100 nF (HF) ───┘

   DVDD (2) ──┬─── 10 µF (bulk) ──┬─── DGND (18)
              │                   │
              └─── 100 nF (HF) ───┘
```

**Capacitor Requirements:**
- **10 µF:** X7R ceramic or tantalum, 10V rating
- **100 nF:** X7R ceramic, 50V rating
- **Placement:** Within 5mm of IC pins
- **Grounds:** Connect GND1, GND2, DGND at single point near IC

### Step 6: SPI Interface Connections

```
Microcontroller              MAX31865

GPIO_CS   ───────────────── CS (16)
SPI_CLK   ───────────────── SCLK (15)
SPI_MOSI  ───────────────── SDI (14)
SPI_MISO  ───────────────── SDO (17)

                             DRDY (1) ──── GPIO_INT (optional)
```

**SPI Configuration:**
- **Mode:** SPI Mode 1 or Mode 3 (CPOL=0,CPHA=1 or CPOL=1,CPHA=1)
- **Clock:** Up to 5 MHz
- **Bit Order:** MSB first
- **CS:** Active low (pull high when idle)

**Optional DRDY Usage:**
- Connect DRDY to MCU interrupt input
- Interrupt triggers when new conversion ready
- Reduces CPU polling overhead

### Step 7: Software Configuration

**Initialization Sequence:**

```c
// 1. Power-on delay
delay_ms(100);  // Wait for MAX31865 to initialize

// 2. Write configuration register
// - 60Hz filter, 4-wire RTD, auto-conversion mode
uint8_t config = 0xD1;  // 11010001b
//  ││││││││
//  │││││││└─ 50/60Hz filter (1 = 50Hz, 0 = 60Hz)
//  ││││││└── Fault status clear (1 = clear)
//  │││││└─── Fault detection cycle (00 = auto)
//  │││└──── 3-wire mode (0 = 4-wire, 1 = 3-wire)
//  ││└───── One-shot mode (0 = off, 1 = trigger)
//  │└────── Conversion mode (1 = auto, 0 = manual)
//  └─────── VBIAS enable (1 = on, 0 = off)

write_register(CONFIG_REG, config);

// 3. Set fault detection thresholds
write_register(HIGH_FAULT_THR_MSB, 0xFF);  // Max threshold
write_register(HIGH_FAULT_THR_LSB, 0xFF);
write_register(LOW_FAULT_THR_MSB, 0x00);   // Min threshold
write_register(LOW_FAULT_THR_LSB, 0x00);

// 4. Start conversions
// In auto-conversion mode, conversions start immediately
```

**Reading Temperature:**

```c
uint16_t read_rtd_adc() {
    // Wait for DRDY to go low (conversion ready)
    while (digitalRead(DRDY_PIN) == HIGH);

    // Read RTD data registers
    uint8_t msb = read_register(RTD_MSB);
    uint8_t lsb = read_register(RTD_LSB);

    // Check fault bit (bit 0 of LSB)
    if (lsb & 0x01) {
        // Fault detected, read fault status
        uint8_t fault = read_register(FAULT_STATUS);
        handle_fault(fault);
        return 0xFFFF;  // Invalid
    }

    // Combine MSB and LSB (15-bit value, right-aligned)
    uint16_t adc_code = ((uint16_t)msb << 7) | (lsb >> 1);
    return adc_code;
}

float calculate_temperature(uint16_t adc_code) {
    // Calculate RTD resistance
    float rtd_resistance = (adc_code * RREF) / 32768.0;

    // For PT100: R(T) = 100 × (1 + 0.00385 × T) (simplified)
    // Solving for T: T = (R - 100) / 0.385
    float temperature = (rtd_resistance - 100.0) / 0.385;

    return temperature;  // °C
}
```

**More Accurate Temperature Calculation (Callendar-Van Dusen):**

```c
// PT100 Callendar-Van Dusen coefficients
#define R0 100.0        // Resistance at 0°C
#define A  3.9083e-3    // α coefficient
#define B  -5.775e-7    // β coefficient

float rtd_to_temperature_accurate(float rtd_resistance) {
    // For 0°C to +850°C (simplified quadratic):
    // R(T) = R0 × (1 + A×T + B×T²)
    // Solving quadratic: T = (-A + sqrt(A² - 4×B×(1 - R/R0))) / (2×B)

    float ratio = rtd_resistance / R0;
    float discriminant = A*A - 4*B*(1 - ratio);

    if (discriminant < 0) return -999.9;  // Invalid

    float temperature = (-A + sqrt(discriminant)) / (2 * B);
    return temperature;
}
```

### Step 8: Fault Handling

**Fault Detection:**

The MAX31865 automatically detects:
- **RTD High Fault:** RTD resistance > high threshold
- **RTD Low Fault:** RTD resistance < low threshold
- **REFIN- > 0.85×VBIAS:** Open RTD or reference resistor issue
- **REFIN- < 0.85×VBIAS:** Shorted RTD
- **Overvoltage/Undervoltage:** Input protection triggered

**Fault Status Register (Address 0x07):**

```
Bit 7: RTD High Threshold Fault
Bit 6: RTD Low Threshold Fault
Bit 5: REFIN- > 0.85×VBIAS
Bit 4: REFIN- < 0.85×VBIAS (FORCE- open)
Bit 3: RTDIN- < 0.85×VBIAS (FORCE- open)
Bit 2: Overvoltage/Undervoltage Fault
Bit 1: Reserved
Bit 0: Reserved
```

**Example Fault Handler:**

```c
void handle_fault(uint8_t fault_status) {
    if (fault_status & 0x80) {
        // RTD too high (>400Ω for PT100 with 400Ω ref)
        printf("FAULT: RTD resistance too high (open circuit?)\n");
    }
    if (fault_status & 0x40) {
        // RTD too low (<0Ω, shouldn't happen)
        printf("FAULT: RTD resistance too low (short circuit?)\n");
    }
    if (fault_status & 0x20) {
        // REFIN- voltage too high
        printf("FAULT: Open RTD or reference resistor\n");
    }
    if (fault_status & 0x10) {
        // REFIN- voltage too low (FORCE- open)
        printf("FAULT: FORCE- connection open\n");
    }
    if (fault_status & 0x08) {
        // RTDIN- voltage too low (FORCE- open)
        printf("FAULT: RTD connection fault\n");
    }
    if (fault_status & 0x04) {
        // Overvoltage/undervoltage
        printf("FAULT: Input overvoltage (>VDD+0.1V or <-0.4V)\n");
    }
}
```

---

## SPICE Simulation Guide

### Model Overview

The provided SPICE model (`MAX31865.lib`) is a **behavioral model** that captures key functionality:

**Modeled Features:**
- Bias voltage generation (2.0V ± 3%)
- 15-bit ratiometric ADC conversion
- Input protection (±45V on RTD pins)
- Fault detection (high/low threshold, REFIN- checks)
- DRDY output (conversion ready indicator)
- Supply current consumption (VDD, DVDD)
- Input leakage currents (2-14nA typical)
- Power-on reset and UVLO

**Not Modeled:**
- Complete SPI register set and state machine
- Detailed digital filtering (sinc³ + sinc¹ filter, 50/60Hz notch detail)
- Temperature-dependent specifications
- Rise/fall times and detailed settling behavior
- Detailed fault detection cycle timing

**Use For:**
- System-level design validation
- Reference resistor selection
- RTD wiring configuration testing
- Bias voltage loading analysis
- ADC code calculation verification

**Do NOT Use For:**
- EMI/EMC analysis
- Detailed SPI timing validation
- Production testing
- Noise performance characterization

### Running the Test Circuit

**Quick Start:**

```bash
cd /Users/bennet/Desktop/components/max31865

# Run simulation
ngspice MAX31865_test.cir

# Expected output: Detailed simulation results
```

**What the Test Circuit Simulates:**

1. **Power-on sequence:** VDD/DVDD startup, bias voltage generation
2. **4-wire PT100 RTD at 25°C:** Resistance = 109.73Ω
3. **400Ω reference resistor:** Standard for PT100
4. **Ratiometric ADC conversion:** Calculates 15-bit code
5. **Temperature calculation:** Validates resistance-to-temperature formula

**Expected Results (@ 25°C):**

```
Supply Voltages:
  VDD = 3.3V
  DVDD = 3.3V

Bias Voltage:
  VBIAS = 2.0V ± 3% (1.94V to 2.06V)

Reference Resistor Voltages:
  REFIN+ = 2.0V (connected to BIAS)
  REFIN- = ~0V

RTD Voltages (PT100 @ 25°C = 109.73Ω):
  VRTD_DIFF = ~0.549V (109.73Ω × 5mA)

ADC Code:
  ADC_CODE = ~8989 (109.73/400 × 32768)

Calculated Temperature:
  T ≈ 25°C (using simplified linear formula)

Supply Currents:
  IDD (VDD) = 2-3.5mA during conversion
  IDD (DVDD) = <1mA when idle

DRDY Signal:
  0V = Data ready (active low)
  3.3V = Conversion in progress
```

### Customizing the Simulation

**Change Temperature:**

Edit line 89 in `MAX31865_test.cir`:

```spice
* Original (25°C):
B_RTD RTDIN+_NODE N_RTD_LOW R={100 + 0.385*25}

* For 100°C:
B_RTD RTDIN+_NODE N_RTD_LOW R={100 + 0.385*100}
```

**Temperature Sweep:**

Uncomment lines 268-270 in `MAX31865_test.cir`:

```spice
.step param TEMP_VAR -50 150 25
.param TEMP_VAR=25
B_RTD RTDIN+_NODE N_RTD_LOW R={100 + 0.385*TEMP_VAR}
```

This sweeps temperature from -50°C to +150°C in 25°C steps.

**Change RTD Type (PT100 → PT1000):**

```spice
* Change reference resistor (line 60):
RREF REFIN+_NODE REFIN-_NODE 4300  ; 4.3kΩ for PT1000

* Change RTD model (line 89):
B_RTD RTDIN+_NODE N_RTD_LOW R={1000 + 3.85*25}  ; PT1000 @ 25°C

* Change filter capacitor (line 112):
CRTD_FILTER RTDIN+_NODE RTDIN-_NODE 10n  ; 10nF for PT1000
```

**3-Wire Configuration:**

```spice
* Connect FORCE+ and FORCE2 together (add line after 57):
R_FORCE_FORCE2 FORCE+_NODE FORCE2_NODE 0.001

* Modify RTD connections (replace lines 93-96):
* FORCE+ cable (shared with RTDIN+)
RCABLE_FP FORCE+_NODE RTDIN+_NODE 0.1

* FORCE- and RTDIN- cables (separate)
RCABLE_FN FORCE-_NODE N_RTD_LOW 0.1
RCABLE_RN RTDIN-_NODE N_RTD_LOW 0.1

* Remove FORCE2 ground connection (delete line 124)
```

### Interpreting Results

**Valid Simulation:**
- VBIAS stabilizes at 2.0V ± 3% within 20ms
- ADC_CODE matches expected value ± 2% (accounting for model limitations)
- DRDY toggles periodically (52ms or 62.5ms period)
- Supply currents within datasheet limits

**Invalid Simulation (Troubleshooting):**
- VBIAS = 0V → Check VDD connection, power-on sequence
- ADC_CODE = 0 → Check RTD connections, FORCE pins
- ADC_CODE = 32767 → RTD resistance too high or reference too low
- DRDY stuck high → Power supply issue or configuration error

**Accuracy Note:**
The behavioral model has ±5% typical accuracy for ADC code calculations. For production designs, validate with hardware prototypes.

---

## Safety Information

### Operating Conditions

**Absolute Maximum Ratings:**

| Parameter | Min | Max | Unit |
|-----------|-----|-----|------|
| VDD | -0.3 | 4.0 | V |
| DVDD | -0.3 | 4.0 | V |
| Digital Inputs | -0.3 | DVDD+0.3 | V |
| FORCE+, FORCE2, FORCE-, RTDIN+, RTDIN- | -VDD-0.4 | VDD+45 | V |
| REFIN+, REFIN-, ISENSOR | -0.3 | VDD+0.3 | V |
| Junction Temperature | - | 150 | °C |
| Storage Temperature | -65 | 150 | °C |

**Recommended Operating Conditions:**

| Parameter | Min | Typ | Max | Unit |
|-----------|-----|-----|-----|------|
| VDD | 3.0 | 3.3 | 3.6 | V |
| DVDD | 3.0 | 3.3 | 3.6 | V |
| Ambient Temperature | -40 | 25 | 125 | °C |

### ESD Protection

**ESD Ratings (Human Body Model):**
- Digital pins (SDI, SCLK, CS, SDO, DRDY): 2kV
- RTD pins (FORCE+, FORCE2, FORCE-, RTDIN+, RTDIN-): **±8kV**

**ESD Best Practices:**
- Use ESD wrist strap when handling
- Store in anti-static packaging
- Add TVS diodes on long RTD cables (>3 meters)

### Induction Cooker Safety Considerations

#### High-Voltage Isolation

**Critical:** In induction cookers operating at 230VAC mains (325VDC rectified), the MAX31865 may be measuring RTDs on the high-voltage side (IGBT heatsinks).

**Isolation Requirements:**
1. **Galvanic Isolation:** If RTD is on high-voltage side (not referenced to ground)
   - Use isolated SPI interface (ADUM1250 or similar)
   - Maintain ≥5mm creepage distance between isolated sections
   - Provide separate isolated power supply for MAX31865

2. **Ground-Referenced RTD:** If RTD is on low-voltage side
   - MAX31865 can share ground with microcontroller
   - Standard SPI connection acceptable

**Example Isolated Configuration:**

```
High-Voltage Side (400VDC)          Low-Voltage Side (3.3V)

[PT100 RTD] → MAX31865              Microcontroller
   (IGBT)      (VDD=3.3V)           (3.3V logic)
                   │                     │
                   │ SPI                 │
                   └──[ADUM1250]─────────┘
                      (I2C Isolator
                       + SPI bridge)

[Isolated DC-DC] → 3.3V for MAX31865
```

#### Thermal Management

**MAX31865 Power Dissipation:**

```
P_MAX31865 = VDD × IDD + DVDD × IDVDD
           = 3.3V × 2.5mA + 3.3V × 0.5mA
           = 8.25mW + 1.65mW
           = ~10mW typical
```

**Thermal Resistance:**
- θJA = 155°C/W (20-pin SSOP, no airflow)
- θJC = 45°C/W (junction-to-case)

**Temperature Rise:**
```
ΔT = P × θJA = 10mW × 155°C/W = 1.55°C
```

**Maximum Ambient Calculation:**
```
T_AMBIENT_MAX = T_JUNCTION_MAX - ΔT
              = 125°C - 1.55°C
              = 123.5°C (safe margin)
```

**Induction Cooker Enclosure Temperatures:**
- Typical enclosure: 40-60°C
- Worst-case (blocked vents): 80°C
- MAX31865 junction: 80°C + 1.55°C = 81.55°C (well below 125°C limit)

**Recommendation:** No heatsink required for MAX31865 in typical induction cooker applications.

#### Fault Handling and Safety Shutdown

**Critical Temperature Thresholds:**

For IGBT thermal protection using PT100 RTD:

```c
// PT100 resistance at critical temperatures
#define TEMP_NORMAL_MAX    70   // 127.0Ω @ 70°C
#define TEMP_WARNING       85   // 132.7Ω @ 85°C
#define TEMP_CRITICAL      100  // 138.5Ω @ 100°C
#define TEMP_EMERGENCY     120  // 146.2Ω @ 120°C

// ADC thresholds (for 400Ω RREF)
#define ADC_NORMAL_MAX     10404  // (127.0/400) × 32768
#define ADC_WARNING        10881  // (132.7/400) × 32768
#define ADC_CRITICAL       11363  // (138.5/400) × 32768
#define ADC_EMERGENCY      11995  // (146.2/400) × 32768

void check_thermal_safety(uint16_t adc_code) {
    if (adc_code >= ADC_EMERGENCY) {
        // Immediate hardware shutdown (IGBT damage imminent)
        gpio_set(EMERGENCY_SHUTDOWN_PIN);
        printf("EMERGENCY: IGBT >120°C, immediate shutdown!\n");
    }
    else if (adc_code >= ADC_CRITICAL) {
        // Critical shutdown (safe shutdown sequence)
        printf("CRITICAL: IGBT >100°C, initiating shutdown\n");
        reduce_power(0);  // Cut power immediately
    }
    else if (adc_code >= ADC_WARNING) {
        // Warning: reduce power
        printf("WARNING: IGBT >85°C, reducing power to 50%%\n");
        reduce_power(50);
    }
    else if (adc_code >= ADC_NORMAL_MAX) {
        // Normal high operation: reduce power slightly
        reduce_power(80);
    }
    // Resume full power when temperature drops below 70°C with hysteresis
}
```

**Redundancy Recommendations:**
1. **Dual RTD Sensors:** Two MAX31865 measuring same IGBT
2. **Hardware Comparator:** Independent over-temperature circuit (LM311 + thermistor)
3. **Watchdog Timer:** Resets MCU if temperature monitoring stops
4. **Thermal Fuse:** Last-resort protection (soldered to IGBT heatsink, 150°C rating)

---

## Design Considerations

### Reference Resistor Selection

**Critical Parameters:**

1. **Resistance Value:**
   ```
   RREF = 4 × RTD_nominal
   ```
   - PT100: RREF = 400Ω
   - PT1000: RREF = 4.3kΩ

2. **Tolerance:**
   - ±0.1% (standard precision)
   - ±0.05% (high precision)
   - ±0.01% (ultra-precision, metrology)

3. **Temperature Coefficient (tempco):**
   - ±25 ppm/°C (standard)
   - ±10 ppm/°C (precision)
   - ±5 ppm/°C (ultra-precision)

**Temperature Error Analysis:**

For PT100 with 400Ω ±0.1% reference resistor:

```
RTD error = ±0.1% of reading
Temperature error = 0.1% / 0.385%/°C = ±0.26°C

Over 100°C temperature change:
Tempco error = 25ppm/°C × 100°C = 2500ppm = 0.25%
Temperature error = 0.25% / 0.385%/°C = ±0.65°C
```

**Total Error Budget (PT100, 4-wire):**

| Error Source | Typical | Unit |
|--------------|---------|------|
| MAX31865 ADC | ±0.05% | % of reading |
| Reference resistor tolerance | ±0.1% | % of reading |
| Reference resistor tempco | ±0.25% | % over 100°C |
| RTD tolerance (Class A) | ±0.15°C | °C @ 0°C |
| Lead resistance (4-wire) | ~0 | °C |
| **Total (RSS)** | **±0.5°C** | **°C** |

**Recommendation for Induction Cookers:**
- **Standard:** 400Ω ±0.1%, ±25ppm/°C (Vishay TNPW0805, ~$1)
- **High precision:** 400Ω ±0.05%, ±10ppm/°C (Susumu RG2012, ~$3)

### RTD Sensor Selection

**RTD Types:**

| RTD Type | R @ 0°C | Sensitivity | Cable Resistance Impact | Cost |
|----------|---------|-------------|------------------------|------|
| **PT100** | 100Ω | 0.385Ω/°C | Moderate (use 3/4-wire) | Low |
| **PT200** | 200Ω | 0.770Ω/°C | Lower (better for 2-wire) | Medium |
| **PT500** | 500Ω | 1.925Ω/°C | Low | Medium |
| **PT1000** | 1000Ω | 3.850Ω/°C | Very low (2-wire OK) | Medium |

**Accuracy Classes (IEC 60751):**

| Class | Tolerance @ 0°C | Tolerance @ 100°C | Application |
|-------|----------------|-------------------|-------------|
| **AA** | ±0.10°C | ±0.27°C | Metrology, laboratory |
| **A** | ±0.15°C | ±0.35°C | Precision industrial |
| **B** | ±0.30°C | ±0.80°C | General industrial |
| **C** | ±0.60°C | ±1.60°C | Non-critical monitoring |

**Recommendation for Induction Cookers:**
- **IGBT monitoring:** PT100 Class A (±0.35°C @ 100°C is adequate)
- **Coil monitoring:** PT100 Class B (±0.80°C acceptable)
- **Wiring:** 4-wire for IGBT (critical), 3-wire for coil (cost savings)

**Recommended Parts:**
- Omega P-M-1/10-1/4-6-0-P-3 (Class A, 3-wire, 6" leads)
- Heraeus M222 (Class A, surface mount, fast response)
- Honeywell HEL-700 (Class B, low cost)

### Cable Considerations

**Cable Resistance Impact:**

For 2-wire PT100 with 10m cable (0.1Ω/m, AWG 24):

```
R_cable_total = 2 × 10m × 0.1Ω/m = 2Ω
Temperature error = 2Ω / 0.385Ω/°C = 5.2°C error!
```

**Cable Resistance vs. Wire Gauge:**

| AWG | Ω/m | 10m 2-wire | 10m 3-wire | 10m 4-wire | Temp Error (PT100) |
|-----|-----|-----------|-----------|-----------|-------------------|
| 24 | 0.084 | 1.68Ω | 0.84Ω comp | 0Ω | 2-wire: 4.4°C |
| 22 | 0.053 | 1.06Ω | 0.53Ω comp | 0Ω | 2-wire: 2.8°C |
| 20 | 0.033 | 0.66Ω | 0.33Ω comp | 0Ω | 2-wire: 1.7°C |
| 18 | 0.021 | 0.42Ω | 0.21Ω comp | 0Ω | 2-wire: 1.1°C |

**Cable Recommendations:**

| Application | Cable Length | Wire Gauge | Configuration | Expected Error |
|-------------|-------------|------------|---------------|---------------|
| **PCB traces** | <10cm | - | 2-wire OK | <0.1°C |
| **Induction cooker internal** | <50cm | AWG 24 | 3-wire | <0.3°C |
| **Industrial short run** | 1-5m | AWG 22 | 3-wire | <0.5°C |
| **Industrial long run** | 5-20m | AWG 18-20 | 4-wire | <0.2°C |
| **Outdoor/harsh** | Any | AWG 18 | 4-wire | <0.2°C |

**Cable Specifications:**
- **Insulation:** PTFE (high temp), PVC (standard), or Silicone (flexible)
- **Temperature Rating:** ≥105°C (125°C preferred for induction cookers)
- **Shielding:** Recommended for lengths >3m (reduces EMI pickup)
- **Color Code:** Red/Black (2-wire), Red/White/Black (3-wire), Red/White/Blue/Black (4-wire)

### Noise and Filtering

**Noise Sources in Induction Cookers:**

1. **AC Line Noise:** 50/60Hz and harmonics
2. **Switching Noise:** 20-40kHz from resonant inverter
3. **EMI:** High dI/dt from IGBT switching
4. **Ground Loops:** Multiple ground paths

**MAX31865 Built-in Filtering:**

- **Digital Filter:** Sinc³ + Sinc¹ cascaded filter
- **50Hz Notch:** -120dB rejection at 50Hz (62.5ms conversion time)
- **60Hz Notch:** -120dB rejection at 60Hz (52ms conversion time)
- **Bandwidth:** ~4Hz (adequate for thermal measurements)

**External Filtering:**

**Input Filter Capacitor (required):**
```
C_filter = 10 / (2π × f_cutoff × R_RTD)
```

For PT100 (100Ω) with 10Hz cutoff:
```
C_filter = 10 / (2π × 10Hz × 100Ω) = 159nF → use 100nF standard value
```

**RC Filter Time Constant:**
```
τ = R × C = 100Ω × 100nF = 10µs
Settling time (5τ) = 50µs
```

**Power Supply Filtering:**

```
   VDD ───┬─── 10µF tantalum ──┬─── GND1
          │                    │
          ├─── 100nF X7R ──────┤
          │                    │
          └─── 10nF C0G ───────┘  (optional, for high-frequency)
```

**EMI Mitigation:**

1. **Shielded RTD Cable:** Connect shield to GND1 at MAX31865 only (avoid ground loops)
2. **Twisted Pair:** Twist RTD wires together (FORCE+/RTDIN+ and FORCE-/RTDIN-)
3. **Ferrite Beads:** Add on VDD/DVDD lines if near switching circuits
4. **PCB Layout:** Keep RTD traces away from high dI/dt power traces

---

## PCB Layout Guidelines

### Critical Layout Rules

#### 1. Component Placement

```
        [RTD Connector]
              │
         ┌────┴────┐
         │         │
      [C_filter]   │
              │    │
         ┌────▼────▼─────┐
         │   MAX31865    │
         │  (20-pin SSOP)│
         └────┬──┬──┬────┘
              │  │  │
          [RREF] │  │
              │  │  │
            [CVDD][CDVDD]
              │  │  │
         ─────┴──┴──┴───── GND Plane
```

**Placement Guidelines:**
- RREF within 10mm of MAX31865
- Filter capacitor (C_filter) within 5mm of RTDIN pins
- Bypass capacitors (CVDD, CDVDD) within 5mm of VDD/DVDD pins
- RTD connector as close as practical to MAX31865

#### 2. Reference Resistor Routing

**Critical:** Use Kelvin (4-wire) connection to RREF:

```
   BIAS ────┬──────────────┬──── REFIN+
            │              │
            │    [RREF]    │  ← Sense traces connect at resistor pads
            │     400Ω     │
            │              │
   ISENSOR ─┴──────────────┴──── REFIN-
```

**Layout Rules:**
- **Trace Width:** ≥0.3mm (10mil) for current paths, ≥0.15mm (6mil) for sense
- **Trace Length:** Match BIAS→REFIN+ and ISENSOR→REFIN- lengths (within 10%)
- **Symmetry:** Route symmetrically to cancel thermal gradients
- **Vias:** Minimize vias in current path (adds resistance)

**Bad Layout (2-wire connection to RREF):**
```
   BIAS ──────┬──────── REFIN+
              │
            [RREF]   ← Trace resistance adds error!
              │
   ISENSOR ───┴──────── REFIN-
```

#### 3. RTD Input Routing

**High-Impedance Inputs:** RTDIN+ and RTDIN- are ADC inputs (2nA leakage)

**Layout Rules:**
- **Guard Ring:** Surround RTDIN traces with grounded guard ring (prevents leakage)
- **Trace Width:** ≥0.2mm (8mil) is sufficient (low current)
- **Length Matching:** Match RTDIN+ and RTDIN- trace lengths (within 5%)
- **Separation:** Keep ≥0.5mm (20mil) from noisy signals (SPI, switching circuits)
- **Vias:** Minimize vias (parasitic capacitance)

**Guard Ring Example:**

```
Layer 1 (Top):
    GND ─────────────────────────────
        │  RTDIN+              │
        ─────────────────────────
                              │
    GND ─────────────────────────────

Layer 2 (GND Plane):
    ═════════════════════════════════
```

#### 4. Ground Plane Strategy

**MAX31865 has three ground pins:**
- **GND1 (Pin 19):** Analog ground (RTD measurements)
- **GND2 (Pin 13):** Analog ground (reference resistor)
- **DGND (Pin 18):** Digital ground (SPI interface)

**Star Ground Configuration:**

```
                 ┌─────────────────┐
                 │   MAX31865      │
                 │                 │
    RTD ─────────┤ RTDIN+   GND1├──┐
                 │ RTDIN-   GND2├──┤
                 │          DGND├──┤
  RREF ──────────┤ REFIN+        │  │
                 │ REFIN-        │  │
                 └───────────────┘  │
                                    ▼
                          ┌─────────┴─────────┐
                          │  Single GND Point │
                          │  (Star Ground)    │
                          └───────────────────┘
                                    │
                               GND Plane
```

**Layout Implementation:**

1. **Solid GND Plane:** Layer 2 (or bottom layer) full copper pour
2. **Star Point:** Connect GND1, GND2, DGND at MAX31865 via cluster
3. **Separation:** Keep analog GND traces separate from digital GND traces
4. **Single Connection:** Connect star point to main GND plane with wide trace (≥1mm)

#### 5. Power Supply Decoupling

**Bypass Capacitor Placement:**

```
Top View:
    ┌─────────────────────┐
    │      10µF           │
    │       │             │
    │  ┌────┴────┐        │
    │  │MAX31865 │ 10µF   │
    │  │ VDD DVDD│  │     │
    │  └────┬────┘ 100nF  │
    │       │      │       │
    └───────┴──────┴───────┘
            │      │
         GND Plane
```

**Layout Rules:**
- **Bulk Capacitor (10µF):** Within 10mm of VDD/DVDD pins
- **HF Capacitor (100nF):** Within 5mm of VDD/DVDD pins, shortest path to GND
- **Via Placement:** Use multiple vias (2-4) for GND connection (low inductance)
- **Trace Width:** ≥0.5mm (20mil) for VDD/DVDD power traces

**Via Stitching for Low Inductance:**

```
   VDD ──────────────────┬─── MAX31865 VDD (Pin 3)
                         │
                    ┌────▼────┐
                    │  100nF  │
                    └────┬────┘
                         │
                    ┌────▼────┐
                    │ ● ● ● ● │  ← 4 vias to GND plane
                    └─────────┘
```

#### 6. SPI Interface Routing

**Layout Rules:**
- **Trace Impedance:** Not critical (SPI ≤5MHz is low speed)
- **Trace Width:** ≥0.15mm (6mil)
- **Trace Length:** Keep <10cm for 5MHz operation
- **Termination:** Not required for short traces
- **Separation:** ≥0.3mm (12mil) from analog signals (RTDIN, REFIN)

**Series Resistor for Noise Immunity:**

```
MCU                          MAX31865
GPIO ───[33Ω]─────────────── SCLK (Pin 15)
SPI_MOSI ───[33Ω]──────────── SDI (Pin 14)
SPI_MISO ────────────────────── SDO (Pin 17)
GPIO_CS ───[33Ω]─────────────── CS (Pin 16)
```

**Benefits:**
- Limits current during ESD events
- Reduces ringing on long traces
- Prevents ground bounce coupling

#### 7. Thermal Considerations

**Copper Pour for Heat Spreading:**

- **VDD/DVDD traces:** ≥0.5mm (20mil) width
- **Thermal vias:** Under MAX31865 package (optional, helps heat transfer to bottom layer)
- **Ground plane:** Full copper pour (acts as heatsink)

**Thermal Via Array (optional, for high ambient temperatures):**

```
Top Layer (Component Side):
    ┌───────────────┐
    │  MAX31865     │
    │   (SSOP-20)   │
    └───────────────┘
          ●●●
          ●●●  ← Thermal vias (0.3mm, 3×2 array)
          ●●●

Bottom Layer:
    ═══════════════════
    Copper pour (heatsink)
```

### Example Layout (4-Wire PT100, 4-Layer PCB)

**Layer Stack-Up:**
- **Layer 1 (Top):** Signal + components
- **Layer 2:** GND plane (solid pour)
- **Layer 3:** VDD/DVDD power plane
- **Layer 4 (Bottom):** Signal (optional)

**Top Layer (Component Placement):**

```
┌─────────────────────────────────────────────────────┐
│                                                      │
│  [J1: RTD Connector]                                 │
│   │ │ │ │                                            │
│   F+ R+ R- F-                                        │
│   │ │ │ │                                            │
│   └─┴─┴─┘                                            │
│     │ [C_filter 100nF]                               │
│     │                                                 │
│  ┌──▼───────────────────┐                            │
│  │                      │  [10µF]                    │
│  │    MAX31865          │   │                        │
│  │    (SSOP-20)         │  [100nF]                   │
│  │                      │   │                        │
│  └──┬──────────┬────────┘  ─┴─ GND                   │
│     │          │                                      │
│  [RREF 400Ω]  [SPI to MCU] ──────────────────────>  │
│     │                                                 │
│  ───┴─── GND                                         │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Dimensions:**
- PCB size: ~40mm × 30mm (compact layout)
- Component height: <5mm (SSOP-20 is low profile)

### Design Rule Checklist

**Before Sending to Fabrication:**

- [ ] RREF uses Kelvin (4-wire) connection
- [ ] Filter capacitor within 5mm of RTDIN pins
- [ ] Bypass capacitors within 5mm of VDD/DVDD pins
- [ ] GND1, GND2, DGND connected at single star point
- [ ] Guard ring around RTDIN traces (optional but recommended)
- [ ] RTD traces separated ≥0.5mm from SPI traces
- [ ] Series resistors (33Ω) on SPI lines for noise immunity
- [ ] Solid GND plane on Layer 2 (no splits under MAX31865)
- [ ] Trace widths: ≥0.3mm for power, ≥0.2mm for signals
- [ ] Via stitching for bypass capacitor GND connections
- [ ] Thermal vias under MAX31865 (optional, for high ambient temp)
- [ ] Silkscreen labels for all connectors (polarity, pin names)
- [ ] Testpoints for VBIAS, REFIN+, REFIN-, RTDIN+, RTDIN- (debug)

---

## Bill of Materials

### Complete 4-Wire PT100 Temperature Measurement System

| Qty | Reference | Value | Part Number | Description | Supplier | Price (1k) |
|-----|-----------|-------|-------------|-------------|----------|-----------|
| 1 | U1 | MAX31865 | MAX31865ATP+ | RTD-to-Digital Converter, 20-pin SSOP | Mouser | $7.50 |
| 1 | R_REF | 400Ω 0.1% | TNPW0805400RBEEN | Precision resistor, 0805, ±0.1%, ±25ppm/°C | Mouser | $0.85 |
| 1 | C1 | 100nF | GRM188R71H104KA93D | Ceramic X7R, 0603, 50V, ±10% | Mouser | $0.05 |
| 1 | C2 | 10µF | GRM21BR61E106KA73L | Ceramic X7R, 0805, 25V, ±10% | Mouser | $0.15 |
| 1 | C3 | 100nF | GRM188R71H104KA93D | Ceramic X7R, 0603, 50V, ±10% (DVDD bypass) | Mouser | $0.05 |
| 1 | C4 | 10µF | GRM21BR61E106KA73L | Ceramic X7R, 0805, 25V, ±10% (DVDD bypass) | Mouser | $0.15 |
| 1 | C5 | 100nF | GRM188R71C104KA01D | Ceramic C0G, 0603, 16V, ±10% (RTD filter) | Mouser | $0.10 |
| 1 | R1-R3 | 33Ω | RC0603FR-0733RL | Series resistor, 0603, 1%, 1/10W (SPI noise immunity) | Mouser | $0.03 |
| 1 | J1 | - | 1761606-1 | 4-position terminal block, 3.5mm pitch (RTD connector) | Mouser | $0.50 |
| 1 | RTD | PT100 Class A | P-M-1/10-1/4-6-0-P-3 | PT100 RTD, 3-wire, 6" leads, ±0.15°C @ 0°C | Omega | $15.00 |
| - | - | - | - | **Total** | - | **~$24.40** |

**Notes:**
- Prices are approximate (USD, 1k quantity, 2024)
- Add PCB cost (~$2-5 for small quantity)
- Optional: SPI isolator (ADUM1250, +$3) if isolation required

### Alternative Component Options

#### Budget Option (Lower Accuracy)

| Component | Standard (±0.5°C) | Budget (±1°C) | Savings |
|-----------|-------------------|---------------|---------|
| MAX31865 | MAX31865ATP+ | Same (no alternative) | - |
| R_REF | 400Ω 0.1% ($0.85) | 400Ω 1% ($0.05) | $0.80 |
| RTD | PT100 Class A ($15) | PT100 Class B ($8) | $7.00 |
| **Total Savings** | - | - | **~$7.80** |

**Trade-off:** Accuracy degrades from ±0.5°C to ±1°C (acceptable for non-critical monitoring)

#### High-Precision Option (±0.2°C)

| Component | Standard (±0.5°C) | High-Precision (±0.2°C) | Additional Cost |
|-----------|-------------------|------------------------|-----------------|
| R_REF | 400Ω 0.1% ($0.85) | 400Ω 0.05%, ±10ppm/°C ($3.00) | +$2.15 |
| RTD | PT100 Class A ($15) | PT100 Class AA ($25) | +$10.00 |
| C_filter | C0G 100nF ($0.10) | C0G 100nF matched pair ($0.50) | +$0.40 |
| **Total Additional Cost** | - | - | **~$12.55** |

**Benefit:** Accuracy improves from ±0.5°C to ±0.2°C (metrology, laboratory applications)

### RTD Cable (Not Included in BOM)

| Application | Cable Length | Wire Gauge | Configuration | Part Number Example | Price |
|-------------|-------------|------------|---------------|---------------------|-------|
| Internal (induction cooker) | 0.5m | AWG 24 | 4-wire | Belden 9534 | $2/m |
| Industrial short run | 3m | AWG 22 | 4-wire | Belden 9534 | $2/m |
| Industrial long run | 10m | AWG 20 | 4-wire shielded | Alpha 6414 | $4/m |
| Harsh environment | Any | AWG 18 | 4-wire PTFE insulated | Omega TT-K-24S | $8/m |

**Recommendation for Induction Cooker:**
- 0.5m, AWG 24, 4-wire (IGBT monitoring)
- Red/White/Blue/Black color code for easy identification

### Optional Components

| Component | Part Number | Description | Use Case | Price |
|-----------|-------------|-------------|----------|-------|
| **SPI Isolator** | ADUM1250ARZ | I2C isolator (use with SPI bridge) | High-voltage side RTD | $3.00 |
| **TVS Diode** | SMAJ5.0A | 5V TVS, uni-directional | VDD overvoltage protection | $0.15 |
| **Ferrite Bead** | BLM18PG121SN1D | 120Ω @ 100MHz | EMI filtering on VDD | $0.05 |
| **Test Points** | 5000 | Keystone compact SMT | Debug/production test | $0.10 ea |

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: Reading 0 or 32767 (Invalid ADC Code)

**Symptom:**
- ADC code reads constant 0 or maximum value (32767)
- Temperature calculation fails

**Possible Causes:**

1. **Open RTD Connection**
   - **Check:** Measure resistance between FORCE+ and FORCE- (should be ~100Ω for PT100)
   - **Solution:** Repair cable, check terminal block connections

2. **Wrong Reference Resistor Value**
   - **Check:** Measure RREF (should be 400Ω ± 0.4Ω for 0.1% tolerance)
   - **Solution:** Replace with correct value (400Ω for PT100, 4.3kΩ for PT1000)

3. **BIAS Voltage Not Connected**
   - **Check:** Measure V(BIAS) (should be ~2.0V)
   - **Solution:** Connect BIAS to REFIN+ (required for operation)

4. **Power Supply Issue**
   - **Check:** Measure VDD and DVDD (should be 3.0-3.6V)
   - **Solution:** Fix power supply, check bypass capacitors

**Debugging Steps:**

```c
// Read fault status register
uint8_t fault = read_register(FAULT_STATUS_REG);
printf("Fault Status: 0x%02X\n", fault);

if (fault & 0x80) printf("  - RTD High Fault (open circuit?)\n");
if (fault & 0x40) printf("  - RTD Low Fault (short circuit?)\n");
if (fault & 0x20) printf("  - REFIN- > 0.85*VBIAS (open RTD/RREF?)\n");
if (fault & 0x10) printf("  - REFIN- < 0.85*VBIAS (FORCE- open?)\n");
```

#### Issue 2: Temperature Reading is Constant/Not Changing

**Symptom:**
- ADC code reads reasonable value but doesn't change with temperature
- Temperature stuck at same value

**Possible Causes:**

1. **DRDY Not Toggling (No Conversions)**
   - **Check:** Monitor DRDY pin (should toggle every 52ms/62.5ms)
   - **Solution:** Verify configuration register (VBIAS bit = 1, conversion mode enabled)

2. **Incorrect Configuration Register**
   - **Check:** Read configuration register
   - **Solution:** Write correct value:
     ```c
     uint8_t config = 0xC1;  // Auto-conversion, VBIAS on, 60Hz filter, 4-wire
     write_register(CONFIG_REG, config);
     ```

3. **SPI Communication Failure**
   - **Check:** Verify SPI clock, CS timing with oscilloscope
   - **Solution:** Check SPI mode (Mode 1 or 3), ensure CS goes low before transaction

4. **Stuck in Fault State**
   - **Check:** Read fault status register
   - **Solution:** Clear faults by writing to configuration register (Fault Clear bit)

**Debugging Steps:**

```c
// Force a new conversion (1-shot mode)
uint8_t config = read_register(CONFIG_REG);
config |= 0x20;  // Set 1-shot bit
write_register(CONFIG_REG, config);

delay_ms(65);  // Wait for conversion (62.5ms + margin)

uint16_t adc_new = read_rtd_adc();
printf("New ADC Code: %u\n", adc_new);
```

#### Issue 3: Temperature Reading is Offset (e.g., always +10°C high)

**Symptom:**
- Temperature reading is consistently offset by constant amount
- Offset doesn't change with temperature

**Possible Causes:**

1. **Lead Wire Resistance (2-Wire Configuration)**
   - **Check:** Measure resistance of RTD + cables (should be ~100Ω for PT100 only)
   - **Solution:** Switch to 3-wire or 4-wire configuration

2. **Incorrect RTD Type Setting**
   - **Check:** Verify configuration register 3-wire bit
   - **Solution:**
     - 2-wire: D5 = 0
     - 3-wire: D5 = 1
     - 4-wire: D5 = 0

3. **Reference Resistor Tolerance**
   - **Check:** Measure RREF precisely (should be 400.0Ω ± 0.4Ω)
   - **Solution:** Calibrate in software:
     ```c
     float RREF_actual = 401.2;  // Measured value
     float rtd_resistance = (adc_code * RREF_actual) / 32768.0;
     ```

4. **Self-Heating of RTD**
   - **Check:** Compare reading with known reference temperature
   - **Solution:** Reduce excitation current (not adjustable on MAX31865, but may indicate poor thermal contact)

**Calibration Procedure:**

```c
// Two-point calibration
// Point 1: Ice bath (0°C)
uint16_t adc_0C = 8192;  // Example measurement @ 0°C
float temp_0C = 0.0;

// Point 2: Boiling water (100°C at sea level)
uint16_t adc_100C = 11363;  // Example measurement @ 100°C
float temp_100C = 100.0;

// Calculate calibration coefficients
float slope = (temp_100C - temp_0C) / (adc_100C - adc_0C);
float offset = temp_0C - slope * adc_0C;

// Apply calibration
float temperature_calibrated = slope * adc_code + offset;
```

#### Issue 4: Noisy/Unstable Temperature Reading

**Symptom:**
- Temperature reading fluctuates rapidly (±1-5°C)
- ADC code jumps between values

**Possible Causes:**

1. **Missing Input Filter Capacitor**
   - **Check:** Verify 100nF capacitor across RTDIN+/RTDIN-
   - **Solution:** Add C0G or X7R ceramic capacitor close to MAX31865 pins

2. **Ground Loop / Poor Grounding**
   - **Check:** Measure GND voltage at MAX31865 vs. system GND (should be <10mV)
   - **Solution:** Use star ground configuration, connect GND1/GND2/DGND at single point

3. **EMI from Switching Circuits**
   - **Check:** Shield RTD cable, route away from power circuits
   - **Solution:**
     - Add shielded cable (connect shield to GND at MAX31865 only)
     - Add ferrite bead on VDD line
     - Increase separation from switching circuits

4. **Insufficient Bypass Capacitors**
   - **Check:** Verify 10µF + 100nF on both VDD and DVDD
   - **Solution:** Add/replace bypass capacitors within 5mm of IC pins

**Debugging Steps:**

```c
// Take multiple readings and calculate statistics
#define NUM_SAMPLES 10
uint16_t adc_samples[NUM_SAMPLES];

for (int i = 0; i < NUM_SAMPLES; i++) {
    adc_samples[i] = read_rtd_adc();
    delay_ms(100);
}

// Calculate mean and standard deviation
float mean = 0;
for (int i = 0; i < NUM_SAMPLES; i++) mean += adc_samples[i];
mean /= NUM_SAMPLES;

float std_dev = 0;
for (int i = 0; i < NUM_SAMPLES; i++) {
    float diff = adc_samples[i] - mean;
    std_dev += diff * diff;
}
std_dev = sqrt(std_dev / NUM_SAMPLES);

printf("Mean ADC: %.1f, Std Dev: %.1f\n", mean, std_dev);
printf("Noise: %.2f°C (std dev / 32 × 0.385)\n", std_dev / 32.0 * 0.385);

// If std_dev > 50, investigate noise sources
```

#### Issue 5: DRDY Always High (Never Goes Low)

**Symptom:**
- DRDY pin stuck at DVDD voltage
- No indication of conversion completion

**Possible Causes:**

1. **DVDD Not Connected**
   - **Check:** Measure DVDD (should be 3.0-3.6V)
   - **Solution:** Connect DVDD to power supply, add bypass capacitors

2. **VBIAS Not Enabled**
   - **Check:** Read configuration register, verify VBIAS bit (D7) = 1
   - **Solution:** Write 0xC1 to configuration register

3. **Conversion Mode Not Enabled**
   - **Check:** Read configuration register, verify auto-conversion bit (D6) = 1
   - **Solution:** Enable auto-conversion mode or trigger 1-shot conversions manually

4. **Fault State (Conversion Halted)**
   - **Check:** Read fault status register
   - **Solution:** Clear faults by writing configuration register with Fault Clear bit set

**Debugging Steps:**

```c
// Read and display configuration register
uint8_t config = read_register(CONFIG_REG);
printf("Config Register: 0x%02X\n", config);
printf("  VBIAS: %s\n", (config & 0x80) ? "ON" : "OFF");
printf("  Conversion Mode: %s\n", (config & 0x40) ? "AUTO" : "OFF");
printf("  1-Shot: %s\n", (config & 0x20) ? "TRIGGERED" : "OFF");
printf("  3-Wire: %s\n", (config & 0x10) ? "YES" : "NO (2-wire or 4-wire)");
printf("  Fault Detection: 0x%X\n", (config >> 2) & 0x03);
printf("  50/60Hz: %s\n", (config & 0x01) ? "50Hz" : "60Hz");

// If VBIAS or Conversion Mode is OFF, fix configuration
if (!(config & 0x80) || !(config & 0x40)) {
    config = 0xC1;  // Enable VBIAS, auto-conversion, 60Hz, 4-wire
    write_register(CONFIG_REG, config);
    printf("Configuration corrected.\n");
}
```

### Hardware Debug Checklist

**Voltage Measurements (Multimeter):**

| Node | Expected Voltage | Tolerance | Notes |
|------|-----------------|-----------|-------|
| VDD | 3.3V | ±0.3V | Analog supply |
| DVDD | 3.3V | ±0.3V | Digital supply |
| BIAS | 2.0V | ±0.06V (±3%) | Should be present after power-on |
| REFIN+ | ~2.0V | ±0.1V | Connected to BIAS |
| REFIN- | <0.1V | - | Low side of RREF, near GND |
| RTDIN+ | 0.5-1.0V | - | Depends on RTD resistance and excitation |
| RTDIN- | <0.1V | - | Typically near GND for 4-wire |

**Resistance Measurements (Multimeter, Power OFF):**

| Measurement | Expected Value | Notes |
|-------------|----------------|-------|
| RREF (REFIN+ to REFIN-) | 400Ω ± 0.4Ω | For PT100, 0.1% tolerance |
| RTD (FORCE+ to FORCE-) | ~100Ω @ 0°C | Temperature dependent (PT100) |
| RTD (RTDIN+ to RTDIN-) | Very high (>1MΩ) | High-impedance ADC inputs |

**Oscilloscope Probing:**

| Signal | Expected Waveform | Frequency | Notes |
|--------|------------------|-----------|-------|
| DRDY | Square wave, active low | ~19Hz (52ms period) or ~16Hz (62.5ms) | Toggles on conversion complete |
| SCLK | Clock bursts | Up to 5MHz | During SPI transactions |
| SDO | Data output | - | Valid when CS low, tri-state when CS high |

---

## References and Resources

### Datasheets and Application Notes

**Maxim Integrated (Analog Devices) Official Documents:**

1. **MAX31865 Datasheet**
   - Part Number: MAX31865
   - Document: 19-7245; Rev 2; 9/20
   - URL: https://www.analog.com/media/en/technical-documentation/data-sheets/MAX31865.pdf

2. **MAX31865 Evaluation Kit User Guide**
   - Part Number: MAX31865EVKIT#
   - Includes schematic, layout, test procedures
   - URL: https://www.analog.com/en/design-center/evaluation-hardware-and-software/evaluation-boards-kits/max31865evkit.html

3. **Application Note: RTD Ratiometric Measurements**
   - Tutorial on ratiometric ADC conversions
   - URL: https://www.analog.com/en/technical-articles/rtd-ratiometric-measurements.html

### RTD Sensor Information

**Standards:**

1. **IEC 60751:2008** - Industrial Platinum Resistance Thermometers and Platinum Temperature Sensors
   - Defines PT100, PT1000 specifications
   - Tolerance classes (AA, A, B, C)
   - Callendar-Van Dusen equation coefficients

2. **ASTM E1137** - Standard Specification for Industrial Platinum Resistance Thermometers

**RTD Manufacturers:**

- **Omega Engineering:** https://www.omega.com/en-us/temperature-measurement/temperature-sensors/rtd-sensors
- **Heraeus (Nexensos):** https://www.heraeus.com/en/hne/products_hne/temperature_sensing/temperature_sensing.html
- **Honeywell:** https://sps.honeywell.com/us/en/products/advanced-sensing-technologies/temperature-sensing

**Callendar-Van Dusen Coefficients (IEC 60751):**

For PT100 RTD (α = 0.00385):
```
R(T) = R₀(1 + AT + BT² + C(T-100)T³)  for T < 0°C
R(T) = R₀(1 + AT + BT²)                for T ≥ 0°C

Where:
  R₀ = 100Ω
  A = 3.9083 × 10⁻³ °C⁻¹
  B = -5.775 × 10⁻⁷ °C⁻²
  C = -4.183 × 10⁻¹² °C⁻⁴ (for T < 0°C only)
```

### Software Libraries and Example Code

**Arduino Library:**

- **Adafruit MAX31865 Library**
  - GitHub: https://github.com/adafruit/Adafruit_MAX31865
  - Includes: PT100/PT1000 support, fault detection, calibration

**Raspberry Pi Python Library:**

- **Adafruit CircuitPython MAX31865**
  - GitHub: https://github.com/adafruit/Adafruit_CircuitPython_MAX31865

**STM32 HAL Example:**

- **GitHub: MAX31865_STM32**
  - URL: https://github.com/eXtract/MAX31865_STM32
  - SPI HAL driver for STM32 microcontrollers

### Precision Resistor Manufacturers

**Reference Resistor (RREF) Sources:**

1. **Vishay Dale**
   - RN55D series (through-hole, 0.1%, 10ppm/°C)
   - TNPW series (SMD 0805, 0.1%, 25ppm/°C)
   - URL: https://www.vishay.com/resistors/

2. **Susumu**
   - RG series (SMD 0603/0805, 0.05%, 10ppm/°C)
   - URL: https://www.susumu.co.jp/english/

3. **Bourns**
   - CHV series (SMD 0805, 0.1%, 25ppm/°C)
   - URL: https://www.bourns.com/products/resistive-products

### Design Tools

**Online Calculators:**

1. **RTD Temperature to Resistance Calculator**
   - URL: https://www.omega.com/en-us/resources/rtd-calculator
   - Converts temperature ↔ resistance for PT100/PT1000

2. **MAX31865 ADC Code Calculator**
   - Custom spreadsheet (create in Excel/Google Sheets):
     ```
     ADC_CODE = (RTD_Resistance / RREF) × 32768
     Temperature = (RTD_Resistance - 100) / 0.385  (simplified)
     ```

**PCB Design Guidelines:**

- Analog Devices: "PCB Layout Guidelines for Precision Analog Components"
- URL: https://www.analog.com/en/technical-articles/pcb-layout-guidelines-for-precision-analog-components.html

### Community Resources

**Forums:**

1. **Adafruit Forums**
   - MAX31865 discussions, troubleshooting
   - URL: https://forums.adafruit.com/

2. **Arduino Forums**
   - Community projects using MAX31865
   - URL: https://forum.arduino.cc/

3. **EEVblog Forums**
   - Professional electronics design discussions
   - URL: https://www.eevblog.com/forum/

**YouTube Tutorials:**

- "MAX31865 RTD to Digital Converter - How it Works" (Andreas Spiess)
- "PT100 Temperature Measurement with MAX31865" (Adafruit)

### Additional Learning

**Books:**

1. **"Temperature Measurement" by L. Michalski et al.**
   - Comprehensive guide to RTD theory and practice
   - ISBN: 978-0-470-84413-6

2. **"Sensor Systems: Fundamentals and Applications" by Clarence W. de Silva**
   - Chapter on temperature sensors
   - ISBN: 978-1-4398-1508-6

**Online Courses:**

- **Coursera: "Measurement and Instrumentation"**
- **edX: "Temperature Sensors and Measurement Systems"**

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Dec 11, 2024 | Bennet's Claude Code Assistant | Initial comprehensive documentation release |

---

## Legal Disclaimer

This documentation and SPICE model are provided for design evaluation and educational purposes. They are NOT official Maxim Integrated / Analog Devices materials.

**IMPORTANT:**

1. **For Production Designs:**
   - Use official MAX31865 datasheet from Analog Devices
   - Validate all calculations with hardware prototypes
   - Perform thorough testing across full operating range
   - Follow applicable safety standards and regulations

2. **SPICE Model Limitations:**
   - Behavioral model for system-level simulation only
   - Not suitable for production testing or validation
   - Results may differ from actual hardware (±5% typical)
   - Contact Analog Devices for official SPICE models

3. **Safety:**
   - RTD sensors may be exposed to high temperatures (>200°C)
   - Ensure proper insulation and cable ratings
   - In high-voltage applications (induction cookers), provide galvanic isolation
   - Follow IEC 60335-2-6 and local electrical safety codes

4. **Liability:**
   - Use this information at your own risk
   - Author assumes no liability for errors, omissions, or damages
   - Consult qualified engineers for production designs

**For Technical Support:**
- Analog Devices: https://www.analog.com/en/support.html
- MAX31865 Product Page: https://www.analog.com/en/products/max31865.html

---

**End of Documentation**
