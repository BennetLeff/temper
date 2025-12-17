# UCC14140-Q1 Isolated DC/DC Power Module

## High-Level Summary

The **UCC14140-Q1** is an automotive-qualified, high-density, isolated DC/DC power module from Texas Instruments designed specifically for gate driver bias power in electric vehicle (EV) and hybrid electric vehicle (HEV) traction inverters. This compact module provides >3kVRMS basic isolation between the low-voltage control side and high-voltage power stage, enabling safe and reliable operation of IGBT or SiC MOSFET gate drivers.

### Key Features

- **Automotive qualified**: AEC-Q100 Grade 1 (-40°C to +125°C)
- **High isolation**: >3kVRMS basic isolation, 5657VPK per DIN EN IEC 60747-17
- **Dual regulated outputs**:
  - VDD-VEE: 15-25V adjustable (gate drive power)
  - COM-VEE: 2.5V to VDD-VEE adjustable (gate driver logic supply)
- **Wide input range**: 8-18V (12V automotive nominal)
- **High power density**: 1.5W in compact 36-pin SSOP package (12.83mm × 7.50mm)
- **Integrated protection**: UVLO, OVLO, OVP, UVP, thermal shutdown
- **Power-good output**: Open-drain flag for system monitoring
- **Programmable current limit**: Via external RLIM resistor
- **Low EMI**: Integrated soft-start and low dV/dt design

### Typical Applications

- **Automotive traction inverters**: IGBT/SiC gate driver bias power for EV/HEV motor drives
- **Industrial motor drives**: High-voltage motor control with isolated gate drivers
- **Solar inverters**: PV inverter gate driver power supplies
- **Energy storage systems**: Battery management system (BMS) gate driver bias
- **Charging infrastructure**: DC fast charger and onboard charger gate drivers

---

## Role in Gate Driver Bias Applications

### Why Isolated Gate Driver Bias?

In high-voltage inverter applications (300V-900V DC bus), the gate driver circuits for high-side IGBTs or SiC MOSFETs must float at the switching node potential, which can swing from ground to the full DC bus voltage within nanoseconds. This creates several critical requirements:

1. **Galvanic isolation**: The gate driver power supply must be isolated from the controller ground to prevent ground loops and ensure safety.

2. **Voltage regulation**: Gate drive voltage must remain stable (typically ±15V to ±20V) regardless of the switching node voltage or input supply variations.

3. **Sufficient power**: Gate drivers require power for:
   - Quiescent current (5-20mA typical)
   - Gate charge/discharge current (peak currents up to 2-5A)
   - Protection and monitoring circuits

4. **Fast transient response**: Gate driver loads are highly dynamic due to gate switching, requiring low output impedance and adequate output capacitance.

5. **Low noise**: Switching noise must be minimized to prevent false triggering of gate drivers.

### How UCC14140-Q1 Solves These Challenges

The UCC14140-Q1 integrates a complete isolated DC/DC converter with:

- **Capacitive isolation barrier**: Provides >3kVRMS isolation using high-voltage isolation capacitors, enabling compact package size compared to transformer-based solutions

- **Dual regulated outputs**:
  - **VDD-VEE**: Provides the gate drive voltage rails (typically ±15V or ±20V split supply)
  - **COM-VEE (VEEA)**: Provides the analog ground reference and logic supply for the gate driver (typically 2.5V above VEE)

- **High efficiency**: ~75-85% efficiency enables minimal heat generation in space-constrained gate driver circuits

- **Fast startup**: Integrated soft-start ensures controlled output voltage ramp without output overshoot

- **Robust protection**: Comprehensive protection features prevent damage during fault conditions

### System Integration

In a typical three-phase inverter, you would use:
- **3-6 UCC14140-Q1 modules**: One per high-side gate driver (3 for half-bridge, 6 for full isolation of all switches)
- **One shared input bus**: 12V automotive battery/auxiliary supply
- **Coordinated enable**: Single enable signal or individual enable per phase for protection coordination

The UCC14140-Q1 pairs perfectly with gate driver ICs like the UCC21550 or UCC21750, providing the isolated bias power while the gate driver IC handles the PWM signal isolation and gate drive buffering.

---

## How to Use the UCC14140-Q1

### Basic Circuit Configuration

#### Minimum Required External Components

1. **Input side (Primary)**:
   - Input bulk capacitor: 47-100µF electrolytic + 10µF ceramic (close to VIN pins)
   - Enable pull-down or control signal from microcontroller
   - Power-good pull-up resistor: 10kΩ to VIN or 3.3V/5V logic supply

2. **Output side (Secondary)**:
   - VDD output capacitor: 10µF ceramic (X7R) + 47µF electrolytic minimum
   - VEEA output capacitor: 10µF ceramic (X7R) + 47µF electrolytic minimum
   - VEE output capacitor: 10µF ceramic (optional but recommended)
   - Feedback resistor divider (R1, R2) for VDD-VEE voltage setting
   - RLIM resistor for current limit programming

#### Pin Connections

**Primary Side (Low Voltage, Referenced to GNDP)**:
- **VIN (pins 6, 7)**: Connect both pins together to 12V input supply (8-18V range)
- **GNDP (pins 1, 2, 5, 8-18)**: Connect all 14 pins to primary ground plane (thermal and current sharing)
- **ENA (pin 4)**: Enable input (active high, TTL/CMOS compatible)
  - Logic high (>1.5V): Module enabled
  - Logic low (<1.35V): Module disabled, outputs discharged
  - Internal 100kΩ pull-down: Safe to leave floating for always-on operation
- **PG (pin 3)**: Power-good output (open-drain, active low)
  - Asserted low when outputs are in regulation
  - Requires external pull-up resistor (10kΩ typical)

**Secondary Side (Isolated, Referenced to VEE)**:
- **VDD (pins 28, 29)**: Positive output rail (connect both pins together)
- **VEE (pins 19-27, 30, 31, 36)**: Negative output rail (connect all 12 pins together)
- **VEEA (pin 35)**: Analog ground / common reference (gate driver logic supply)
- **FBVDD (pin 34)**: VDD feedback input (connect to resistor divider from VDD)
- **FBVEE (pin 33)**: VEE feedback input (connect to resistor divider to VEE)
- **RLIM (pin 32)**: Current limit programming resistor (connect resistor to VEEA)

### Output Voltage Programming

