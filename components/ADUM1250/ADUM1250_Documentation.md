# ADUM1250/ADUM1251 I2C Isolator - Comprehensive Documentation

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
The **ADUM1250** and **ADUM1251** are hot-swappable dual I2C isolators from Analog Devices that provide bidirectional I2C communication across a galvanic isolation barrier. Using Analog Devices' iCoupler® magnetic isolation technology, these devices eliminate the need for optocouplers while providing superior performance and reliability.

### Key Features

| Feature | Specification |
|---------|--------------|
| **Isolation Rating** | 2500 V<sub>RMS</sub> (UL 1577), 560 V peak working voltage |
| **Channels** | ADUM1250: 2 bidirectional<br>ADUM1251: 1 bidirectional + 1 unidirectional |
| **Supply Voltage** | 3.0 V to 5.5 V (both sides, independent) |
| **Maximum Data Rate** | 1000 kHz (1 MHz) |
| **Propagation Delay** | Side 1→2: 82 ns typ (25°C)<br>Side 2→1: 310 ns typ (25°C) |
| **Supply Current** | Side 1: 1.7 mA typ @ 3.3 V<br>Side 2: 2.1 mA typ @ 3.3 V |
| **Output Drive** | Side 1: 3 mA sink<br>Side 2: 30 mA sink |
| **Package** | 8-lead SOIC |
| **Temperature Range** | -40°C to +105°C |
| **CMTI** | 25 kV/μs (typ) common-mode transient immunity |
| **Hot Swap** | Glitch-free startup with proper sequencing |

### Technology: iCoupler Magnetic Isolation

Unlike traditional optocouplers, the ADUM1250/1251 use:
- **Chip-scale transformers** for signal coupling
- **On-chip refresh circuits** to support DC and low-frequency signals
- **No LED degradation** over time (unlike optocouplers)
- **Higher speed** and lower propagation delays than optocouplers
- **Lower power consumption** than discrete isolation solutions

### Pin Configuration (8-lead SOIC)

```
     ┌─────────┐
VDD1 │1      8│ VDD2
SCL1 │2      7│ SCL2
SDA1 │3      6│ SDA2
GND1 │4      5│ GND2
     └─────────┘
```

**Pin Descriptions:**
- **Pin 1 (VDD1):** Supply voltage for Side 1 (3.0 V to 5.5 V)
- **Pin 2 (SCL1):** I2C clock, Side 1 (bidirectional, open-drain)
- **Pin 3 (SDA1):** I2C data, Side 1 (bidirectional or input only for ADUM1251)
- **Pin 4 (GND1):** Ground for Side 1
- **Pin 5 (GND2):** Ground for Side 2
- **Pin 6 (SDA2):** I2C data, Side 2 (bidirectional, open-drain)
- **Pin 7 (SCL2):** I2C clock, Side 2 (bidirectional, open-drain)
- **Pin 8 (VDD2):** Supply voltage for Side 2 (3.0 V to 5.5 V)

### ADUM1250 vs ADUM1251

| Feature | ADUM1250 | ADUM1251 |
|---------|----------|----------|
| SCL Channel | Bidirectional | Bidirectional |
| SDA Channel | Bidirectional | **Unidirectional** (Side 1 → Side 2 only) |
| Use Case | Standard I2C with multi-master | Simple master-slave with no clock stretching on SDA |
| Applications | Full I2C protocol support | Read-only sensors, simplified protocols |

**When to use ADUM1251:**
- Single master, single slave configuration
- Slave device doesn't use SDA for clock stretching
- Cost optimization (slightly lower cost than ADUM1250)
- Simplified routing (one less return path)

---

## Role in Induction Cooker

### System Architecture

In an induction cooker, the ADUM1250/1251 provides **critical safety isolation** between:

1. **Low-voltage side (Side 1):**
   - Microcontroller (3.3 V or 5 V logic)
   - User interface (buttons, display, touch panel)
   - Low-voltage control circuits
   - USB or external communication interfaces

2. **High-voltage side (Side 2):**
   - Temperature sensors monitoring IGBTs, heatsinks, or induction coil
   - Power monitoring ICs (voltage, current, power factor)
   - Gate driver configuration ICs
   - EEPROM for calibration data on isolated side
   - Digital potentiometers for power control
   - Fan controllers (if on high-voltage side)

### Typical Induction Cooker Block Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                       INDUCTION COOKER SYSTEM                      │
└────────────────────────────────────────────────────────────────────┘

LOW-VOLTAGE SIDE (Side 1)          │          HIGH-VOLTAGE SIDE (Side 2)
                                   │
┌──────────────────┐               │         ┌─────────────────────┐
│                  │   I2C         │   I2C   │  Temperature        │
│  Microcontroller ├───SCL1────────┼────SCL2─┤  Sensor (LM75, etc) │
│   (3.3V/5V)      │               │         │  Address: 0x48      │
│                  ├───SDA1────┐   │   ┌─SDA2┤                     │
└──────────────────┘            │   │   │     └─────────────────────┘
        │                    ┌──┴───┴───┴──┐
        │                    │  ADUM1250   │  ← 2500V RMS ISOLATION
        │                    │  I2C        │
        │                    │  Isolator   │
        │                    └──┬───┬───┬──┘
        │                       │   │   │     ┌─────────────────────┐
┌──────────────────┐            │   │   └─SDA2┤  Power Monitor IC   │
│  User Interface  │            │   │         │  (INA226, etc)      │
│  - Display       │            │   │         │  Address: 0x40      │
│  - Buttons       │            │   └────SCL2─┤                     │
│  - LEDs          │            │             └─────────────────────┘
└──────────────────┘            │
                                │             ┌─────────────────────┐
┌──────────────────┐            │             │  Gate Driver        │
│  Isolated        ├────────────┼─────────────┤  (UCC21550)         │
│  Gate Driver     │   PWM      │    PWM      │                     │
│  (Input Side)    │  Control   │  Control    │  Drives IGBTs       │
└──────────────────┘            │             └─────────────────────┘
                                │
        GND1                    │                    GND2
         ⏚                      │                     ⏚
                            ISOLATION
                             BARRIER
                         (2500V RMS)
```

### Why I2C Isolation is Critical

1. **Safety:**
   - **Prevents electric shock:** Isolates user-accessible controls from AC mains
   - **Meets regulatory requirements:** IEC 60335-2-6, UL 858 for household appliances
   - **Protects users:** Even if high-voltage side fails, isolation prevents dangerous voltages reaching user interface

2. **Ground Loop Elimination:**
   - High-voltage power electronics and low-voltage control often have different ground potentials
   - Without isolation, ground loops can cause:
     - **Measurement errors** in temperature and power monitoring
     - **Noise injection** into microcontroller ADC and digital circuits
     - **Latch-up or damage** to microcontroller
   - ADUM1250 breaks ground loops while maintaining I2C communication

3. **Common-Mode Noise Rejection:**
   - IGBT switching (20-100 kHz) creates large common-mode voltage transients
   - ADUM1250 CMTI (25 kV/μs) rejects these transients
   - Prevents false triggering or data corruption on I2C bus

4. **Surge Protection:**
   - AC mains can experience voltage surges (lightning, grid switching)
   - 2500 V<sub>RMS</sub> isolation protects low-voltage circuits
   - Meets UL 1577 isolation standards

### Common I2C Devices on Isolated Side

| Device Type | Example Part | I2C Address | Purpose in Induction Cooker |
|-------------|--------------|-------------|----------------------------|
| **Temperature Sensor** | LM75, TMP100, PCT2075 | 0x48-0x4F | Monitor IGBT temperature for thermal protection |
| **Temperature Sensor** | TMP117, MCP9808 | 0x48-0x4F | Monitor heatsink or coil temperature |
| **Power Monitor** | INA226, INA219 | 0x40-0x4F | Measure DC bus voltage and current |
| **ADC** | ADS1015, ADS1115 | 0x48-0x4B | Read analog signals (AC voltage, current sense) |
| **EEPROM** | 24LC64, AT24C256 | 0x50-0x57 | Store calibration data, power curves |
| **Digital Pot** | MCP4451, AD5252 | 0x2C-0x2F | Adjust gate driver strength or timing |
| **GPIO Expander** | MCP23008, PCF8574 | 0x20-0x27 | Read isolated switches or drive LEDs |
| **Fan Controller** | EMC2101, MAX6650 | 0x4C-0x4F | Control cooling fan speed based on temperature |

### Typical Application: Temperature Monitoring

**Scenario:** Monitor IGBT junction temperature to prevent thermal runaway.

1. **Hardware:**
   - LM75 temperature sensor mounted on IGBT heatsink (high-voltage side)
   - ADUM1250 isolates I2C between microcontroller and LM75
   - Pull-up resistors on both sides of isolation barrier

2. **Operation:**
   - Microcontroller reads temperature every 100 ms
   - If temperature exceeds 100°C: reduce power
   - If temperature exceeds 125°C: shut down inverter
   - If temperature exceeds 150°C: latch fault and disable

3. **Safety:**
   - Even if IGBT fails short and heatsink becomes energized at AC mains voltage
   - ADUM1250 maintains 2500 V isolation
   - Microcontroller and user interface remain safe

---

## How to Use This Chip

### Step 1: Power Supply Design

Both sides of the ADUM1250 require independent power supplies in the range of 3.0 V to 5.5 V.

#### Side 1 (Microcontroller Side)

**Typical supply:** 3.3 V or 5 V from microcontroller's LDO or switching regulator

**Bypassing requirements:**
```
VDD1 ───┬───[0.1 μF]───┬─── GND1
        └───[10 μF]────┘