#### VDD-VEE Voltage Setting

The VDD-VEE output voltage is programmed using a resistor divider connected between VDD and VEE, with the center tap connected to FBVDD and FBVEE:

```
VDD ----[R1]---- FBVDD (pin 34)
                    |
                 FBVEE (pin 33) ----[R2]---- VEE
```

The output voltage is regulated to maintain **2.5V** between FBVDD and FBVEE:

**V(FBVDD - FBVEE) = 2.5V**

Therefore:
```
V(VDD-VEE) = 2.5V × (1 + R1/R2)
```

Or solving for resistors:
```
R1/R2 = [V(VDD-VEE) / 2.5V] - 1
```

**Example calculations**:

| Target V(VDD-VEE) | R2 (fixed) | R1 (calculated) | R1/R2 ratio | Standard R1 |
|-------------------|------------|-----------------|-------------|-------------|
| 15V               | 2kΩ        | 10kΩ            | 5.0         | 10kΩ        |
| 18V               | 2kΩ        | 12.4kΩ          | 6.2         | 12.4kΩ      |
| 20V               | 2kΩ        | 14kΩ            | 7.0         | 14kΩ        |
| 22V               | 2kΩ        | 15.6kΩ          | 7.8         | 15.4kΩ      |
| 25V               | 2kΩ        | 18kΩ            | 9.0         | 18kΩ        |

**Recommended values**:
- R2 = 2kΩ ±1% (bottom resistor to VEE)
- R1 = Selected per table above ±1% (top resistor from VDD)
- Resistor tolerance: ±1% or better for <±2% output voltage accuracy
- Resistor power rating: 1/16W minimum (typical power dissipation <1mW)

**Design notes**:
- Keep total divider impedance (R1+R2) between 10kΩ and 50kΩ for optimal performance
- Lower impedance = better noise immunity but higher quiescent current
- Higher impedance = lower power loss but more susceptible to noise
- Route feedback traces away from switching nodes to minimize noise coupling
- Use 0.1µF ceramic capacitor from FBVDD to FBVEE if in high-noise environment

#### VEEA (COM) Voltage Setting

By default, VEEA settles at approximately **2.5V above VEE** when left unconnected (floating). This provides a convenient logic supply and analog reference for the gate driver.

For other voltages between 2.5V and V(VDD-VEE), a feedback divider can be used between VEEA and VEE. However, for most gate driver applications, the default 2.5V is appropriate and no external components are needed.

**VEEA typical use cases**:
- **Default (floating)**: VEEA = VEE + 2.5V (gate driver logic supply, 5V logic with ±15V gates)
- **Higher voltage**: Can be increased to provide higher logic supply voltage if needed by gate driver

### Current Limit Programming

The output current limit is programmed by a resistor from RLIM (pin 32) to VEEA (pin 35):

```
I_LIM = 175µA / R_RLIM  (typical)
```

Or solving for RLIM:
```
R_RLIM = 175µA / I_LIM
```

**Example calculations**:

| Target I_LIM | R_RLIM (calculated) | Standard R_RLIM |
|--------------|---------------------|-----------------|
| 50mA         | 3.5kΩ               | 3.48kΩ (1%)     |
| 75mA         | 2.33kΩ              | 2.32kΩ (1%)     |
| 100mA        | 1.75kΩ              | 1.74kΩ (1%)     |
| 150mA        | 1.17kΩ              | 1.15kΩ (1%)     |

**Recommended current limit setting**:

For gate driver applications, select I_LIM based on:
1. **Worst-case gate driver load**: Quiescent current + average gate switching current
2. **Margin**: Set I_LIM = 1.5× typical load current for adequate margin
3. **Absolute maximum**: I_LIM should not exceed the module's maximum output power capability

**Typical gate driver load estimation**:
- Quiescent current: 5-20mA (gate driver IC quiescent)
- Average gate switching current: f_SW × Q_G × V_GS / 1000
  - Example: 20kHz × 200nC × 15V / 1000 = 60mA average

**Design example**:
- Quiescent: 15mA
- Switching average: 60mA
- Total typical: 75mA
- Set I_LIM = 75mA × 1.5 = 112mA → Use R_RLIM = 1.5kΩ for ~117mA limit

**Important notes**:
- Current limit is a fold-back type that reduces output voltage when triggered
- Continuous operation in current limit may cause thermal shutdown
- Use current limit as a protection feature, not a current source

### Enable and Power-Good Operation

#### Enable Input (ENA, pin 4)

- **Logic high (>1.5V)**: Module enabled, soft-start begins, outputs ramp up
- **Logic low (<1.35V)**: Module disabled, outputs actively pulled down via APD (Active Pull-Down)
- **Hysteresis**: ~150mV between rising and falling thresholds for noise immunity
- **Input impedance**: 100kΩ pull-down to GNDP (default disabled if floating)

**Enable control options**:

1. **Always enabled**: Tie ENA to VIN through a 10kΩ resistor (enabled whenever input power present)

2. **Microcontroller control**: Drive ENA from MCU GPIO (3.3V or 5V logic)
   - Allows coordinated startup/shutdown sequences
   - Enables fault response (disable outputs during overcurrent, overtemperature, etc.)

3. **UVLO protection**: Use external comparator to disable module if input voltage drops below safe level

#### Power-Good Output (PG, pin 3)

- **Open-drain output** (requires external pull-up resistor)
- **Active low** (pulled to ground when output is good)
- **Assertion conditions** (all must be true):
  - VIN > UVLO rising threshold (8V)
  - ENA is high
  - VDD-VEE output is within ±10% of regulation target
  - Soft-start complete
  - No fault conditions (OVP, thermal shutdown)

**Typical PG connections**:

1. **Status LED**:
   ```
   VIN ----[1kΩ]----(LED anode)----(LED cathode)---- PG
   ```
   LED on when power good (PG pulled low)

2. **Microcontroller monitoring**:
   ```
   3.3V ----[10kΩ]---- PG ---- MCU GPIO input
   ```
   GPIO reads low when power good, high when fault

3. **Gate driver enable**:
   ```
   5V ----[10kΩ]---- PG ---- Gate Driver "Enable" input
   ```
   Gate driver enabled only when bias power is stable

**Design notes**:
- PG assertion typically occurs 30-50ms after ENA rising edge (soft-start time)
- PG has weak pull-up when module is unpowered (high impedance)
- Maximum sink current: 5mA typical (use >1kΩ pull-up for 5V systems)

### Thermal Considerations

The UCC14140-Q1 dissipates power equal to:
```
P_DISS = P_IN - P_OUT = P_OUT × [(1/η) - 1]
```

Where η is efficiency (typically 75-85% depending on load and input voltage).

**Example**:
- P_OUT = 1.2W (800mA total output at 20V VDD-VEE)
- η = 80%
- P_DISS = 1.2W × [(1/0.80) - 1] = 1.2W × 0.25 = 0.3W

**Thermal resistance**:
- θ_JA = 32°C/W (typical with recommended PCB layout and thermal vias)
- θ_JA = 44°C/W (worst case, minimal copper)

**Junction temperature**:
```
T_J = T_A + P_DISS × θ_JA
```

**Example** (continued):
- T_A = 85°C (maximum ambient for automotive applications)
- T_J = 85°C + 0.3W × 32°C/W = 85°C + 9.6°C = 94.6°C

Maximum T_J = 150°C (thermal shutdown at 165°C typical), so this design has adequate thermal margin.

**Thermal design recommendations**:

1. **Use thermal vias**: Place 9-16 thermal vias (0.3mm diameter) under the GNDP and VEE pads

2. **Maximize copper area**: Connect GNDP pins to large primary ground plane, VEE pins to large secondary ground plane

3. **Airflow**: In high-power applications (>1W), ensure adequate airflow over the module

4. **Board material**: Use PCB with good thermal conductivity (standard FR-4 with 2oz copper is adequate)

5. **Keep-out zones**: Avoid placing heat-sensitive components within 5mm of the module

6. **Monitor temperature**: Use the thermal shutdown as a last-resort protection; design for T_J < 125°C under worst-case conditions

---

## SPICE Simulation Guide

The UCC14140-Q1 SPICE model (`UCC14140-Q1.lib`) is a behavioral model suitable for system-level analysis in ngspice, LTspice, and KiCad/Eeschema.

### Model Capabilities

**What the model includes**:
- Primary-side UVLO (8V rising, 7V falling)
- Enable control with threshold and hysteresis
- Soft-start timing (~28-30ms typical)
- Dual regulated outputs (VDD-VEE and VEEA-VEE) with 2.5V reference
- Feedback voltage control via FBVDD and FBVEE
- Current limit programming via RLIM resistor
- Power-good output with assertion logic
- Input current draw based on output power and efficiency (~80%)
- Thermal model (simplified junction temperature calculation)
- OVP (overvoltage protection) at 28V typical

**Model limitations** (typical for behavioral models):
- Switching ripple is not modeled (outputs are ideal DC)
- Isolation barrier is not physically modeled (no capacitive/magnetic coupling)
- EMI/EMC characteristics are not included
- Transient response is simplified (actual hardware has more complex dynamics)
- Temperature-dependent parameter variations are simplified

### Running the Test Circuit

1. **Install ngspice** (if not already installed):
   ```bash
   # macOS
   brew install ngspice

   # Linux (Debian/Ubuntu)
   sudo apt-get install ngspice

   # Windows
   # Download from http://ngspice.sourceforge.net/download.html
   ```

2. **Navigate to the component directory**:
   ```bash
   cd /path/to/components/ucc14140
   ```

3. **Run the simulation**:
   ```bash
   ngspice UCC14140-Q1_test.cir
   ```

4. **View results**:
   The simulation will automatically generate plots showing:
   - Input voltage, enable signal, and power-good output
   - Output voltages (VDD-COM, COM-VEE, VDD-VEE)
   - Output currents on each rail
   - Input current and power
   - Efficiency calculation

   At the end, the simulation prints measured parameters including:
   - Startup time to 90% of final output voltage
   - Steady-state output voltages
   - Output voltage ripple
   - Average output currents
   - Input/output power and efficiency
   - Feedback voltage accuracy

### Expected Results

From the test circuit (`UCC14140-Q1_test.cir`), you should see:

| Parameter | Expected Value | Tolerance |
|-----------|----------------|-----------|
| VDD-VEE output | 20V | ±5% (19-21V) |
| VDD-VEEA output | ~17.5V | ±5% |
| VEEA-VEE output | ~2.5V | ±5% |
| Startup time (90%) | 25-32ms | - |
| Efficiency | 75-85% | - |
| Feedback voltage | 2.5V | ±2% |
| Input current (at 12V, 1.2W load) | 125-150mA | - |
| PG assertion time | 30-50ms | - |

**Troubleshooting simulation issues**:

- **"Subcircuit UCC14140-Q1 not found"**: Ensure `UCC14140-Q1.lib` is in the same directory or update `.include` path
- **"Timestep too small"**: Increase minimum timestep in `.tran` statement (e.g., `.tran 10u 100m 0 10u`)
- **"Singular matrix"**: Check for floating nodes, ensure all grounds are properly connected
- **Convergence issues**: Add `.options reltol=0.01` to relax convergence criteria

### Customizing the Test Circuit

To adapt the test circuit for your application:

1. **Change input voltage**:
   ```spice
   VIN VIN_RAIL 0 DC 12.0    → Change to your input voltage (8-18V)
   ```

2. **Change output voltage**:
   Modify feedback resistors R_FBVDD_TOP and R_FBVDD_BOT per the equations in "Output Voltage Programming" section.

3. **Change current limit**:
   ```spice
   R_RLIM RLIM_PIN VEEA_OUT 2.2k    → Change to desired RLIM value
   ```

4. **Change load profile**:
   Modify `I_LOAD_VDD`, `I_LOAD_VEEA`, and `I_LOAD_PULSE` current sources to match your gate driver load.

5. **Add enable sequence**:
   ```spice
   VEN ENABLE 0 PWL(0 0 1m 0 1.01m 3.3 100m 3.3)
   ```
   Modify PWL time points to match your enable timing requirements.

### Using the Model in Your Design

To integrate the UCC14140-Q1 model into your own SPICE netlist:

1. **Include the library**:
   ```spice
   .include path/to/UCC14140-Q1.lib
   ```