```

- **0.1 μF ceramic capacitor:** Place within 5 mm of VDD1 pin (X7R or X5R, 10 V rated)
- **10 μF bulk capacitor:** Electrolytic or ceramic, within 20 mm of VDD1 pin
- **Low ESR:** Use quality ceramic capacitors for high-frequency decoupling

#### Side 2 (Isolated Side)

**Typical supply options:**
1. **Isolated DC-DC converter:** Use if Side 2 devices need significant current
   - Example: TMR 1-0511 (5V, 200 mA, 1 kV isolation)
   - Example: MEE1S0505SC (5V, 200 mA, 1.5 kV isolation)
2. **Isolated flyback from high-voltage side:** If induction cooker already has isolated auxiliary supply
3. **Shared with gate driver isolated supply:** If gate driver has spare current capacity

**Bypassing requirements:**
```
VDD2 ───┬───[0.1 μF]───┬─── GND2
        └───[10 μF]────┘
```

- Same requirements as Side 1
- **Critical:** Keep Side 2 bypass capacitors on isolated side of creepage gaps

#### Hot Swap Sequencing

The ADUM1250/1251 includes hot swap circuitry to prevent I2C bus glitching during power-up.

**Requirements:**
1. **Both VDD1 and VDD2 must exceed 2.5 V** before outputs become active
2. **40 μs delay** after both supplies cross 2.0 V threshold
3. **No specific power-up order required** (can power up in any sequence)

**Best practice:**
- Use microcontroller power-on reset to delay I2C communication for ~100 ms after power-up
- This allows ADUM1250 hot swap circuit to stabilize
- Prevents false starts or corrupted first transaction

### Step 2: Pull-Up Resistor Selection

The ADUM1250/1251 have **open-drain outputs** requiring external pull-up resistors on both sides.

#### Pull-Up Resistor Calculation

**Formula:**
```
R_pullup_min = (VDD - VOL_max) / IOL_max

R_pullup_max = t_rise / (0.8473 × C_bus)
```

Where:
- `VDD`: Supply voltage (3.3 V or 5 V)
- `VOL_max`: Maximum output low voltage (0.4 V for Side 2, 0.9 V for Side 1)
- `IOL_max`: Maximum current sink capability (30 mA for Side 2, 3 mA for Side 1)
- `t_rise`: Maximum rise time per I2C spec (1000 ns for 100 kHz, 300 ns for 400 kHz)
- `C_bus`: Total bus capacitance (ADUM1250 + traces + slave devices)

#### Recommended Values by I2C Speed

| I2C Speed | Side 1 Pull-Up | Side 2 Pull-Up | Notes |
|-----------|----------------|----------------|-------|
| **100 kHz (Standard)** | 4.7 kΩ | 4.7 kΩ | Most common, works with most devices |
| **400 kHz (Fast)** | 2.2 kΩ | 2.2 kΩ | Check Side 1 current (1.5 mA @ 3.3V) |
| **1 MHz (Fast-Plus)** | Not recommended | 1.0 kΩ to 2.2 kΩ | Use Side 2 only, short traces |

**Side 1 limitation:** 3 mA sink capability limits minimum pull-up resistor
- At 3.3 V: R_min = (3.3 - 0.9) / 0.003 = 800 Ω
- **Practical minimum: 1 kΩ** (leaves margin)
- For 1 MHz I2C, use **Side 2 as master** (30 mA sink supports lower pull-ups)

**Side 2:** 30 mA sink allows lower pull-up resistors for faster rise times

#### Example Calculation

**Target:** 100 kHz I2C, 3.3 V supply, 150 pF bus capacitance

**Minimum pull-up (current limit):**
```
Side 2: R_min = (3.3 - 0.4) / 0.030 = 97 Ω  → Use much higher for proper I2C operation
Side 1: R_min = (3.3 - 0.9) / 0.003 = 800 Ω
```

**Maximum pull-up (rise time limit):**
```
t_rise = 1000 ns (for 100 kHz)
R_max = 1000n / (0.8473 × 150p) = 7.86 kΩ
```

**Selected value:** 4.7 kΩ (within 800 Ω to 7.86 kΩ range, standard value)

#### Schematic Example

```
  VDD1 (3.3V)           VDD2 (3.3V or 5V)
    │                       │
   ┌┴┐                     ┌┴┐
   │ │ 4.7kΩ               │ │ 4.7kΩ
   │ │                     │ │
   └┬┘                     └┬┘
    │                       │
    ├───SCL1    SCL2───────┤
    │       │   │          │
    │    ┌──┴───┴──┐       │
    │    │ ADUM1250│       │    To I2C
    │    │         │       │    devices
    │    └──┬───┬──┘       │
    │       │   │          │
    ├───SDA1    SDA2───────┤
    │                       │
   ┌┴┐                     ┌┴┐
   │ │ 4.7kΩ               │ │ 4.7kΩ
   │ │                     │ │
   └┬┘                     └┬┘
    │                       │
   GND1                    GND2
```

### Step 3: I2C Master Configuration (Microcontroller)

Configure your microcontroller's I2C peripheral considering the **asymmetric propagation delays** of the ADUM1250.

#### Propagation Delay Impact

| Direction | Typical Delay | Impact |
|-----------|---------------|--------|
| Side 1 → Side 2 | 95 ns @ 25°C | Master transmit: minimal impact |
| Side 2 → Side 1 | 325 ns @ 25°C | Slave ACK/data: may affect timing |

**Total round-trip delay:** ~420 ns

At 100 kHz (10 μs bit time), 420 ns delay is 4.2% of bit time — **negligible**.
At 400 kHz (2.5 μs bit time), 420 ns delay is 16.8% of bit time — **may require timing adjustment**.
At 1 MHz (1 μs bit time), 420 ns delay is 42% of bit time — **requires careful timing**.

#### Recommended I2C Timing Parameters

**For 100 kHz (Standard Mode):**
```c
// Example: STM32 HAL configuration
hi2c1.Init.Timing = 0x00201D2B;  // 100 kHz @ 8 MHz I2C clock
hi2c1.Init.ClockSpeed = 100000;
hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
```

**For 400 kHz (Fast Mode):**
```c
// Add extra margin to setup/hold times due to asymmetric delays
hi2c1.Init.Timing = 0x00300619;  // 400 kHz with relaxed timing
hi2c1.Init.ClockSpeed = 400000;
```

**General guidelines:**
1. **Increase SCL rise time allowance** by at least 500 ns for isolated I2C
2. **Increase setup time (t_SU:DAT)** by 400 ns to account for Side 2→1 delay
3. **Use longer hold time (t_HD:DAT)** for robust operation
4. **Avoid clock stretching timing limits** close to minimum spec

### Step 4: Slave Device Configuration

Connect standard I2C devices to Side 2 (isolated side).

**Key points:**
- Side 2 is **fully I2C compliant** (standard VIL/VIH levels)
- Side 1 has **modified logic levels** (500-700 mV threshold) — do not connect standard I2C devices to Side 1
- Use standard I2C slave devices on Side 2 without modification

**Example:** LM75 temperature sensor
```
  VDD2 (3.3V to 5.5V)
    │
    ├───────┐
    │       │
  ┌─┴───────┴─┐
  │   LM75    │
  │ Temp      │
  │ Sensor    │
  └─┬───┬─┬─┬─┘
    │   │ │ │
   SCL SDA│ A0-A2 (address pins)
    │   │ │
    │   │ └── GND2 (set address to 0x48)
    │   │
   To ADUM1250 Side 2
```

### Step 5: Layout Considerations (See detailed section below)

**Quick checklist:**
- [ ] Maintain >4 mm creepage and >0.4 mm clearance between Side 1 and Side 2
- [ ] Keep all Side 1 and Side 2 ground planes separated
- [ ] Place bypass capacitors within 5 mm of VDD1/VDD2 pins
- [ ] Use short, direct traces for SCL and SDA
- [ ] Add test points for debugging both sides independently
- [ ] Keep high-voltage AC traces away from ADUM1250

---

## SPICE Simulation Guide

The provided SPICE model (`ADUM1250.lib`) and test circuit (`ADUM1250_test.cir`) allow you to simulate I2C isolation behavior before building hardware.

### Model Features and Limitations

#### What IS Modeled

✅ **Bidirectional signal propagation** through isolation barrier
✅ **Asymmetric propagation delays** (Side 1→2: 95 ns, Side 2→1: 325 ns)
✅ **Open-drain outputs** requiring external pull-up resistors
✅ **Different logic levels** on Side 1 vs Side 2
✅ **Hot swap startup** sequencing (40 μs delay after power valid)
✅ **Supply current consumption** (~1.7 mA Side 1, ~2.1 mA Side 2)
✅ **Power-on reset** behavior
✅ **Input thresholds** (600 mV Side 1, 0.3/0.7×VDD Side 2)
✅ **Output low voltages** (750 mV Side 1, 400 mV Side 2)
✅ **Current sink limits** (3 mA Side 1, 30 mA Side 2)

#### What is NOT Modeled

❌ **Rise/fall time temperature coefficients** (modeled at 25°C only)
❌ **Common-mode transient immunity (CMTI)** effects
❌ **Detailed glitch suppression** during hot swap
❌ **Isolation barrier capacitance** and coupling
❌ **Electromagnetic interference (EMI)** from switching
❌ **Long-term drift** or aging effects
❌ **ESD protection structures**

### Running the Simulation

#### Prerequisites

Install ngspice (open-source SPICE simulator):
```bash
# macOS
brew install ngspice

# Ubuntu/Debian
sudo apt-get install ngspice

# Windows
# Download from: http://ngspice.sourceforge.net/download.html
```

#### Basic Simulation

```bash
cd /Users/bennet/Desktop/components/ADUM1250
ngspice ADUM1250_test.cir
```

The simulation will:
1. Run 500 μs transient analysis
2. Generate plots of SCL1, SDA1, SCL2, SDA2 waveforms
3. Measure propagation delays in both directions
4. Measure supply currents
5. Validate logic levels and timing
6. Print comprehensive results to terminal

#### Expected Results

When the simulation completes, you should see:

```
===== ADUM1250 I2C Isolator Test Results =====

Supply Currents (should be ~1.7mA and ~2.1mA respectively):
i_dd1_avg = 1.700e-03
i_dd2_avg = 2.100e-03

SCL Propagation Delay (Side 1 to Side 2, should be ~95ns):
prop_delay_scl_1to2 = 9.500e-08

SDA Propagation Delay (Side 1 to Side 2, should be ~95ns):
prop_delay_sda_1to2 = 9.500e-08

SDA Propagation Delay (Side 2 to Side 1, should be ~325ns):
prop_delay_sda_2to1 = 3.250e-07

Side 1 Logic Levels:
v_scl1_low = 7.500e-01
v_scl1_high = 3.300e+00
v_sda1_low = 7.500e-01

Side 2 Logic Levels:
v_scl2_low = 4.000e-01
v_scl2_high = 5.000e+00
v_sda2_low = 4.000e-01

===== Validation Status =====
✓ Side 1 to Side 2 propagation delay within spec
✓ Side 2 to Side 1 propagation delay within spec
✓ Supply currents within spec
✓ Logic levels within spec
```

### Validation Checklist

Use this checklist to verify the SPICE model produces realistic results:

#### Timing Validation

- [ ] **Side 1→2 propagation delay: 50-200 ns range**
  - Typical: 82-115 ns depending on temperature
  - Model uses: 95 ns nominal

- [ ] **Side 2→1 propagation delay: 200-500 ns range**
  - Typical: 310-340 ns depending on temperature
  - Model uses: 325 ns nominal

- [ ] **Asymmetry ratio: ~3:1 to 4:1**
  - Side 2→1 should be ~3.4× slower than Side 1→2
  - This is normal behavior, not a bug

#### Logic Level Validation

- [ ] **Side 1 output low: 600-900 mV @ 3 mA sink**
  - Model uses: 750 mV typical

- [ ] **Side 2 output low: <400 mV @ 3 mA sink**
  - Model uses: 400 mV max

- [ ] **Side 1 input threshold: 500-700 mV**
  - Model uses: 600 mV with 100 mV hysteresis

- [ ] **Side 2 input threshold: 0.3-0.7 × VDD2**
  - Standard I2C levels

#### Supply Current Validation

- [ ] **Side 1 current: 1.5-2.5 mA range**
  - Typical: 1.7 mA @ 3.3 V, 2.3 mA @ 5 V

- [ ] **Side 2 current: 1.9-3.0 mA range**
  - Typical: 2.1 mA @ 3.3 V, 2.8 mA @ 5 V

- [ ] **Total power: <15 mW @ 3.3 V both sides**
  - Typical: ~12.5 mW total

#### Functional Validation

- [ ] **I2C START condition propagates** from Side 1 to Side 2
- [ ] **I2C data bits propagate** correctly in both directions
- [ ] **I2C ACK from slave** propagates back from Side 2 to Side 1
- [ ] **No glitches during hot swap** startup sequence
- [ ] **Both supplies must be >2.5 V** before outputs activate

### Modifying the Test Circuit

#### Change I2C Speed to 400 kHz

Edit `ADUM1250_test.cir`:

```spice
* Change pull-up resistors from 4.7kΩ to 2.2kΩ
R_PU_SCL1 VDD1 SCL1 2.2k   ; was 4.7k
R_PU_SDA1 VDD1 SDA1 2.2k   ; was 4.7k
R_PU_SCL2 VDD2 SCL2 2.2k   ; was 4.7k
R_PU_SDA2 VDD2 SDA2 2.2k   ; was 4.7k

* Change I2C bit time from 10us to 2.5us
* Adjust all timing in B_SCL1_CTRL and B_SDA1_CTRL behavioral sources
```

#### Add More I2C Slave Devices

```spice
* Add second slave at address 0x50 (EEPROM)
* Pull-up resistors are shared (already present)

* Slave 2 SDA control (ACK at different clock cycles)
B_SDA2_SLAVE2_CTRL N_SDA2_SLAVE2_CTRL 0 V={
+ IF(TIME > 178u & TIME < 188u, 0, 1)
+}
S_SDA2_SLAVE2 SDA2 0 N_SDA2_SLAVE2_CTRL 0 SDA2_SLAVE_SW
```

#### Test Different Supply Voltages

```spice
* Change Side 1 to 5V, Side 2 to 3.3V
VDD1 VDD1 0 DC 5.0    ; was 3.3
VDD2 VDD2 0 DC 3.3    ; was 5.0

* Adjust initial conditions
.ic V(SCL1)=5.0 V(SDA1)=5.0 V(SCL2)=3.3 V(SDA2)=3.3
```

### Integration with Full Induction Cooker Simulation

To simulate the ADUM1250 together with UCC21550 gate driver and IKW40N120H3 IGBT:

```spice
* Combined induction cooker simulation
.title Complete Induction Cooker with I2C Temperature Monitoring

.include ../UCC21550/UCC21550.lib
.include ../IKW40N120H3/IKW40N120H3.lib
.include ADUM1250.lib

* (UCC21550 and IKW40N120H3 power circuit here)

* I2C temperature sensor on isolated side
XISO VDD1 SCL1 SDA1 0 0 SDA2 SCL2 VDD2 ADUM1250

* Simplified temperature sensor model
* Reads IGBT junction temperature and reports via I2C
* (Use behavioral model to convert V(IGBT_TEMP) to I2C response)
```

---

## Safety Information

### Isolation Specifications

The ADUM1250/1251 provides robust isolation suitable for induction cooker applications:

| Parameter | Value | Standard | Notes |
|-----------|-------|----------|-------|
| **RMS Isolation Voltage** | 2500 V | UL 1577 | 1 minute test |
| **Peak Working Voltage** | 560 V | IEC 60747-17 (VDE 0884-17) | Continuous |
| **Surge Isolation Voltage** | 6000 V | IEC 60747-5-5 | 1.2/50 μs surge |
| **Partial Discharge** | <5 pC @ 560 V<sub>PK</sub> | IEC 60664-1 | Qual level III |
| **Installation Category** | II | IEC 60664-1 | Household appliances |
| **Pollution Degree** | 2 | IEC 60664-1 | Normal indoor |

### Regulatory Compliance

✅ **UL 1577:** Component recognition for galvanic isolation
✅ **IEC 60747-17 (VDE 0884-17):** Digital isolator standard
✅ **IEC 60335-2-6:** Safety of household cooking appliances
✅ **UL 858:** Standard for household electric ranges
✅ **RoHS compliant:** Lead-free, halogen-free options available

### Creepage and Clearance Requirements

To maintain 2500 V<sub>RMS</sub> isolation, observe minimum spacing on PCB:

| Measurement | Minimum Value | Recommended |
|-------------|---------------|-------------|
| **Creepage** | 4.0 mm | 5.0 mm |
| **Clearance** | 0.4 mm | 0.8 mm |
| **PCB Material** | FR-4, CTI ≥ 175 | FR-4, CTI ≥ 250 |

**Definitions:**
- **Creepage:** Shortest path along PCB surface between isolated conductors
- **Clearance:** Shortest direct air gap between isolated conductors
- **CTI (Comparative Tracking Index):** Measure of insulation resistance to tracking

### Ground Plane Separation

```
     Side 1 Ground             Side 2 Ground
         Plane                     Plane
    ┌────────────┐            ┌────────────┐
    │            │            │            │
    │   GND1     │            │   GND2     │
    │            │            │            │
    └────────────┘            └────────────┘
          ▲                         ▲
          │                         │
          │◄────── ≥4.0 mm ────────►│
          │    (5.0 mm recommended) │
          │                         │
        Creepage Gap
     (no copper, no traces,
      no vias, no silkscreen)