2. **Instantiate the module**:
   ```spice
   * UCC14140-Q1 instance
   * Pin order: GNDP×14, PG, ENA, VIN×2, VEE×12, VDD×2, RLIM, FBVEE, FBVDD, VEEA
   XUCC14140 0 0 PG_OUT ENA_IN 0 VIN_NODE VIN_NODE 0 0 0 0 0 0 0 0 0 0 0
   + VEE VEE VEE VEE VEE VEE VEE VEE
   + VDD VDD
   + VEE VEE
   + RLIM_NODE FBVEE_NODE FBVDD_NODE VEEA
   + VEE
   + UCC14140-Q1
   ```

3. **Connect external components** per the schematic in the "How to Use" section.

---

## Safety and Compliance

### Isolation Ratings

The UCC14140-Q1 provides basic isolation suitable for functional isolation in automotive and industrial applications:

| Isolation Parameter | Rating | Standard |
|---------------------|--------|----------|
| Isolation voltage (RMS) | >3000V | VDE 0884-11 |
| Isolation voltage (peak) | 5657V | DIN EN IEC 60747-17 |
| Isolation group | 600V | DIN VDE V 0884-11:2017-01 |
| Creepage distance | ≥4mm | UL1577 |
| Clearance distance | ≥4mm | UL1577 |
| Comparative Tracking Index (CTI) | 250-400 | IEC 60112 |

**Important**: The UCC14140-Q1 provides **basic isolation**, not reinforced isolation. It is suitable for:
- ✓ Functional isolation in automotive traction inverters (per ISO 16750)
- ✓ Operating voltages up to 600V DC bus
- ✓ Working voltage up to 300V RMS
- ✗ **Not** suitable for reinforced isolation per IEC 61010 (medical, direct mains connection)

### Automotive Qualification

- **AEC-Q100 Grade 1**: Qualified for -40°C to +125°C ambient temperature
- **Moisture Sensitivity Level**: MSL 1 (unlimited floor life at <30°C / 85% RH)
- **ESD Rating**: HBM ±2kV, CDM ±500V (Class 1C)

### Electromagnetic Compatibility (EMC)

The UCC14140-Q1 is designed for low EMI, but proper PCB layout is critical:

**Emissions**:
- Meets CISPR 25 Class 5 limits with proper layout and input filtering
- Soft-start minimizes inrush current and dI/dt

**Immunity**:
- ISO 7637-2 pulse 1 (negative transients): -100V to -150V
- ISO 7637-2 pulse 2a (positive transients): +75V to +100V
- ISO 7637-2 pulse 3a/b (fast transients): ±100V

**Required external components for EMC compliance**:
1. **Input filter**: 10µH series inductor + 47µF bulk capacitor + 10µF ceramic capacitor
2. **Output capacitors**: Low ESR ceramic capacitors on all outputs (reduce high-frequency noise)
3. **PCB layout**: Follow layout guidelines (see PCB Layout Guidelines section)

### Functional Safety

The UCC14140-Q1 is **functional safety capable** but not pre-certified:
- Suitable for use in ASIL-B and ASIL-C systems with external monitoring
- Provides diagnostic coverage via:
  - UVLO monitoring (primary and secondary side)
  - OVP/UVP detection
  - Thermal shutdown
  - Power-good output for system health monitoring

**Recommended functional safety measures**:
1. Monitor PG output for bias power health
2. Implement input voltage monitoring (external to module)
3. Implement output voltage monitoring (measure VDD-VEE and VEEA-VEE)
4. Coordinate enable control with system safety state
5. Include redundant bias supply for ASIL-D systems

---

## Design Considerations

### Input Power Supply

**Input voltage range**: 8V to 18V
- Recommended nominal: 12V (automotive battery)
- Minimum for full power: 10.8V (1.5W available)
- Below 10.8V or above 13.2V: Derate to 1W maximum output power

**Input current**:
- Quiescent (disabled): <100µA
- Quiescent (enabled, no load): ~18mA typical
- Full load (1.5W out at 12V in, 80% efficiency): ~155mA

**Input bulk capacitor**:
- Minimum: 47µF electrolytic or polymer
- Recommended: 100µF electrolytic + 10µF ceramic (X7R or X5R)
- Voltage rating: ≥25V (for 12V input with automotive transients)
- ESR: <100mΩ at 100kHz (electrolytic), <10mΩ (ceramic)

**Input filtering** (for EMC compliance):
- Series inductor: 10µH to 47µH, current rating >500mA
- Additional input capacitors: 10µF X7R ceramic close to VIN pins

### Output Capacitor Selection

Adequate output capacitance is critical for:
1. Stability of the internal regulation loop
2. Transient response to load steps (gate switching)
3. Ripple voltage minimization

**VDD output** (pins 28, 29):
- **Minimum**: 10µF ceramic (X7R) + 47µF electrolytic/polymer
- **Recommended**: 22µF ceramic (X7R) + 100µF low-ESR electrolytic
- Voltage rating: ≥35V for 20V VDD-VEE (1.5× margin), ≥50V for 25V VDD-VEE
- ESR: <10mΩ for ceramic, <50mΩ for electrolytic
- Place ceramic capacitor within 5mm of VDD and VEEA pins

**VEEA output** (pin 35):
- **Minimum**: 10µF ceramic (X7R) + 47µF electrolytic/polymer
- **Recommended**: 22µF ceramic (X7R) + 100µF low-ESR electrolytic
- Voltage rating: ≥10V (for 2.5V VEEA-VEE default)
- ESR: <10mΩ for ceramic, <50mΩ for electrolytic
- Place ceramic capacitor within 5mm of VEEA and VEE pins

**VEE output** (pins 19-27, 30, 31, 36):
- **Minimum**: 10µF ceramic (X7R) referenced to secondary ground
- **Recommended**: 22µF ceramic (X7R) + 47µF electrolytic
- Note: VEE is typically the most negative rail and may not require as much bulk capacitance as VDD/VEEA

**Ceramic capacitor derating**:
- X7R and X5R dielectrics lose capacitance with applied DC bias voltage
- At 50% rated voltage, X7R typically retains 70-80% of nominal capacitance
- **Design rule**: Specify ceramic capacitors with voltage rating ≥2× maximum DC voltage to maintain capacitance

**Example**: For 20V VDD-VEEA output:
- Use 50V rated ceramic capacitors
- 22µF/50V X7R will provide ~17-18µF effective capacitance at 20V bias
- This exceeds the minimum 10µF requirement

### Feedback Network Design