```

**Critical rules:**
1. **No ground pour** in isolation gap area
2. **No signal traces** crossing gap (except through ADUM1250 pins)
3. **No mounting holes or vias** in gap area
4. **Silkscreen indication** of isolation boundary for assembly reference

### Maximum Transient Overvoltage

**Common-Mode Transient Immunity (CMTI):** 25-35 kV/μs

This protects against:
- IGBT switching transients (dV/dt)
- ESD events
- Fast mains transients

**However**, CMTI does NOT protect against:
- Sustained overvoltages exceeding 560 V<sub>PK</sub>
- Lightning direct strikes (use additional surge protection)
- Long-duration mains surges (use MOVs or TVS diodes)

### Additional Protection (Recommended)

For robust operation in induction cookers, add:

1. **TVS diodes on Side 2 supply:**
   ```
   VDD2 ──┬──────
          │
         ─┴─ SMAJ5.0A (5V TVS diode)
         ─┬─
          │
         GND2
   ```

2. **MOV (Metal Oxide Varistor) on AC input:**
   - Clamps mains surges before they reach DC bus
   - Prevents overvoltage on Side 2 high-voltage circuitry

3. **Fuse on Side 2 supply:**
   - Protects against short circuits on isolated side
   - Prevents damage to ADUM1250 if Side 2 supply fails

### Safe Working Conditions

| Parameter | Condition |
|-----------|-----------|
| **Operating temperature** | -40°C to +105°C ambient |
| **Storage temperature** | -65°C to +150°C |
| **Maximum humidity** | 85% RH non-condensing |
| **Altitude** | Up to 2000 m (higher altitude requires derating) |

**Derating:**
- Above 2000 m altitude: reduce working voltage by 10% per 1000 m
- Above 70°C: ensure adequate airflow and thermal management

### Failure Modes and FMEA

Understanding failure modes is critical for safety-critical designs:

| Failure Mode | Probability | Effect | Mitigation |
|--------------|-------------|--------|------------|
| **Open circuit on one channel** | Low | I2C communication fails, safe state | Monitor I2C timeouts, implement watchdog |
| **Short circuit input-output (same side)** | Very Low | Channel fails, isolation maintained | Use redundant sensors or fail-safe logic |
| **Isolation breakdown** | Extremely Low | Loss of isolation barrier | Design for fail-safe: use current limiting, fuses |
| **Supply overvoltage** | Low (if unprotected) | Potential device damage | Add TVS diodes and LDO regulators |

**Key safety principle:** Design system to fail safe
- Loss of I2C communication → shut down inverter
- Temperature sensor failure → assume overtemperature, reduce power
- Isolation failure → current limiting and fuses prevent hazard

### Periodic Testing and Maintenance

For commercial induction cookers, consider:

1. **Production testing:**
   - Hi-pot test at 3000 V (verify isolation)
   - Functional I2C test at operating temperature
   - Visual inspection of creepage/clearance

2. **Field maintenance:**
   - ADUM1250 does not degrade over time (unlike optocouplers)
   - No periodic replacement needed
   - Inspect for physical damage (cracks, contamination)

---

## Design Considerations

### Bidirectional Communication Details

Unlike simple unidirectional isolators, the ADUM1250 supports full bidirectional I2C, including:

✅ **Clock stretching** (slave holds SCL low)
✅ **Multi-master arbitration** (multiple devices can be bus masters)
✅ **General call addressing** (0x00 address)
✅ **10-bit addressing** (extended address range)
✅ **Repeated START** conditions
✅ **ACK/NACK** from slave devices

**ADUM1251 limitation:** Unidirectional SDA channel does NOT support:
❌ Clock stretching on SDA line
❌ Slave transmission (read operations) — **only master reads are possible**

### Logic Level Differences (Side 1 vs Side 2)

**Side 1 (Modified Levels):**
- Input threshold: 500-700 mV (600 mV typical)
- Output low: 600-900 mV @ 3 mA (750 mV typical)
- **Not standard I2C compliant**
- Allows lower voltage operation and reduced power

**Side 2 (Standard I2C Levels):**
- Input low (VIL): < 0.3 × VDD2
- Input high (VIH): > 0.7 × VDD2
- Output low (VOL): < 0.4 V @ 3 mA
- **Fully I2C compliant**

**Why the difference?**
- Side 1 optimized for low power and compatibility with iCoupler receiver
- Side 2 designed for standard I2C slave devices
- Isolation barrier between sides allows different signaling levels

**Design rule:** Always connect standard I2C devices to Side 2 only.

### Bus Capacitance Considerations

I2C specification limits bus capacitance to 400 pF, but ADUM1250 adds capacitance:

| Component | Capacitance |
|-----------|-------------|
| ADUM1250 input (per pin) | ~10 pF (estimated) |
| PCB trace (per cm) | ~2-3 pF |
| I2C slave device (typical) | 10-20 pF |
| Pull-up resistor parasitic | <5 pF |

**Example calculation:**
```
Total Side 2 capacitance:
- ADUM1250 input: 10 pF
- 5 cm PCB trace: 15 pF
- LM75 sensor: 15 pF
- INA226 monitor: 15 pF
Total: 55 pF (well within 400 pF limit)
```

**Recommendations:**
- Keep traces short (<10 cm per side)
- Limit number of devices on isolated side (max 4-5 devices)
- Use lower pull-up resistors if capacitance is high
- Measure actual capacitance during prototyping

### Temperature Effects

**Propagation delay vs temperature:**

| Temperature | Side 1→2 Delay | Side 2→1 Delay |
|-------------|----------------|----------------|
| 25°C | 82 ns | 310 ns |
| 85°C | 100 ns | 325 ns |
| 125°C | 115 ns | 340 ns |

**Impact:** Delays increase ~40% from 25°C to 125°C

**Supply current vs temperature:**
- Increases ~10% from 25°C to 85°C
- Remains well within 5 mA specification

**Design margin:** Use 400 kHz or slower I2C to maintain timing margins across temperature.

### EMI and Noise Immunity

**Sources of noise in induction cooker:**
1. IGBT switching (20-100 kHz, high dV/dt)
2. Resonant tank ringing
3. AC mains rectification (100/120 Hz)
4. Switch-mode power supplies

**ADUM1250 noise immunity:**
- **CMTI: 25 kV/μs** rejects fast common-mode transients
- **Differential noise:** Use twisted pair for SCL2/SDA2 if long traces
- **Supply noise:** Bypass capacitors critical for rejecting conducted noise

**Best practices:**
```
1. Route I2C traces away from:
   - IGBT drain/source connections
   - AC mains traces
   - High-current DC bus

2. Use ground plane on both sides
   - Provides shielding from radiated EMI
   - Reduces trace impedance

3. Add ferrite beads on VDD1/VDD2 if needed
   - 600Ω @ 100 MHz typical
   - Blocks high-frequency noise from supply
```

### Multi-Device I2C Bus on Isolated Side

You can connect multiple I2C slaves to Side 2:

```
                    VDD2
                     │
                    ┌┴┐ 4.7kΩ
                    │ │
                    └┬┘
                     │
     ┌───────────────┼───────────────┬───────────────┐
     │               │               │               │
     │               │               │               │
SCL2─┼───────────────┼───────────────┼───────────────┤
     │               │               │               │
   ┌─┴──┐          ┌─┴──┐          ┌─┴──┐          ┌─┴──┐
   │LM75│          │INA │          │24LC│          │MCP4│
   │Temp│          │226 │          │64  │          │451 │
   │0x48│          │0x40│          │0x50│          │0x2C│
   └────┘          └────┘          └────┘          └────┘

   Temp            Power           EEPROM          Digital
   Sensor          Monitor         256kB           Pot
```

**Address planning:**
- Avoid address conflicts (each device needs unique address)
- Use device address pins (A0, A1, A2) to set addresses
- Document address map in firmware

**Bus loading:**
- Each additional device adds capacitance
- Each additional device adds pull-down current during ACK
- Limit to 4-5 devices to stay within 400 pF limit

### Clock Stretching Considerations

Some I2C slaves use **clock stretching** to slow down the master:
- Slave holds SCL low to delay next bit
- Common in ADCs (waiting for conversion), EEPROMs (waiting for write)

**ADUM1250 supports clock stretching:**
- SCL is bidirectional on both sides
- Slave holding SCL low propagates through isolator
- Master sees extended low period on SCL

**Firmware considerations:**
```c
// Enable clock stretching timeout in I2C driver
// ADUM1250 adds ~325ns delay, plus slave stretch time
i2c_set_timeout(&hi2c1, 100);  // 100ms timeout

// Some slaves stretch for milliseconds (e.g., EEPROM write)
// Ensure timeout is longer than worst-case stretch time
```

### Mixed Voltage Operation

Side 1 and Side 2 can operate at different voltages (3.0 V to 5.5 V each):

**Common configurations:**

| Application | Side 1 (MCU) | Side 2 (Sensors) | Notes |
|-------------|--------------|------------------|-------|
| Modern MCU + mixed sensors | 3.3 V | 5 V | 5V sensors common (older parts) |
| Legacy system | 5 V | 3.3 V | Modern low-power sensors |
| Battery-powered | 3.3 V | 3.3 V | Minimize power consumption |
| High-noise environment | 3.3 V | 5 V | Higher VOH on Side 2 improves noise margin |

**Design tips:**
- Higher VDD2 provides better noise immunity on isolated side
- Lower VDD reduces power consumption
- Use same voltage if no specific reason to differ

---

## PCB Layout Guidelines

Proper PCB layout is **critical** for maintaining isolation safety and signal integrity.

### Isolation Barrier Design

#### Creepage and Clearance (IPC-2221)

For 2500 V<sub>RMS</sub> isolation, use:

**Minimum spacing (per IEC 60664-1, Pollution Degree 2):**
- Creepage: 4.0 mm
- Clearance: 0.4 mm

**Recommended spacing (includes safety margin):**
- Creepage: 5.0 mm (25% margin)
- Clearance: 0.8 mm (100% margin)

#### PCB Stackup

**2-layer board (minimum):**
```
TOP:    [Side 1 signals] ──GAP─→ [Side 2 signals]
        └─ ADUM1250 pins 1-4     └─ ADUM1250 pins 5-8

BOTTOM: [Side 1 GND] ────GAP──→ [Side 2 GND]
        └─ No vias in gap        └─ No vias in gap
```

**4-layer board (recommended for low EMI):**
```
TOP:    [Side 1 signals] ──GAP─→ [Side 2 signals]
L2:     [Side 1 GND plane] ─GAP→ [Side 2 GND plane]
L3:     [Side 1 PWR plane] ─GAP→ [Side 2 PWR plane]
BOTTOM: [Side 1 signals] ──GAP─→ [Side 2 signals]
```

#### Isolation Slot (Optional, for High-Voltage)

For extra safety margin in high-voltage designs:

```
     Side 1                Side 2
┌──────────────┐      ┌──────────────┐
│              │      │              │
│   Circuit    │  ╱╲  │   Circuit    │
│              │ ╱  ╲ │              │
└──────────────┘╱    ╲└──────────────┘
              ╱  5mm  ╲
             ╱   Slot  ╲
            ╱  (routed) ╲
```

**When to use isolation slot:**
- Induction cookers with >300 V DC bus
- Commercial/industrial equipment
- Extra protection against PCB contamination
- Meeting higher certification requirements

**How to create:**
- Route 1-2 mm wide slot through PCB
- Maintains air gap even with conformal coating
- Keep at least 5 mm total creepage distance

### Component Placement

```
        Side 1 (Microcontroller)          Side 2 (Isolated Sensors)

   ┌────────┐                         ┌────────┐
   │  MCU   │                         │ LM75   │
   │  I2C   ├──SCL1──┐         ┌──SCL2┤ Temp   │
   │ Master │        │         │      │ Sensor │
   └────────┘    ┌───┴─────────┴───┐  └────────┘
                 │   ADUM1250      │
   ┌────────┐   │  I2C Isolator   │  ┌────────┐
   │ 0.1µF  │──VDD1             VDD2──│ 0.1µF  │
   └────────┘   │ 1 2 3 4   5 6 7 8 │  └────────┘
   ┌────────┐   └───┬─────────┬───┘  ┌────────┐
   │  10µF  │───GND1│         │GND2───│  10µF  │
   └────────┘       │         │       └────────┘
                    │◄───────►│
                     5.0 mm gap
                  (no copper, no vias)
```

**Placement rules:**
1. **Bypass capacitors:** <5 mm from VDD1/VDD2 pins
2. **Pull-up resistors:** <10 mm from SCL/SDA pins
3. **Isolation gap:** ≥5 mm around ADUM1250 between sides
4. **MCU and sensors:** Can be far from ADUM1250 (minimize trace length for signal integrity)

### Trace Routing

#### I2C Signal Traces

**Best practices:**
- **Width:** 0.2-0.3 mm (8-12 mil) for low capacitance
- **Spacing:** Minimum 0.2 mm (8 mil) between SCL and SDA
- **Length matching:** Not required (I2C is not differential)
- **Via count:** Minimize vias (each adds ~0.5 pF capacitance)

**Routing priority:**
1. Keep SCL and SDA on same layer if possible
2. Route directly from pull-up resistor to ADUM1250 pin
3. Avoid routing under noisy traces (PWM, IGBT gates)
4. Use ground plane on adjacent layer for shielding

#### Crossing the Isolation Barrier

**Only these connections cross the barrier:**
- VDD1 (if powered from Side 2, otherwise no connection)
- VDD2 (if powered from Side 1, otherwise no connection)
- SCL1 ↔ SCL2 (through ADUM1250 pins)
- SDA1 ↔ SDA2 (through ADUM1250 pins)
- **No GND connection between sides**

**Critical:** GND1 and GND2 must remain isolated
- No direct copper connection
- No shared vias
- No mounting screws connecting both grounds

### Example Layout (Top View)

```
       Side 1 (Low Voltage)          │         Side 2 (Isolated High Voltage)
                                     │
  ┌────┐   R1              ┏━━━━━┓  │  ┏━━━━━┓              R3   ┌────┐
  │ C1 ├───4.7k───SCL1─────┃1   8┃──┼──┃VDD2 ┃─────VDD2────4.7k──┤ C3 │
  └────┘                   ┃     ┃  │  ┗━━━━━┛                    └────┘
  ┌────┐   R2             2┃ A   7┃  │                R4   ┌────┐
  │ C2 ├───4.7k───SDA1─────┃D   S┃──┼───SCL2──────────4.7k──┤ C4 │
  └────┘                   ┃U   C┃  │                       └────┘
  ┌────┐                  3┃M   L┃  │                       ┌────┐  To
VDD1┤0.1µ├─VDD1────────────┃1   2┃──┼───SDA2────────────────┤LM75│  I2C
  └────┘                   ┃2   ┃  │                       └────┘  Slaves
  ┌────┐                  4┃5   ┃  │
  │10µF├─GND1─────────────┃0   ┃  │             ┌────┐
  └────┘                   ┗━━━━━┛  │       GND2─┤10µF│
                                     │             └────┘
       Ground Plane 1                │           Ground Plane 2
  ═══════════════════════════════    │    ═══════════════════════════
                                     │
                                     │◄─── 5.0 mm isolation gap ───►
                                     │      (no copper, traces, or
                                     │       vias in this zone)