**Resistor divider for VDD-VEE regulation**:

Critical design parameters:
- **Accuracy**: Use ±1% tolerance resistors for ±2% output voltage accuracy
  - Output voltage error: ±1% from reference + ±1.4% from resistor tolerance = ±2.4% total

- **Divider current**: Typically 100µA to 500µA
  - Too low (<50µA): Susceptible to leakage currents and noise
  - Too high (>1mA): Wastes power and causes self-heating

- **Temperature coefficient**: Use resistors with low tempco (±100ppm/°C or better)
  - Metal film resistors recommended over thick-film

- **Noise filtering**: Optional 0.1µF capacitor from FBVDD to FBVEE in high-noise environments
  - Avoid large capacitors (>1µF) which can cause instability

**Example design** (20V VDD-VEE output):
```
Target: 20V ± 2%
Reference: 2.5V
R1/R2 ratio = (20V / 2.5V) - 1 = 7.0

Select: R2 = 2.0kΩ ±1%, R1 = 14.0kΩ ±1%
Divider current: 20V / (14kΩ + 2kΩ) = 1.25mA (acceptable)
Power dissipation: 20V × 1.25mA = 25mW (use 1/16W or 1/10W resistors)
```

**PCB layout**:
- Route FBVDD and FBVEE traces as a differential pair if possible
- Keep traces <25mm in length
- Avoid routing feedback traces near switching nodes or high dI/dt paths
- Place feedback resistors close to FBVDD and FBVEE pins (within 10mm)

### Current Limit Resistor Selection

The RLIM resistor programs the overcurrent threshold:

```
I_LIM(typ) = 175µA / R_RLIM
I_LIM(min) = 160µA / R_RLIM
I_LIM(max) = 190µA / R_RLIM
```

**Design procedure**:

1. **Calculate worst-case load current**:
   ```
   I_LOAD_MAX = I_QUIESCENT + I_SWITCHING_AVG + I_TRANSIENT
   ```

2. **Add margin** (typically 1.5× to 2×):
   ```
   I_LIM_TARGET = I_LOAD_MAX × 1.5
   ```

3. **Calculate RLIM** (use typical formula for nominal target):
   ```
   R_RLIM = 175µA / I_LIM_TARGET
   ```

4. **Verify against min/max**:
   ```
   I_LIM(min) = 160µA / R_RLIM  (must be > I_LOAD_MAX for margin)
   I_LIM(max) = 190µA / R_RLIM  (must not exceed power budget)
   ```

**Example**:
```
Gate driver load: 80mA maximum
Margin: 1.5×
Target: 120mA
R_RLIM = 175µA / 120mA = 1.46kΩ → Select 1.5kΩ ±1%

Verify:
I_LIM(min) = 160µA / 1.5kΩ = 107mA > 80mA ✓ (33% margin)
I_LIM(max) = 190µA / 1.5kΩ = 127mA < 150mA ✓ (within power budget)
```

**Resistor specifications**:
- Tolerance: ±1% for predictable current limit
- Power rating: 1/16W minimum (power dissipation negligible)
- Temperature coefficient: ±100ppm/°C or better (metal film)

**Important**: Current limit is a **protection feature**, not a constant-current mode. Do not design for continuous operation in current limit, as this may trigger thermal shutdown.

### Layout Considerations for Isolation

To maintain the >3kVRMS isolation rating:

1. **Primary-to-secondary separation**:
   - Minimum creepage: 4mm on PCB surface
   - Minimum clearance: 4mm through air
   - No copper pour between primary and secondary sides within 4mm
   - No vias within 4mm of the isolation boundary

2. **PCB stackup**:
   - Internal isolation: Ensure no internal layers bridge primary and secondary sides
   - Slot or cutout under the IC between primary and secondary is recommended for high-voltage applications (>600V)

3. **Avoid placement**:
   - No components should span the isolation barrier
   - No test points, vias, or mounting holes within the isolation zone

4. **PCB material**:
   - Use PCB material with adequate CTI rating (≥250 for Pollution Degree 2 environments)
   - Standard FR-4 is acceptable for most automotive applications

### Power Budget and Derating

**Maximum output power**:
- 1.5W at VIN = 10.8V to 13.2V (80% of input range)
- 1W at VIN = 8.0V to 10.8V or 13.2V to 18V (edges of input range)

**Design rule**: Derate output power to 80% of maximum for reliability:
- Recommended maximum: 1.2W continuous at nominal input voltage
- Recommended maximum: 0.8W continuous at min/max input voltage

**Power allocation** between VDD and VEEA outputs:
- Total P_OUT = P_VDD + P_VEEA ≤ 1.2W (recommended)
- Typically: P_VDD = 70-80% of total (gate drive power)
- Typically: P_VEEA = 20-30% of total (logic supply)

**Example power budget**:
```
VDD-VEEA = 17.5V, I_VDD = 60mA → P_VDD = 1.05W
VEEA-VEE = 2.5V, I_VEEA = 40mA → P_VEEA = 0.10W
Total: P_OUT = 1.15W ✓ (within 1.2W budget)
```

**Thermal derating**:
- At high ambient temperature (>85°C), ensure junction temperature stays below 125°C
- Use thermal calculation: T_J = T_A + P_DISS × θ_JA
- If T_J exceeds 125°C, reduce output power or improve cooling

---

## Bill of Materials (BOM)

Typical BOM for UCC14140-Q1 application circuit (per module):

| Reference Designator | Component | Value/Part Number | Quantity | Description |
|----------------------|-----------|-------------------|----------|-------------|
| U1 | UCC14140-Q1 | UCC14140QDWNQ1 | 1 | Isolated DC/DC module, 36-pin SSOP |
| C1 | Capacitor, electrolytic | 100µF/25V | 1 | Input bulk capacitor |
| C2 | Capacitor, ceramic X7R | 10µF/25V | 1 | Input bypass capacitor |
| C3 | Capacitor, ceramic X7R | 22µF/50V | 1 | VDD output capacitor |
| C4 | Capacitor, electrolytic | 100µF/50V | 1 | VDD bulk capacitor |
| C5 | Capacitor, ceramic X7R | 22µF/16V | 1 | VEEA output capacitor |
| C6 | Capacitor, electrolytic | 100µF/16V | 1 | VEEA bulk capacitor |
| C7 | Capacitor, ceramic X7R | 10µF/50V | 1 | VEE output capacitor (optional) |
| R1 | Resistor, metal film 1% | 14.0kΩ | 1 | Feedback divider top (for 20V output) |
| R2 | Resistor, metal film 1% | 2.0kΩ | 1 | Feedback divider bottom |
| R3 | Resistor, metal film 1% | 1.5kΩ | 1 | Current limit programming (for ~120mA) |
| R4 | Resistor, thick film 5% | 10kΩ | 1 | Power-good pull-up |
| R5 | Resistor, thick film 5% | 10kΩ | 1 | Enable pull-down (optional) |
| L1 | Inductor, power | 10µH/500mA | 1 | Input filter inductor (optional, for EMC) |