```

### Silkscreen Markings

Add these markings for assembly and safety:

```
┌─────────────────────────────────────────┐
│  Side 1              │       Side 2     │
│  LOW VOLTAGE         │  ISOLATED        │
│  3.3V/5V            │  HIGH VOLTAGE   │
│                     │                  │
│                ⚠ ISOLATION BARRIER ⚠   │
│         DO NOT CROSS THIS LINE          │
│    MAINTAIN 5.0mm CREEPAGE DISTANCE    │
└─────────────────────────────────────────┘
```

**Benefits:**
- Guides technicians during debug/rework
- Prevents accidental bridging during assembly
- Meets regulatory requirements for safety marking

### Ground Plane Strategy

**Side 1 ground plane:**
- Connect all GND1 pins and bypass capacitors
- Extend to microcontroller and user interface
- Pour ground plane under I2C traces for shielding
- **Stop at isolation barrier** (leave 5 mm gap minimum)

**Side 2 ground plane:**
- Connect all GND2 pins and bypass capacitors
- Extend to isolated sensors and power supply
- Pour ground plane under I2C traces
- **Stop at isolation barrier** (leave 5 mm gap minimum)

**Thermal relief:**
- Use thermal relief for GND connections (4 spokes, 0.3 mm width)
- Allows easier soldering without preheating
- Does not affect isolation performance

---

## Bill of Materials

### Essential Components for I2C Isolation

| Ref | Part Number | Description | Quantity | Unit Price | Supplier | Notes |
|-----|-------------|-------------|----------|------------|----------|-------|
| U1 | **ADUM1250ARZ** | I2C isolator, 2 bidir channels, SOIC-8 | 1 | $3.50 | Digi-Key, Mouser | Standard version |
| | *or ADUM1251ARZ* | I2C isolator, 1 bidir + 1 unidir, SOIC-8 | 1 | $3.30 | Digi-Key, Mouser | For simple applications |
| C1, C3 | 0805 100nF | MLCC 0.1µF, 10V, X7R, 0805 | 2 | $0.05 | Any | High-frequency bypass |
| C2, C4 | 1206 10µF | MLCC 10µF, 10V, X5R, 1206 | 2 | $0.15 | Any | Bulk capacitance |
| R1-R4 | 0603 4.7kΩ | Resistor 4.7kΩ, 1%, 0.1W, 0603 | 4 | $0.01 | Any | I2C pull-ups (100 kHz) |
| | *or 0603 2.2kΩ* | Resistor 2.2kΩ, 1%, 0.1W, 0603 | 4 | $0.01 | Any | For 400 kHz I2C |

**Total cost per channel:** ~$4.00 (plus isolated power supply if needed)

### Isolated Power Supply Options

If Side 2 requires galvanically isolated power:

| Part Number | Description | Output | Power | Isolation | Price | Notes |
|-------------|-------------|--------|-------|-----------|-------|-------|
| **TMR 1-0511** | Isolated DC-DC | 5V, 200mA | 1W | 1kV | $5.50 | Compact SIP package |
| **MEE1S0505SC** | Isolated DC-DC | 5V, 200mA | 1W | 1.5kV | $4.20 | Economical option |
| **MGLS1D051505C** | Isolated DC-DC | 5V, 200mA | 1W | 1.5kV | $6.80 | Medical grade |
| **NME0505SC** | Isolated DC-DC | 5V, 200mA | 1W | 1kV | $3.90 | Budget option |

**Selection criteria:**
- **Isolation voltage:** Must be ≥560 V to match ADUM1250 working voltage
- **Output current:** Size for total Side 2 load (ADUM1250 + I2C slaves)
- **Efficiency:** 70-80% typical for small isolators
- **Size:** SIP-7 or SMD package depending on space

**Typical Side 2 power budget:**
```
ADUM1250:    2.1 mA @ 3.3V  =  7.0 mW
LM75:        1.0 mA @ 3.3V  =  3.3 mW
INA226:      1.2 mA @ 3.3V  =  4.0 mW
EEPROM:      0.5 mA @ 3.3V  =  1.7 mW (standby)
──────────────────────────────────────
Total:       4.8 mA         = 16.0 mW

Isolated supply required: 5V @ 10mA minimum (50mW)
Recommended: 5V @ 50mA (250mW) for margin and EEPROM writes
```

### Protection Components (Recommended)

| Ref | Part Number | Description | Quantity | Price | Purpose |
|-----|-------------|-------------|----------|-------|---------|
| D1, D2 | SMAJ5.0A | TVS diode, 5V, 400W | 2 | $0.25 | Overvoltage protection on VDD1/VDD2 |
| F1 | 0603L050YR | PTC fuse, 50mA, 6V | 1 | $0.30 | Overcurrent protection on VDD2 |
| FB1, FB2 | BLM18PG121SN1D | Ferrite bead, 120Ω@100MHz | 2 | $0.08 | EMI filtering on supplies |

### Complete Induction Cooker I2C System BOM

For reference, typical complete isolated I2C system in induction cooker:

| Component | Part | Qty | Price | Total |
|-----------|------|-----|-------|-------|
| **Isolation** | ADUM1250ARZ | 1 | $3.50 | $3.50 |
| **Power isolation** | TMR 1-0511 (5V, 1W) | 1 | $5.50 | $5.50 |
| **Temperature sensor** | LM75BDP | 1 | $0.80 | $0.80 |
| **Power monitor** | INA226AIDGSR | 1 | $2.10 | $2.10 |
| **EEPROM (optional)** | 24LC64-I/SN | 1 | $0.45 | $0.45 |
| **Passives** | Resistors, capacitors | 10 | $0.20 | $2.00 |
| | | | **Total** | **$14.35** |

**Cost breakdown:**
- Isolation infrastructure: $11.00 (77%)
- Active sensors/monitors: $2.90 (20%)
- Passives: $2.00 (14%)

**Cost optimization tips:**
1. Use ADUM1251 instead of ADUM1250 if bidirectional SDA not needed: saves $0.20
2. Share isolated power supply with gate driver if available: saves $5.50
3. Reduce to single temperature sensor if power monitoring not needed: saves $2.10

---

## Troubleshooting

### Common Issues and Solutions

#### 1. No I2C Communication After Power-Up

**Symptoms:**
- I2C transactions timeout
- SCL/SDA stuck high or low
- No ACK from slave devices

**Possible causes and fixes:**

| Cause | Check | Solution |
|-------|-------|----------|
| **Hot swap delay not complete** | Scope VDD1/VDD2 rise time | Wait 100+ ms after power valid before I2C access |
| **One supply not powered** | Measure VDD1 and VDD2 voltages | Both must be 3.0-5.5V; check isolated supply |
| **Missing pull-up resistors** | Measure SCL/SDA DC voltage | Should be at VDD when idle; add 4.7kΩ pull-ups |
| **Wrong pull-up side** | Check which side has pull-ups | Need pull-ups on BOTH Side 1 and Side 2 |
| **Shorted I2C bus** | Disconnect slaves, test isolator alone | Check for solder bridges, damaged slave devices |

**Debug procedure:**
```
1. Measure VDD1 and VDD2 with multimeter
   → Both should be within 3.0-5.5V range

2. Measure SCL1, SDA1, SCL2, SDA2 DC voltages with multimeter
   → All should equal VDD (via pull-up resistors)
   → If 0V: missing pull-up or shorted to ground
   → If mid-level: bus contention or damaged device

3. Scope VDD1 and VDD2 during power-up
   → Check for clean monotonic rise
   → Ensure both reach final voltage within 100ms

4. Scope SCL1 and SDA1 during I2C transaction
   → Should see clock pulses and data transitions
   → If no activity: check microcontroller I2C configuration
   → If stuck low: one device holding bus (check slaves)
```

#### 2. Intermittent Communication Errors

**Symptoms:**
- I2C works sometimes, fails randomly
- ACK errors
- Data corruption

**Possible causes:**

| Cause | Diagnostic | Solution |
|-------|------------|----------|
| **Marginal pull-up resistors** | Measure rise time on scope | Should be <1μs for 100kHz; reduce pull-up value |
| **Excessive bus capacitance** | Measure with LCR meter | Must be <400pF; reduce trace length or slave count |
| **Noise coupling** | Check for correlation with IGBT switching | Reroute I2C traces away from power; add ferrite beads |
| **Timing violations** | Measure setup/hold times | Reduce I2C speed from 400kHz to 100kHz |
| **Insufficient bypass capacitors** | Scope VDD1/VDD2 during transaction | Add or move closer 0.1µF caps to ADUM1250 pins |
| **Ground bounce** | Scope GND1/GND2 during IGBT switching | Improve ground plane; add more GND vias |

**Example scope measurement:**

Check SCL rise time:
```
Expected rise time (10% to 90%):
t_rise = 2.2 × R_pullup × C_bus

For 4.7kΩ and 150pF:
t_rise = 2.2 × 4700 × 150e-12 = 1.55 μs

This is acceptable for 100 kHz I2C (max 3 μs rise time).
For 400 kHz, max rise time is 300 ns → need lower pull-up (2.2kΩ).
```

#### 3. Wrong Data Read from Slave Devices

**Symptoms:**
- Sensor readings incorrect (e.g., temperature reads 500°C instead of 50°C)
- EEPROM returns garbage data
- Power monitor shows negative current

**Debugging steps:**

1. **Verify I2C address:**
   ```c
   // LM75 default address is 0x48 (7-bit addressing)
   // Some libraries use 8-bit format: 0x90 (write), 0x91 (read)

   // Check datasheet for address pins (A0, A1, A2)
   // Confirm solder jumpers or resistor straps match firmware
   ```

2. **Verify byte order:**
   ```c
   // Many I2C sensors use MSB-first (big-endian)
   // Microcontroller may use LSB-first (little-endian)

   uint16_t temp_raw = (i2c_data[0] << 8) | i2c_data[1];  // Correct
   // Not: uint16_t temp_raw = (i2c_data[1] << 8) | i2c_data[0];
   ```

3. **Verify register addresses:**
   ```c
   // Check datasheet for correct register map
   // LM75: temperature register = 0x00
   // INA226: voltage register = 0x02, current = 0x04
   ```

4. **Check for device-specific initialization:**
   ```c
   // Some devices require configuration before reading
   // Example: INA226 needs calibration register written first
   ```

#### 4. Communication Works on Bench, Fails in Final System

**Symptoms:**
- I2C functions correctly when tested standalone
- Fails when integrated into induction cooker with IGBTs switching

**Root causes:**

| Issue | Mechanism | Solution |
|-------|-----------|----------|
| **Common-mode noise** | IGBT dV/dt couples into I2C traces | Add ground plane under traces; use twisted pair for long runs |
| **Ground potential difference** | GND1 and GND2 shift relative to each other | This is normal; ADUM1250 designed for this |
| **Supply voltage droop** | IGBT switching causes VDD2 sag | Add bulk capacitance (100µF); check isolated supply rating |
| **EMI from gate driver** | UCC21550 switching couples into ADUM1250 | Increase spacing between gate driver and I2C isolator |
| **Conducted noise on supply** | Switching noise on VDD1/VDD2 rails | Add LC filter or ferrite bead before ADUM1250 |

**Example: Adding ferrite bead to supply**
```
VDD2_RAW ───[ FB1 ]───┬─── VDD2_FILTERED ─── ADUM1250 Pin 8
                      │
                    [ 10µF ]
                      │
                     GND2