**Total component count**: 13 components (11 required, 2 optional)

**Estimated BOM cost** (at 1k quantity, 2024 pricing):
- UCC14140-Q1: $3.50-$4.50 (varies by distributor and volume)
- Passives: $1.00-$1.50 (capacitors, resistors, inductor)
- **Total**: ~$4.50-$6.00 per module

### Recommended Component Suppliers

**Capacitors**:
- Ceramic X7R: TDK (C series), Murata (GRM series), Samsung (CL series)
- Electrolytic: Panasonic (FR, FK series), Nichicon (UWT, UWX series), Rubycon (ZLJ series)
- Polymer: Panasonic (SP-Cap), Kemet (T510, T520 series)

**Resistors**:
- Metal film 1%: Vishay (RN series), Yageo (MFR series), KOA Speer (RN73 series)
- Thick film 5%: Yageo (RC series), Vishay (CRCW series), Panasonic (ERJ series)

**Inductors**:
- Power inductor: Würth Elektronik (WE-PD series), Coilcraft (MSS series), TDK (SLF series)

---

## PCB Layout Guidelines

Proper PCB layout is essential for:
1. Maintaining isolation ratings
2. Minimizing EMI/EMC issues
3. Ensuring thermal performance
4. Achieving optimal electrical performance

### Layer Stack-up

Recommended 4-layer PCB:
```
Layer 1 (Top):     Component layer, primary and secondary circuits
Layer 2 (Inner):   Primary ground plane (GNDP)
Layer 3 (Inner):   Secondary ground plane (VEE or VEEA reference)
Layer 4 (Bottom):  Power routing, optional components
```

**Alternative 2-layer PCB** (cost-optimized):
```
Layer 1 (Top):     Component layer, signal routing
Layer 2 (Bottom):  Ground planes (split between primary and secondary)
```

For 2-layer designs:
- Use wide traces for power routing (≥1mm for input, ≥0.5mm for outputs)
- Maximize copper pour for ground planes on bottom layer
- Split ground plane at isolation boundary (4mm gap minimum)

### Primary Side Layout (Input Side)

1. **Input power routing**:
   - VIN trace width: ≥1mm (for 200mA current)
   - Place input bulk capacitor (C1) within 20mm of VIN pins
   - Place input ceramic capacitor (C2) within 5mm of VIN pins
   - Use star-point grounding: all GNDP pins → C1 ground → input connector ground

2. **GNDP connections**:
   - Connect all 14 GNDP pins together with wide traces or solid copper pour
   - Use multiple vias (9-16 vias, 0.3mm drill) to connect GNDP pins to inner ground layer
   - Thermal relief for GNDP pins is acceptable for hand soldering, but direct connection is preferred for thermal performance

3. **Enable signal routing**:
   - Keep ENA trace <50mm in length
   - Route away from switching nodes and VIN power traces
   - Add series resistor (100Ω-1kΩ) close to microcontroller GPIO for ESD protection

4. **Power-good signal routing**:
   - PG is open-drain; route to pull-up resistor (R4) and then to monitoring circuit
   - Keep trace <100mm in length
   - Can be routed as a low-speed digital signal (no special impedance control needed)

### Secondary Side Layout (Isolated Output Side)

1. **Output power routing**:
   - VDD trace width: ≥0.5mm (for 100mA current)
   - VEEA trace width: ≥0.5mm (for 50mA current)
   - VEE trace width: ≥0.8mm (for combined return current)

2. **Output capacitor placement**:
   - Place ceramic capacitors (C3, C5, C7) within 5mm of respective output pins
   - Place electrolytic capacitors (C4, C6) within 20mm of output pins
   - Minimize loop area: VDD → C3 → VEEA → C5 → VEE → module

3. **VDD and VEE pin connections**:
   - Connect VDD pins (28, 29) together with wide traces
   - Connect all VEE pins (19-27, 30, 31, 36) together with wide traces or solid copper pour
   - Use multiple vias (9-16 vias, 0.3mm drill) to connect VEE pins to inner ground layer

4. **Feedback network placement**:
   - Place feedback resistors (R1, R2) close to FBVDD and FBVEE pins (within 10mm)
   - Route FBVDD and FBVEE traces as a twisted pair or parallel traces (minimize loop area)
   - Avoid routing feedback traces near switching nodes (VDD, VEE power traces)
   - Keep feedback traces <25mm in length

5. **RLIM resistor placement**:
   - Place R_RLIM within 10mm of RLIM pin
   - Connect to VEEA with short trace (<10mm)

### Isolation Barrier

1. **Primary-to-secondary separation**:
   - Maintain ≥4mm creepage distance on PCB surface between primary and secondary sides
   - Maintain ≥4mm clearance through air and internal PCB layers
   - Mark isolation boundary on silkscreen for assembly reference

2. **Copper pour separation**:
   - Use "keep-out" zones for copper pour on all layers
   - 4mm minimum gap in copper pour between primary ground and secondary ground
   - For high-voltage applications (>600V), consider PCB slot or routed cutout under IC

3. **Component placement**:
   - No components should span the isolation barrier
   - No vias within 4mm of isolation boundary (on either side)
   - No test points or mounting holes within isolation zone

### Thermal Vias

To achieve low thermal resistance (θ_JA = 32°C/W typical):

1. **Primary side (GNDP pins)**:
   - Place 9-16 thermal vias under GNDP pad area (0.3mm drill, plated)
   - Connect to inner ground plane (Layer 2)
   - Connect to large copper pour on bottom layer (if 2-layer PCB)