FB1: 120Ω @ 100MHz ferrite bead (BLM18PG121SN1D)
Attenuates switching noise without affecting DC supply
```

#### 5. One Channel Works, Other Doesn't

**For ADUM1250 (both channels bidirectional):**

1. **Check for assymetric issues:**
   - Verify pull-ups on both SCL and SDA
   - Check for damaged pin (inspect under microscope)
   - Verify traces for SCL2 and SDA2 not swapped

2. **Test each channel independently:**
   ```c
   // First test SCL channel
   // Send clock pulses, verify propagation with scope

   // Then test SDA channel
   // Toggle SDA, verify propagation

   // If one channel dead: likely damaged IC (replace)
   ```

#### 6. High Supply Current

**Expected current:**
- Side 1: 1.7-2.3 mA
- Side 2: 2.1-2.8 mA
- Total: <5 mA

**If measuring >10 mA:**

| Cause | Check | Fix |
|-------|-------|-----|
| **Damaged IC** | Measure VDD current with I2C bus disconnected | Replace ADUM1250 |
| **Short on bus** | Disconnect all slaves; re-measure | Find and fix short circuit |
| **Pull-up too low** | Check pull-up resistor values | Use 4.7kΩ minimum for Side 1 |
| **Bus stuck low** | Scope SCL/SDA for constant low | Device holding bus low; identify and fix |

### Debugging Tools and Techniques

#### Essential Equipment

1. **Oscilloscope:**
   - Minimum 100 MHz bandwidth (for 400 kHz I2C)
   - 4 channels (SCL1, SDA1, SCL2, SDA2)
   - I2C decode/trigger capability (very helpful)

2. **Logic analyzer:**
   - 8+ channels
   - I2C protocol decode built-in
   - Examples: Saleae Logic, Rigol MSO5000 series

3. **Multimeter:**
   - DC voltage measurements (VDD1, VDD2, SCL, SDA)
   - Current measurement (IDD1, IDD2)

4. **I2C bus analyzer (optional):**
   - Total Phase Beagle I2C/SPI analyzer
   - Helps identify protocol violations

#### Scope Trigger Setup for I2C Debug

**To capture I2C START condition:**
```
Channel 1: SDA1
Channel 2: SCL1
Trigger:   SDA1 falling edge WHILE SCL1 high
```

**To capture specific I2C address:**
```
Enable I2C decode feature
Set trigger on address = 0x48
Captures all transactions to LM75 temperature sensor
```

#### Software Debug

**Add verbose I2C logging:**
```c
void i2c_debug_transaction(uint8_t addr, uint8_t reg, uint8_t *data, uint8_t len) {
    printf("I2C: Addr=0x%02X Reg=0x%02X", addr, reg);

    // Log each byte
    for (int i = 0; i < len; i++) {
        printf(" Data[%d]=0x%02X", i, data[i]);
    }
    printf("\n");

    // Check for errors
    if (HAL_I2C_GetError(&hi2c1) != HAL_I2C_ERROR_NONE) {
        printf("ERROR: I2C error code = 0x%08lX\n", HAL_I2C_GetError(&hi2c1));
    }
}
```

**Implement retry logic with backoff:**
```c
#define I2C_MAX_RETRIES 3

int i2c_read_with_retry(uint8_t addr, uint8_t reg, uint8_t *data, uint8_t len) {
    for (int retry = 0; retry < I2C_MAX_RETRIES; retry++) {
        if (HAL_I2C_Mem_Read(&hi2c1, addr << 1, reg, 1, data, len, 100) == HAL_OK) {
            return 0;  // Success
        }

        // Log error
        printf("I2C read retry %d/%d\n", retry + 1, I2C_MAX_RETRIES);

        // Exponential backoff
        HAL_Delay(10 << retry);  // 10ms, 20ms, 40ms
    }

    return -1;  // Failed after retries
}
```

### Isolation Testing

To verify isolation barrier integrity:

1. **Hi-pot test (production):**
   - Apply 3000 VDC between Side 1 and Side 2 for 60 seconds
   - Leakage current should be <10 μA
   - **Caution:** Destructive test if isolation is already damaged

2. **Megohm test (non-destructive):**
   - Use megohm meter (1000 VDC test voltage)
   - Measure resistance between GND1 and GND2
   - Should read >100 MΩ (typically >1 GΩ)

3. **Visual inspection:**
   - Check for:
     - Solder bridges across isolation barrier
     - Cracks in PCB around ADUM1250
     - Contamination (flux, dust) reducing creepage
     - Damaged package (cracks in molding compound)

---

## References and Resources

### Datasheets and Application Notes

1. **ADUM1250/ADUM1251 Datasheet**
   - Analog Devices, Rev. D
   - Complete electrical specifications, timing diagrams, package information
   - [Download from Analog Devices website]

2. **AN-1073: Designing Power Supply Bypassing for I2C Isolators**
   - Analog Devices Application Note
   - Details on bypass capacitor placement and selection

3. **AN-1079: I2C Isolation System Design**
   - Covers pull-up resistor selection, bus loading, timing analysis
   - Multi-drop I2C through isolators

4. **AN-1109: PCB Layout Guidelines for iCoupler Isolation Products**
   - Creepage/clearance requirements
   - Example layouts for different isolation voltages

### I2C Specification Documents

5. **UM10204: I2C-bus Specification and User Manual**
   - NXP Semiconductors
   - Official I2C protocol specification (Standard, Fast, Fast-Plus modes)
   - Timing requirements, electrical specifications

### Safety Standards

6. **UL 1577: Optical Isolators**
   - Underwriters Laboratories
   - Standard for component-level isolation testing

7. **IEC 60747-17 (VDE 0884-17): Digital Isolators**
   - International standard for semiconductor-based isolators
   - Replaces optical isolator standards for magnetic isolators

8. **IEC 60664-1: Insulation Coordination for Equipment Within Low-Voltage Systems**
   - Creepage and clearance requirements
   - Pollution degree, installation category definitions

9. **IEC 60335-2-6: Safety of Household and Similar Electrical Appliances**
   - Part 2-6: Particular requirements for stationary cooking ranges and ovens
   - Relevant for induction cooker safety certification

### Development Tools

10. **Analog Devices EVAL-ADUM1250EBZ Evaluation Board**
    - Pre-built test platform for ADUM1250
    - Includes recommended layout and component values
    - ~$100 USD

11. **I2C Tools (Linux command-line utilities)**
    - i2cdetect, i2cget, i2cset, i2cdump
    - Useful for testing I2C communication on embedded Linux platforms

### Online Resources

12. **Analog Devices EngineerZone Forum**
    - https://ez.analog.com
    - Community support for ADUM1250 questions
    - Search for "ADUM1250" for existing threads

13. **TI I2C Application Notes**
    - While for TI isolators, many design principles apply universally
    - Useful for pull-up calculations and bus loading

### Recommended Reading for Induction Cooker Design

14. **Application Note: Gate Drive Considerations for IGBT Modules**
    - Infineon Technologies
    - Covers gate driver isolation and control signal isolation

15. **EMC Design Guidelines for Induction Cooking**
    - Various manufacturers (Infineon, ON Semi, Texas Instruments)
    - Techniques for minimizing EMI from IGBT switching

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024 | Claude | Initial release for ADUM1250/ADUM1251 documentation |

---

## Appendix A: Quick Reference Tables

### Pin Functions Summary

| Pin | Name | Side | Function | Connection |
|-----|------|------|----------|------------|
| 1 | VDD1 | 1 | Power supply | 3.0-5.5V, bypass with 0.1µF + 10µF |
| 2 | SCL1 | 1 | I2C clock | To MCU I2C SCL, add 4.7kΩ pull-up to VDD1 |
| 3 | SDA1 | 1 | I2C data | To MCU I2C SDA, add 4.7kΩ pull-up to VDD1 |
| 4 | GND1 | 1 | Ground | To Side 1 ground plane, isolate from GND2 |
| 5 | GND2 | 2 | Ground | To Side 2 ground plane, isolate from GND1 |
| 6 | SDA2 | 2 | I2C data | To I2C slaves, add 4.7kΩ pull-up to VDD2 |
| 7 | SCL2 | 2 | I2C clock | To I2C slaves, add 4.7kΩ pull-up to VDD2 |
| 8 | VDD2 | 2 | Power supply | 3.0-5.5V isolated, bypass with 0.1µF + 10µF |

### Absolute Maximum Ratings

| Parameter | Value | Unit |
|-----------|-------|------|
| VDD1, VDD2 to GND1, GND2 | -0.3 to +7.0 | V |
| IO pins to GND (same side) | -0.3 to VDD+0.3 | V |
| Transient isolation voltage (60 seconds, UL 1577) | 3750 | V<sub>RMS</sub> |
| Continuous working voltage (IEC 60747-17) | 560 | V<sub>PEAK</sub> |
| Operating temperature | -40 to +105 | °C |
| Storage temperature | -65 to +150 | °C |
| Junction temperature | 150 | °C |
| Lead temperature (soldering, 10 sec) | 300 | °C |

### Electrical Characteristics (VDD1 = VDD2 = 3.3V, TA = 25°C)

| Parameter | Min | Typ | Max | Unit |
|-----------|-----|-----|-----|------|
| **Supply Current** | | | | |
| IDD1 (Side 1) | - | 1.7 | 2.3 | mA |
| IDD2 (Side 2) | - | 2.1 | 2.8 | mA |
| **Logic Inputs (Side 1)** | | | | |
| Input low threshold | - | 500-700 | - | mV |
| Input hysteresis | - | 100 | - | mV |
| **Logic Inputs (Side 2)** | | | | |
| Input low voltage (VIL) | - | - | 0.3×VDD2 | V |
| Input high voltage (VIH) | 0.7×VDD2 | - | - | V |
| **Logic Outputs (Side 1)** | | | | |
| Output low voltage (VOL) @ 3mA | - | 750 | 900 | mV |
| Current sink | - | 3 | - | mA |
| **Logic Outputs (Side 2)** | | | | |
| Output low voltage (VOL) @ 3mA | - | - | 400 | mV |
| Current sink | - | 30 | - | mA |
| **Timing (TA = 25°C)** | | | | |
| Propagation delay (Side 1→2) | - | 82 | 115 | ns |
| Propagation delay (Side 2→1) | - | 310 | 340 | ns |
| Maximum data rate | - | 1000 | - | kHz |

### I2C Pull-Up Resistor Selection Guide

| I2C Speed | VDD | Bus Capacitance | Recommended R_PU | Notes |
|-----------|-----|-----------------|------------------|-------|
| 100 kHz | 3.3V | 50-150 pF | 4.7 kΩ | Standard choice |
| 100 kHz | 5.0V | 50-150 pF | 4.7 kΩ | Standard choice |
| 400 kHz | 3.3V | <100 pF | 2.2 kΩ | Check Side 1 current limit |
| 400 kHz | 5.0V | <100 pF | 2.2 kΩ | Preferred for Fast Mode |
| 1 MHz | 5.0V | <50 pF | 1.0-1.5 kΩ | Side 2 only (30mA sink) |

---

## Appendix B: Example Firmware Code

### STM32 HAL I2C Initialization

```c
/* I2C1 initialization for communication through ADUM1250 */
void MX_I2C1_Init(void)
{
    hi2c1.Instance = I2C1;
    hi2c1.Init.ClockSpeed = 100000;  // 100 kHz for reliable isolated I2C
    hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
    hi2c1.Init.OwnAddress1 = 0;
    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;

    if (HAL_I2C_Init(&hi2c1) != HAL_OK) {
        Error_Handler();
    }
}