2. **Secondary side (VEE pins)**:
   - Place 9-16 thermal vias under VEE pad area (0.3mm drill, plated)
   - Connect to inner secondary ground plane (Layer 3)
   - Connect to large copper pour on bottom layer (if 2-layer PCB)

3. **Via pattern**:
   ```
   Recommended via grid under IC:
   ●  ●  ●  ●
   ●  ●  ●  ●
   ●  ●  ●  ●
   (3×4 or 4×4 array)
   ```

4. **Copper area**:
   - Maximize copper area connected to GNDP and VEE pins on all layers
   - Minimum 500mm² for each ground plane (primary and secondary)

### Example Layout Checklist

Before finalizing PCB layout, verify:

- [ ] Input bulk capacitor (C1) within 20mm of VIN pins
- [ ] Input ceramic capacitor (C2) within 5mm of VIN pins
- [ ] Output ceramic capacitors (C3, C5) within 5mm of respective output pins
- [ ] All 14 GNDP pins connected together with low-impedance path
- [ ] All 12 VEE pins connected together with low-impedance path
- [ ] Thermal vias under GNDP and VEE pad areas (9-16 vias each)
- [ ] Isolation boundary clearly marked on silkscreen
- [ ] ≥4mm creepage and clearance between primary and secondary sides
- [ ] No copper pour bridging isolation barrier on any layer
- [ ] Feedback resistors (R1, R2) within 10mm of FBVDD/FBVEE pins
- [ ] Feedback traces <25mm in length, routed away from power traces
- [ ] RLIM resistor (R3) within 10mm of RLIM pin
- [ ] VIN trace width ≥1mm, output trace widths ≥0.5mm
- [ ] Power-good pull-up resistor (R4) close to monitoring circuit

---

## Troubleshooting Guide

### Module Does Not Start Up (PG Remains High)

**Symptoms**:
- VDD, VEEA, VEE outputs remain at 0V
- PG output remains high (not asserted)

**Possible causes**:

1. **Input voltage too low**:
   - **Check**: Measure VIN voltage at pins 6 and 7
   - **Requirement**: VIN must be >8V for UVLO rising threshold
   - **Fix**: Increase input voltage or check input power supply capability

2. **Enable not asserted**:
   - **Check**: Measure ENA voltage at pin 4
   - **Requirement**: ENA must be >1.5V to enable module
   - **Fix**: Drive ENA high or remove pull-down resistor if present

3. **Insufficient input capacitance**:
   - **Check**: Verify input capacitors are installed (C1, C2) and not damaged
   - **Requirement**: Minimum 47µF bulk + 10µF ceramic
   - **Fix**: Install input capacitors close to VIN pins

4. **Insufficient output capacitance**:
   - **Check**: Verify output capacitors are installed (C3-C7) and correct polarity
   - **Requirement**: Minimum 10µF ceramic on VDD and VEEA outputs
   - **Fix**: Install output capacitors with correct polarity (electrolytic caps)

5. **Feedback network open**:
   - **Check**: Verify resistors R1 and R2 are installed and correct values
   - **Check**: Continuity from VDD → R1 → FBVDD, FBVEE → R2 → VEE
   - **Fix**: Install feedback resistors or repair open traces

6. **Thermal shutdown**:
   - **Check**: Measure case temperature of IC (should be <100°C)
   - **Fix**: Improve thermal design (add thermal vias, increase airflow, reduce load)

### Output Voltage Incorrect

**Symptoms**:
- VDD-VEE output is not at expected voltage (e.g., 17V instead of 20V)
- Output voltage is stable but out of spec

**Possible causes**:

1. **Incorrect feedback resistor values**:
   - **Check**: Measure R1 and R2 resistor values with multimeter
   - **Calculate**: V_OUT = 2.5V × (1 + R1/R2)
   - **Fix**: Install correct resistor values per "Output Voltage Programming" section

2. **Feedback connection error**:
   - **Check**: Measure voltage at FBVDD (pin 34) and FBVEE (pin 33)
   - **Requirement**: V(FBVDD - FBVEE) should be 2.5V ±2%
   - **Fix**: Check for shorts or opens in feedback network

3. **Output in current limit**:
   - **Check**: Measure output current (should be below I_LIM)
   - **Check**: Output voltage sags under load (indicates current limiting)
   - **Fix**: Reduce load current or increase RLIM (reduce R_RLIM resistor value)

4. **Load too high (overload)**:
   - **Check**: Disconnect load and measure no-load output voltage
   - **If no-load voltage is correct**: Load exceeds module capability (>1.5W)
   - **Fix**: Reduce load current or use multiple modules in parallel

5. **Input voltage out of range**:
   - **Check**: Measure input voltage under load
   - **Requirement**: VIN = 8-18V (10.8-13.2V for full 1.5W power)
   - **Fix**: Increase input voltage or reduce load (derate to 1W)

### High Output Voltage Ripple or Noise

**Symptoms**:
- Excessive ripple on VDD or VEEA outputs (>100mV p-p)
- High-frequency noise on outputs
- Gate driver false triggering

**Possible causes**:

1. **Insufficient output capacitance**:
   - **Check**: Verify ceramic capacitors (C3, C5) are installed close to output pins
   - **Requirement**: Minimum 10µF ceramic (X7R) within 5mm of pins
   - **Fix**: Add ceramic capacitors or move existing capacitors closer to IC

2. **High ESR output capacitors**:
   - **Check**: Measure output impedance at switching frequency (typically 100kHz-1MHz)
   - **Fix**: Replace electrolytic capacitors with low-ESR types or add parallel ceramic capacitors

3. **Poor PCB layout**:
   - **Check**: Review PCB layout for large loop areas in output filter
   - **Fix**: Minimize loop area: VDD → C_OUT → VEEA → GND → module

4. **Ground bounce**:
   - **Check**: Measure ground potential difference between VEE pins and load ground
   - **Fix**: Improve grounding (use ground plane, add more vias, star-point grounding)

5. **External noise coupling**:
   - **Check**: Measure noise on input supply (may be coupling through module)
   - **Fix**: Add input filter (ferrite bead or inductor) and increase input capacitance

### Thermal Shutdown (Module Shuts Down After Startup)

**Symptoms**:
- Module starts up normally, PG asserts
- After seconds to minutes, outputs shut down and PG de-asserts
- Module restarts (oscillating behavior) or stays off

**Possible causes**:

1. **Insufficient thermal vias**:
   - **Check**: Review PCB layout for thermal vias under GNDP and VEE pins
   - **Requirement**: 9-16 vias (0.3mm drill) under IC for θ_JA = 32°C/W
   - **Fix**: Add thermal vias in PCB layout (requires PCB revision)

2. **Inadequate copper area**:
   - **Check**: Measure copper area connected to GNDP and VEE pins
   - **Requirement**: >500mm² per ground plane
   - **Fix**: Increase copper pour area (requires PCB revision)

3. **Excessive power dissipation**:
   - **Check**: Calculate power dissipation: P_DISS = P_OUT × [(1/η) - 1]
   - **Check**: Estimate junction temperature: T_J = T_A + P_DISS × θ_JA
   - **Requirement**: T_J < 150°C (T_SD = 165°C typical)
   - **Fix**: Reduce output power, improve cooling, or reduce ambient temperature

4. **High ambient temperature**:
   - **Check**: Measure ambient temperature near IC
   - **Requirement**: T_A < 125°C (AEC-Q100 Grade 1 max)
   - **Fix**: Improve ventilation, add heatsink, or relocate module to cooler area

5. **Continuous operation in current limit**:
   - **Check**: Measure output current against I_LIM
   - **Fix**: Reduce load current or increase current limit (lower R_RLIM)

### Module Does Not Disable (Outputs Active When ENA Low)

**Symptoms**:
- VDD, VEEA, VEE outputs remain active even when ENA is pulled low
- PG remains asserted

**Possible causes**:

1. **ENA pin floating or pulled high externally**:
   - **Check**: Measure ENA voltage at pin 4 with control signal disconnected
   - **Expected**: ENA should be near 0V with internal pull-down (no external pull-up)
   - **Fix**: Remove external pull-up resistor or ensure control signal can drive ENA low

2. **ENA trace shorted to VIN or logic supply**:
   - **Check**: Continuity test between ENA and VIN / logic supply
   - **Fix**: Repair short on PCB or replace module

3. **Module damaged**:
   - **Check**: Measure quiescent input current with ENA low (should be <100µA)
   - **If input current is high (>1mA)**: Module may be damaged
   - **Fix**: Replace module

### Poor Efficiency / Excessive Input Current

**Symptoms**:
- Input current higher than expected
- Module runs hot even at light load
- Efficiency <70%

**Possible causes**:

1. **Input voltage out of optimal range**:
   - **Check**: Measure VIN under load
   - **Optimal range**: 10.8V to 13.2V (highest efficiency)
   - **Fix**: Adjust input voltage to nominal 12V if possible

2. **Output voltage too high**:
   - **Check**: VDD-VEE output voltage
   - **Note**: Higher output voltage = more power dissipation = lower efficiency
   - **Fix**: Reduce output voltage to minimum required by load (e.g., 15V instead of 25V)

3. **Incorrect load measurement**:
   - **Check**: Verify output power calculation: P_OUT = V_VDD × I_VDD + V_VEEA × I_VEEA
   - **Common error**: Forgetting to include VEEA load current
   - **Fix**: Measure all output currents and recalculate

4. **Feedback network loading**:
   - **Check**: Measure feedback divider current (should be <2mA)
   - **If current is high**: Divider impedance too low
   - **Fix**: Increase feedback resistor values (maintain same ratio)

5. **Short circuit on output**:
   - **Check**: Disconnect load and measure no-load input current (should be <25mA)
   - **If no-load current is high**: Short circuit on output
   - **Fix**: Inspect PCB for solder bridges, damaged capacitors

### PG Output Does Not Assert (Outputs OK But PG Stays High)

**Symptoms**:
- VDD, VEEA, VEE outputs are at correct voltage
- Module operates normally
- PG output remains high (not pulled low)

**Possible causes**:

1. **Missing pull-up resistor**:
   - **Check**: Verify R_PG pull-up resistor (R4) is installed
   - **Requirement**: 10kΩ pull-up to VIN or logic supply
   - **Fix**: Install pull-up resistor

2. **Soft-start not complete**:
   - **Check**: Wait for soft-start time (30-50ms after ENA rising edge)
   - **Fix**: Allow sufficient time for PG to assert

3. **Output voltage out of regulation window**:
   - **Check**: Measure feedback voltage V(FBVDD - FBVEE)
   - **Requirement**: 2.5V ±10% for PG assertion
   - **Fix**: Adjust feedback resistors to achieve 2.5V feedback voltage

4. **Input voltage marginal**:
   - **Check**: Measure VIN under load (must be >8.5V for PG assertion)
   - **Fix**: Increase input voltage or reduce load

---

## Conclusion

The UCC14140-Q1 is a robust, compact, and automotive-qualified isolated DC/DC power module ideally suited for gate driver bias applications in high-voltage inverters. By following the design guidelines in this document, you can achieve:

- **Reliable operation** in harsh automotive environments (-40°C to +125°C)
- **High efficiency** (75-85%) for minimal power dissipation
- **Compact solution** with minimal external components (11 required parts)
- **Safe isolation** (>3kVRMS) for functional isolation up to 600V systems
- **Flexible output configuration** (15-25V adjustable, dual outputs)

### Quick Start Summary

1. **Input**: 12V nominal (8-18V range), 47µF + 10µF input capacitors
2. **Outputs**:
   - VDD-VEE = 2.5V × (1 + R1/R2), use R2=2kΩ and R1 per table
   - VEEA-VEE = 2.5V default (leave floating)
3. **Current limit**: R_RLIM = 175µA / I_LIM
4. **Output capacitors**: Minimum 10µF ceramic + 47µF electrolytic per rail
5. **Enable**: Pull ENA high (>1.5V) to enable
6. **Power-good**: Open-drain PG output, requires 10kΩ pull-up
7. **Thermal**: Use 9-16 thermal vias under IC for optimal thermal performance
8. **Layout**: Maintain ≥4mm isolation creepage/clearance

For additional support, refer to:
- **Datasheet**: https://www.ti.com/lit/ds/symlink/ucc14140-q1.pdf
- **Application note**: AN-2359 "Gate Driver Bias Power Supply Design for IGBT and SiC Applications"
- **TI E2E Forums**: https://e2e.ti.com/

---

**Document Revision**: 1.0
**Date**: 2024-12
**Author**: Generated from datasheet analysis for KiCad component library
**Status**: Complete