/* Read temperature from LM75 sensor on isolated side */
float read_igbt_temperature(void)
{
    uint8_t temp_data[2];
    int16_t temp_raw;
    float temperature;

    // LM75 I2C address (7-bit): 0x48
    // Temperature register address: 0x00
    HAL_StatusTypeDef status = HAL_I2C_Mem_Read(
        &hi2c1,           // I2C handle
        0x48 << 1,        // Device address (shifted for HAL)
        0x00,             // Register address
        I2C_MEMADD_SIZE_8BIT,
        temp_data,        // Receive buffer
        2,                // Number of bytes
        100               // Timeout (ms)
    );

    if (status != HAL_OK) {
        // Error handling
        return -999.0f;  // Invalid temperature indicates error
    }

    // LM75 returns 11-bit temperature in MSB format
    // Resolution: 0.125°C per LSB
    temp_raw = (int16_t)((temp_data[0] << 8) | temp_data[1]);
    temp_raw >>= 5;  // Shift to align 11-bit value

    temperature = temp_raw * 0.125f;

    return temperature;
}

/* Read voltage and current from INA226 power monitor */
typedef struct {
    float voltage;  // Bus voltage in volts
    float current;  // Current in amps
    float power;    // Power in watts
} power_measurement_t;

power_measurement_t read_power_monitor(void)
{
    power_measurement_t result = {0};
    uint8_t data[2];
    int16_t raw_value;

    // INA226 I2C address: 0x40
    // Bus voltage register: 0x02 (16-bit, LSB = 1.25mV)
    if (HAL_I2C_Mem_Read(&hi2c1, 0x40 << 1, 0x02,
                         I2C_MEMADD_SIZE_8BIT, data, 2, 100) == HAL_OK) {
        raw_value = (int16_t)((data[0] << 8) | data[1]);
        result.voltage = raw_value * 0.00125f;  // LSB = 1.25mV
    }

    // Current register: 0x04 (16-bit, depends on calibration)
    // Assuming 0.1 ohm shunt, 5A max, calibration = 4096
    // LSB = 5A / 32768 = 152.6 μA
    if (HAL_I2C_Mem_Read(&hi2c1, 0x40 << 1, 0x04,
                         I2C_MEMADD_SIZE_8BIT, data, 2, 100) == HAL_OK) {
        raw_value = (int16_t)((data[0] << 8) | data[1]);
        result.current = raw_value * 0.0001526f;  // 152.6 μA per LSB
    }

    result.power = result.voltage * result.current;

    return result;
}
```

### Arduino I2C Example

```cpp
#include <Wire.h>

// I2C addresses
#define LM75_ADDR      0x48
#define INA226_ADDR    0x40

void setup() {
    Serial.begin(115200);
    Wire.begin();  // Initialize I2C as master
    Wire.setClock(100000);  // 100 kHz for ADUM1250

    delay(100);  // Wait for ADUM1250 hot swap startup

    Serial.println("ADUM1250 I2C Isolator - Induction Cooker Monitor");
}

void loop() {
    // Read IGBT temperature every second
    float temp = readTemperature();
    Serial.print("IGBT Temp: ");
    Serial.print(temp);
    Serial.println(" °C");

    // Thermal protection logic
    if (temp > 125.0) {
        Serial.println("CRITICAL: IGBT overtemperature! Shutting down.");
        digitalWrite(SHUTDOWN_PIN, LOW);  // Disable gate driver
    } else if (temp > 100.0) {
        Serial.println("WARNING: High temperature, reducing power.");
        // Reduce PWM duty cycle
    }

    // Read DC bus voltage and current
    float voltage = readBusVoltage();
    float current = readBusCurrent();
    float power = voltage * current;

    Serial.print("DC Bus: ");
    Serial.print(voltage);
    Serial.print(" V, ");
    Serial.print(current);
    Serial.print(" A, ");
    Serial.print(power);
    Serial.println(" W");

    delay(1000);
}

float readTemperature() {
    Wire.beginTransmission(LM75_ADDR);
    Wire.write(0x00);  // Temperature register
    if (Wire.endTransmission() != 0) {
        return -999.0;  // Error
    }

    Wire.requestFrom(LM75_ADDR, 2);
    if (Wire.available() == 2) {
        uint8_t msb = Wire.read();
        uint8_t lsb = Wire.read();

        int16_t temp_raw = ((int16_t)(msb << 8) | lsb) >> 5;
        return temp_raw * 0.125;
    }

    return -999.0;  // Error
}

float readBusVoltage() {
    Wire.beginTransmission(INA226_ADDR);
    Wire.write(0x02);  // Bus voltage register
    if (Wire.endTransmission() != 0) {
        return 0.0;
    }

    Wire.requestFrom(INA226_ADDR, 2);
    if (Wire.available() == 2) {
        uint8_t msb = Wire.read();
        uint8_t lsb = Wire.read();

        uint16_t raw = (msb << 8) | lsb;
        return raw * 0.00125;  // 1.25mV per LSB
    }

    return 0.0;
}

float readBusCurrent() {
    Wire.beginTransmission(INA226_ADDR);
    Wire.write(0x04);  // Current register
    if (Wire.endTransmission() != 0) {
        return 0.0;
    }

    Wire.requestFrom(INA226_ADDR, 2);
    if (Wire.available() == 2) {
        uint8_t msb = Wire.read();
        uint8_t lsb = Wire.read();

        int16_t raw = (int16_t)((msb << 8) | lsb);
        return raw * 0.0001526;  // Depends on calibration
    }

    return 0.0;
}
```

---

**End of ADUM1250 Documentation**

For questions, support, or design review assistance, consult:
- Analog Devices technical support
- EngineerZone online forum
- Your local Analog Devices field applications engineer (FAE)
