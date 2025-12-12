# Advanced Power Electronics Curriculum
## Modular Design and Validation of a High-Precision Induction Cooking System
### *Simulation-First Methodology*

---

# Executive Summary

This curriculum guides engineers through the development of a production-grade, high-precision induction heating system—a functional clone of the benchmark Breville Control Freak. Unlike traditional hardware-first approaches, this curriculum employs a rigorous **Simulation-First** methodology where every subsystem is mathematically modeled, simulated, and validated in software before any physical components are purchased or assembled.

The primary objective is the synthesis of a 1500W–2000W Half-Bridge Resonant Inverter controlled by the ESP32-S3 microcontroller, utilizing automotive-grade components for high efficiency and safety. The curriculum emphasizes metrological accuracy, robust thermal management, and strict adherence to industrial isolation standards.

## Core Philosophy: Simulation Before Silicon

The Simulation-First approach provides several critical advantages:

- **Early Error Detection:** Catch design flaws when they cost nothing to fix
- **Parametric Exploration:** Sweep component values to optimize before purchasing
- **Risk Reduction:** Validate thermal limits, voltage stresses, and current ratings in software
- **Documentation:** Simulation files become permanent design records
- **Modular Validation:** Each subsystem proven independently before integration

## Curriculum Structure

The curriculum is organized into six phases that progressively build complexity while maintaining strict validation gates between each phase:

| Phase | Lessons | Focus |
|-------|---------|-------|
| **Phase I** | 1–10 | Simulation Environment & Component Characterization |
| **Phase II** | 11–18 | Power Stage Simulation & Resonant Tank Design |
| **Phase III** | 19–26 | Control System & Sensing Simulation |
| **Phase IV** | 27–32 | Firmware Development & Algorithm Validation |
| **Phase V** | 33–38 | PCB Design & Manufacturing Preparation |
| **Phase VI** | 39–44 | Hardware Assembly, Integration & Calibration |

Physical PCB work is deliberately deferred until Phase V. By that point, every component value, thermal limit, and control parameter will have been validated through simulation, dramatically reducing the risk of expensive hardware failures.

---

# KiCad Simulation Workflow Overview

This section provides a comprehensive reference for building schematics in KiCad and running simulations. Each lesson includes both a raw SPICE netlist (for standalone ngspice use) and detailed instructions for building the equivalent schematic in KiCad's graphical environment.

## Two Simulation Approaches

Throughout this curriculum, you can simulate circuits using either method:

### Method A: Standalone ngspice (Command Line)

Run netlists directly without building schematics—fastest for iterating on component values.

```bash
# Save the netlist as a .cir file and run:
ngspice -b simulation/testbenches/circuit_name.cir

# For interactive mode with plotting:
ngspice simulation/testbenches/circuit_name.cir
```

### Method B: KiCad Integrated Simulation

Build the schematic graphically, then simulate from within KiCad—best for documentation and eventual PCB design.

## KiCad Simulation Symbol Library

KiCad 8.0 includes a dedicated `Simulation_SPICE` library with components pre-configured for simulation. **Always use these symbols for simulation work:**

| Symbol | Library Location | Purpose |
|--------|------------------|---------|
| `VSOURCE` | Simulation_SPICE:VSOURCE | Voltage source (DC, AC, PULSE, SIN) |
| `ISOURCE` | Simulation_SPICE:ISOURCE | Current source |
| `R` | Simulation_SPICE:R | Resistor |
| `C` | Simulation_SPICE:C | Capacitor |
| `L` | Simulation_SPICE:L | Inductor |
| `D` | Simulation_SPICE:D | Diode |
| `NMOS` | Simulation_SPICE:NMOS | N-channel MOSFET |
| `PMOS` | Simulation_SPICE:PMOS | P-channel MOSFET |
| `NPN` | Simulation_SPICE:NPN | NPN BJT |
| `PNP` | Simulation_SPICE:PNP | PNP BJT |
| `OPAMP` | Simulation_SPICE:OPAMP | Ideal op-amp |

> **[PHOTO PLACEHOLDER: Screenshot of KiCad symbol chooser showing Simulation_SPICE library]**

## Essential KiCad Simulation Setup

### Step 1: Configure SPICE Model Paths

1. Open **Preferences → Configure Paths**
2. Add a new path variable: `SPICE_LIB_DIR`
3. Set value to your models directory: `${KIPRJMOD}/simulation/models`

> **[PHOTO PLACEHOLDER: Screenshot of KiCad path configuration dialog]**

### Step 2: Create a Simulation Schematic

1. **File → New → Schematic** (or create a new sheet in your project)
2. Name it descriptively: `sim_gate_drive_comparison.kicad_sch`
3. Add components from `Simulation_SPICE` library
4. **Critical:** Always include a ground symbol (GND or 0) — ngspice requires node 0

### Step 3: Configure Component Values

Double-click each component to edit its properties:

**For passive components (R, L, C):**
- Set the `Value` field directly: `150`, `10u`, `2.7n`
- Units: Use SPICE notation (p=pico, n=nano, u=micro, m=milli, k=kilo, MEG=mega)

**For voltage/current sources:**
- Edit the `Value` field with the source specification
- DC source: `DC 3.3` or just `3.3`
- Pulse source: `PULSE(0 15 0 10n 10n 5u 10u)`
  - Format: `PULSE(V1 V2 Tdelay Trise Tfall Ton Tperiod)`
- Sine source: `SIN(0 170 60)`
  - Format: `SIN(Voffset Vamplitude Frequency)`
- AC source: `AC 1` (for frequency sweep analysis)

> **[PHOTO PLACEHOLDER: Screenshot of VSOURCE properties dialog with PULSE configuration]**

**For semiconductors:**
- Set the `Sim.Device` field to match the SPICE model type
- Set the `Sim.Pins` field to define pin order (e.g., `1=C 2=B 3=E` for BJT)
- Reference external models with `Sim.Library` field

### Step 4: Add SPICE Directives

Add simulation commands as text on the schematic:

1. **Place → Add Text** (or press `T`)
2. Type your SPICE directive
3. Check **"Simulation directive"** checkbox in the text properties

Common directives:

```spice
* Transient analysis: .tran <step> <stop> [start] [UIC]
.tran 1n 20u

* AC analysis: .ac <dec/oct/lin> <points> <fstart> <fstop>
.ac dec 100 1 10MEG

* DC operating point
.op

* DC sweep: .dc <source> <start> <stop> <step>
.dc V1 0 5 0.1

* Parameter sweep: .step param <name> <start> <stop> <step>
.step param Rval 1k 10k 1k

* Include external model file
.include {SPICE_LIB_DIR}/IKW40N120H3.lib

* Define a model
.model LED_MODEL D(Is=1e-20 N=1.5 Rs=0.5 Vj=1.8)

* Measurement (results appear in simulation log)
.meas tran Ipeak MAX I(R1)
.meas tran Trise TRIG V(out) VAL=0.1 RISE=1 TARG V(out) VAL=0.9 RISE=1
```

> **[PHOTO PLACEHOLDER: Screenshot showing SPICE directive text on schematic with checkbox enabled]**

### Step 5: Assign Net Labels for Probing

Assign meaningful labels to nets you want to probe:

1. **Place → Label** (or press `L`)
2. Type a descriptive name: `gate_weak`, `Vout`, `Itank`
3. Place on the wire

These labels become the node names in simulation—you'll reference them when plotting.

### Step 6: Run the Simulation

1. **Inspect → Simulator** (or click the oscilloscope icon)
2. The Simulation window opens
3. Click **Run/Stop Simulation** (play button) or press `R`
4. Wait for simulation to complete (progress shown in status bar)

> **[PHOTO PLACEHOLDER: Screenshot of KiCad Simulator window with Run button highlighted]**

### Step 7: Plot Results

After simulation completes:

1. **Add Signals:** Click **Add Signals** or press `A`
2. Select signals from the list (your net labels appear here)
3. **Voltage:** Select `V(net_name)` 
4. **Current:** Select `I(component_ref)` — e.g., `I(R1)` for current through R1
5. **Power:** Use expression: `V(node)*I(Rload)`

**Cursor Measurements:**
- Click on waveform to place cursor
- Press `C` to add a second cursor
- Delta values shown in cursor panel

> **[PHOTO PLACEHOLDER: Screenshot of waveform plot with two cursors showing rise time measurement]**

### Step 8: Export Results

**Export waveform data:**
1. **File → Export to CSV** in simulator window
2. Choose signals to export
3. Save as `.csv` for external analysis

**Export plot image:**
1. Right-click on plot area
2. **Export to PNG/SVG**

---

## Working with External SPICE Models

Many components require manufacturer-provided models. Here's how to integrate them:

### Subcircuit Models (.lib or .sub files)

1. Download the model file from manufacturer website
2. Place in `/simulation/models/` directory
3. Add include directive to schematic:
   ```spice
   .include {SPICE_LIB_DIR}/IKW40N120H3.lib
   ```
4. Create a symbol or use generic symbol with proper `Sim.Device` assignment

### Creating a KiCad Symbol for a SPICE Subcircuit

1. **Symbol Editor → File → New Symbol**
2. Draw the symbol outline (rectangle for ICs, standard shapes for discretes)
3. Add pins matching the subcircuit definition order
4. In Symbol Properties:
   - `Sim.Device`: `SUBCKT`
   - `Sim.Pins`: `1=C 2=G 3=E` (map symbol pins to subcircuit pins)
   - `Sim.Library`: `{SPICE_LIB_DIR}/IKW40N120H3.lib`
   - `Sim.Name`: `IKW40N120H3` (must match .subckt name in file)

> **[PHOTO PLACEHOLDER: Screenshot of symbol properties showing Sim.* fields]**

### Behavioral Sources (B-sources)

For complex behaviors not covered by standard models, use behavioral sources:

```spice
* Voltage-controlled voltage source (equation-based)
B1 out 0 V = V(in) > 1.5 ? 5 : 0

* Voltage-controlled current source
B2 out 0 I = V(ctrl) * 0.001

* Using IF-THEN-ELSE
B3 out 0 V = IF(V(in) > V(ref), V(vdd), 0)
```

To add in KiCad:
1. Use `Simulation_SPICE:B` symbol (behavioral source)
2. Set the `Value` field to the expression

---

## Common Simulation Pitfalls and Solutions

| Problem | Symptom | Solution |
|---------|---------|----------|
| Missing ground | "No node 0 found" error | Add GND symbol connected to circuit |
| Floating node | "Singular matrix" error | Add high-value resistor to ground (1GΩ) |
| Convergence failure | "Time step too small" | Add `.options reltol=0.003` or reduce source slew rates |
| No DC path to ground | Simulation won't start | Add DC bias resistors, check capacitor-coupled inputs |
| Wrong node names | Signals not found | Check net labels match exactly (case-sensitive) |
| Model not found | ".include file not found" | Verify path in Configure Paths, check filename spelling |
| Initial conditions | Strange startup behavior | Add `UIC` to `.tran` and set `IC=` on capacitors/inductors |

### Helpful ngspice Options

Add these directives to improve simulation robustness:

```spice
* Relaxed convergence tolerances (for power electronics)
.options reltol=0.003
.options abstol=1e-9
.options vntol=1e-4
.options chgtol=1e-14

* Increase iteration limits
.options itl1=500
.options itl2=200
.options itl4=100

* Gear integration method (better for stiff circuits)
.options method=gear

* Set default initial conditions to zero
.options uic
```

---

## Quick Reference: SPICE Source Specifications

### Voltage/Current Source Formats

```spice
* DC Source
Vname n+ n- DC <value>
Vname n+ n- <value>

* AC Source (for .ac analysis)
Vname n+ n- AC <magnitude> [phase]

* Pulse Source
Vname n+ n- PULSE(V1 V2 Tdelay Trise Tfall Ton Tperiod [Ncycles])
* V1=initial, V2=pulsed, delays and times in seconds

* Sinusoidal Source
Vname n+ n- SIN(Voffset Vampl Freq [Td] [Damping] [Phase])

* Piecewise Linear Source
Vname n+ n- PWL(T1 V1 T2 V2 T3 V3 ...)

* Exponential Source
Vname n+ n- EXP(V1 V2 Td1 Tau1 Td2 Tau2)
```

### Example Source Configurations

```spice
* 3.3V DC supply
Vcc vcc 0 DC 3.3

* 35kHz square wave, 50% duty, 0-15V, 100ns edges
Vgate gate 0 PULSE(0 15 0 100n 100n 14.2u 28.5u)

* 60Hz AC mains (120Vrms = 170V peak)
Vac ac_hot 0 SIN(0 170 60)

* Load step: 0.1A for 1ms, then 0.6A
Iload vout 0 PWL(0 0.1 1m 0.1 1.001m 0.6 5m 0.6)
```

---

# Phase I: Simulation Environment & Component Characterization

This foundational phase establishes the simulation infrastructure and characterizes every critical component through SPICE modeling. No hardware is purchased until all models are validated against datasheet specifications.

---

## Lesson 01: The Engineering Environment & Hierarchical Project Architecture

### Objective

Establish a version-controlled, hierarchical KiCad 8.0 project structure integrated with ngspice for seamless schematic-to-simulation workflow.

### Theory: Why Hierarchy Matters

In professional hardware design, "flat" schematics are dangerous—they obscure signal flow and prevent effective isolation management. Hierarchical sheets create strict logical boundaries where signals can only pass between sheets through explicitly placed hierarchical pins. This enforces modular design and makes simulation of individual subsystems straightforward.

The hierarchical approach mirrors software engineering principles: each sheet becomes a "module" with defined inputs and outputs, enabling independent testing and validation before integration.

### Simulation Exercise: Project Setup

**Step 1: Create Project Structure**

Open KiCad 8.0 → File → New Project. Name it `Induction_Core_v1`. Create the following subdirectory structure:

```
/Induction_Core_v1/
├── /datasheets/      # PDFs of critical components
├── /simulation/      # SPICE models, netlists, results
│   ├── /models/      # .lib and .sub files
│   ├── /testbenches/ # Individual circuit tests
│   └── /results/     # Waveform exports, data
├── /libraries/       # Custom symbols/footprints
├── /output/          # Gerbers, BOM (Phase V)
└── /docs/            # Design notes, calculations
```

> **[PHOTO PLACEHOLDER: Screenshot of KiCad project tree showing directory structure]**

**Step 2: Hierarchical Sheet Implementation**

Open the root schematic. Create five hierarchical sheets using the `S` shortcut:

1. **Power_Input:** AC mains input, rectification, EMI filtering, soft-start
2. **Resonant_Tank:** Half-bridge IGBTs, gate drivers, LC tank, current sensing
3. **Aux_Power:** 24V→5V buck, 5V→3.3V LDO, UCC14140-Q1 isolated supply for high-side
4. **MCU_Control:** ESP32-S3, crystal, strapping, programming header
5. **Sensing_UI:** Temperature sensing, user interface, safety interlocks

Connect sheets using hierarchical labels. Example: Create `PWM_H` (High-Side PWM) exiting MCU_Control and entering Resonant_Tank.

> **[PHOTO PLACEHOLDER: Screenshot of root schematic showing five hierarchical sheets with interconnecting labels]**

**Step 3: ngspice Integration**

KiCad 8.0 includes native ngspice integration. Configure the simulator:

1. Open Preferences → Configure Paths
2. Add `SPICE_LIB_DIR` pointing to `/simulation/models/`
3. Verify ngspice is detected under Preferences → Simulator

### Automation: Build Scripts

Create automation scripts for reproducible simulation runs:

```bash
#!/bin/bash
# run_simulation.sh - Execute ngspice simulation
ngspice -b simulation/testbenches/$1.cir -o simulation/results/$1.log
```

### Validation Checkpoint

Before proceeding to Lesson 02, verify:

- [ ] All five hierarchical sheets created and labeled
- [ ] ngspice launches correctly from KiCad
- [ ] Directory structure matches specification

> **[PHOTO PLACEHOLDER: Screenshot of ngspice launching from KiCad with test circuit]**

---

## Lesson 02: SPICE Fundamentals — The Passive Signaler

### Objective

Establish trust in the simulator by correlating a simple R-LED network simulation with theoretical calculations. This foundational exercise validates that the simulation environment produces accurate results.

### Theory: The Netlist as Ground Truth

The netlist is the mathematical description of the circuit—a list of nodes and components with their values that the simulator processes. Understanding that the netlist (not the schematic drawing) defines the physics is the philosophical foundation of simulation-first design.

A simple netlist for an LED circuit:

```spice
* LED Current Limiter Test
V1 vcc 0 DC 3.3
R1 vcc led_anode 150
D1 led_anode 0 LED_MODEL
.model LED_MODEL D(Is=1e-20 N=1.5 Rs=0.5 Vj=1.8)
.op
.end
```

---

### Building This Circuit in KiCad

Follow these step-by-step instructions to create the LED test circuit schematic:

#### Step 1: Create New Schematic

1. In your project, right-click in the project tree → **New → Schematic**
2. Name it `sim_02_led_test.kicad_sch`
3. Double-click to open the schematic editor

#### Step 2: Place Components

Press `A` to open the symbol chooser. Add these components from `Simulation_SPICE` library:

| Component | Library:Symbol | Quantity |
|-----------|---------------|----------|
| Voltage Source | `Simulation_SPICE:VSOURCE` | 1 |
| Resistor | `Simulation_SPICE:R` | 1 |
| Diode | `Simulation_SPICE:D` | 1 |
| Ground | `power:GND` | 1 |

**Placement layout:**
```
    +-- R1 --+-- D1 --+
    |        |        |
   V1      (led_anode)|
    |                 |
    +-------GND-------+
```

#### Step 3: Wire the Circuit

1. Press `W` to enter wiring mode
2. Connect V1 positive terminal to R1
3. Connect R1 to D1 anode (the flat bar side of the symbol)
4. Connect D1 cathode to GND
5. Connect V1 negative terminal to GND

#### Step 4: Add Net Label

1. Press `L` to add a label
2. Type `led_anode`
3. Place on the wire between R1 and D1
4. This allows you to probe this node by name in simulation

#### Step 5: Configure Component Values

**Double-click V1 (voltage source):**
- Set `Value` field to: `DC 3.3`

**Double-click R1 (resistor):**
- Set `Value` field to: `150`

**Double-click D1 (diode):**
- Set `Value` field to: `LED_MODEL`
- Set `Sim.Device` field to: `D`
- Set `Sim.Pins` field to: `1=K 2=A` (verify pin order matches symbol)

#### Step 6: Add SPICE Directives

1. Press `T` to add text
2. Type the model definition:
   ```spice
   .model LED_MODEL D(Is=1e-20 N=1.5 Rs=0.5 Vj=1.8)
   ```
3. In text properties, check **"Simulation directive"** checkbox
4. Click OK and place near the circuit

5. Add another text directive for analysis:
   ```spice
   .tran 10u 10m
   ```
6. Again, check **"Simulation directive"** checkbox

> **[PHOTO PLACEHOLDER: Complete LED test schematic in KiCad with all components and directives]**

#### Step 7: Run Simulation

1. Press `F5` or go to **Inspect → Simulator**
2. In the Simulator window, click the **Run** button (play icon)
3. Wait for simulation to complete (status bar shows progress)

#### Step 8: Plot Results

1. Click **Add Signals** button
2. From the signal list, select:
   - `V(led_anode)` — voltage at the LED anode
   - `I(R1)` — current through the resistor (equals LED current)
3. Click **OK**

**Verify the results:**
- `I(R1)` should stabilize at approximately **10mA** (0.01A)
- `V(led_anode)` should be approximately **1.8V** (the LED forward voltage)

> **[PHOTO PLACEHOLDER: KiCad Simulator showing I(R1) waveform at ~10mA]**

#### Step 9: Measure with Cursors

1. Click on the `I(R1)` waveform to place cursor A
2. Press `C` to add cursor B
3. Move cursor B to the steady-state region
4. Read the current value from the cursor panel

---

### Running as Standalone Netlist

Alternatively, save this as `sim_02_led_test.cir` and run from command line:

```bash
# Batch mode (runs and exits)
ngspice -b simulation/testbenches/sim_02_led_test.cir

# Interactive mode (allows plotting)
ngspice simulation/testbenches/sim_02_led_test.cir

# In ngspice interactive mode:
ngspice> run
ngspice> plot i(R1)
ngspice> plot v(led_anode)
ngspice> meas tran Iled AVG i(R1) FROM=5m TO=10m
```

---

### Simulation Exercise: The "Hello World" of SPICE

**Step 1: Theoretical Calculation**

Before simulating, calculate the expected LED current:

$$I_f = \frac{V_{source} - V_f}{R} = \frac{3.3V - 1.8V}{150\Omega} = 10mA$$

This hand calculation becomes the validation target for the simulation.

**Step 2: Schematic Entry**

In KiCad, create a new schematic sheet `test_led.kicad_sch`:

1. Place VSOURCE (set to 3.3V DC)
2. Place R (150Ω)
3. Place D (generic diode symbol)
4. Add ground reference (critical—ngspice requires node 0)

> **[PHOTO PLACEHOLDER: Screenshot of LED test circuit schematic in KiCad]**

**Step 3: SPICE Model Assignment**

The diode needs a SPICE model. Add this directive as a text element on the schematic:

```spice
.model LED_MODEL D(Is=1e-20 N=1.5 Rs=0.5 Vj=1.8)
```

Assign this model to the diode symbol via the "Spice Model" field in symbol properties.

**Step 4: Simulation Directive**

Add the analysis directive to the schematic canvas:

```spice
.tran 10u 10m
```

This runs a transient analysis with 10µs time step for 10ms duration.

**Step 5: Run and Validate**

Open Inspect → Simulator. Run the simulation. Plot the current through R1. The steady-state value should be **10mA ±5%**. If the result deviates significantly, check:

- Model parameters (especially Vj for forward voltage)
- Ground connection (node 0 must exist)
- Component values match schematic

> **[PHOTO PLACEHOLDER: Screenshot of ngspice waveform showing LED current stabilizing at ~10mA]**

### Extended Exercise: Temperature Sweep

Diodes are temperature-sensitive. Add a temperature sweep to understand thermal behavior:

```spice
.temp 25 50 75 100
```

Run the simulation and observe how the forward voltage (and thus current) changes with temperature. Document the relationship—this becomes important for the temperature sensing circuits.

> **[PHOTO PLACEHOLDER: Chart showing LED current vs temperature sweep results]**

### Validation Checkpoint

- [ ] Simulated current matches calculated value within 5%
- [ ] Temperature sweep shows expected Vf decrease with increasing temperature
- [ ] Student can explain netlist ↔ schematic correspondence

---

## Lesson 03: The Gate Charge Model — Understanding Switching Speed

### Objective

Simulate the capacitive loading of a MOSFET/IGBT gate to quantify the need for high-current gate drivers. This lesson establishes why direct MCU pin drive is inadequate for power switches.

### Theory: The Miller Plateau

The IGBT gate acts as a nonlinear capacitor (Ciss). Switching speed (dt) is determined by the rate at which charge (Qg) is delivered to the gate. The gate charge curve exhibits three distinct regions:

1. **Region 1 (Vgs < Vth):** Charging Ciss—gate voltage rises quickly
2. **Region 2 (Miller Plateau):** Cgd absorbs charge as Vds falls—gate voltage stalls
3. **Region 3 (Vgs > plateau):** Final Ciss charging to drive voltage

During the Miller Plateau, a slow, high-impedance driver causes the switch to dwell in the linear region where both Vce and Ic are high, leading to catastrophic switching losses:

$$P_{switching} = V_{ce} \times I_c \times t_{dwell} \times f_{sw}$$

> **[PHOTO PLACEHOLDER: Diagram showing gate charge curve with three regions labeled]**

### Simulation Exercise: Weak vs. Strong Gate Drive

**Step 1: Create Gate Capacitance Model**

The IKW40N120H3 has approximately Ciss = 2.7nF (from datasheet). Create a simplified testbench:

```spice
* Gate Drive Comparison Testbench

* Weak drive (MCU pin simulation)
V_weak pulse_in 0 PULSE(0 3.3 0 10n 10n 5u 10u)
R_weak pulse_in gate_weak 1k
C_gate_weak gate_weak 0 2.7n

* Strong drive (gate driver simulation)
V_strong pulse_in2 0 PULSE(0 15 0 10n 10n 5u 10u)
R_strong pulse_in2 gate_strong 5
C_gate_strong gate_strong 0 2.7n

.tran 1n 20u
.end
```

---

### Building This Circuit in KiCad

This circuit compares two RC networks side-by-side to visualize the dramatic difference between weak and strong gate drive.

#### Step 1: Create New Schematic

1. Create new schematic: `sim_03_gate_drive_comparison.kicad_sch`

#### Step 2: Place Components

You'll build two parallel circuits. From `Simulation_SPICE` library, place:

| Component | Quantity | Purpose |
|-----------|----------|---------|
| `VSOURCE` | 2 | Pulse sources for each driver |
| `R` | 2 | Gate resistors (1kΩ and 5Ω) |
| `C` | 2 | Gate capacitance models |
| `GND` | 1 | Common ground reference |

**Layout (two parallel RC networks):**
```
   V_weak               V_strong
     |                     |
   R_weak(1k)          R_strong(5)
     |                     |
  [gate_weak]         [gate_strong]
     |                     |
 C_gate_weak          C_gate_strong
     |                     |
    GND                   GND
```

#### Step 3: Wire Both Circuits

Wire each as a simple series RC circuit to ground. Keep the two circuits separated but sharing the same ground.

#### Step 4: Add Net Labels for Probing

Place labels on the key nodes:
- `pulse_in` — output of V_weak
- `gate_weak` — junction of R_weak and C_gate_weak  
- `pulse_in2` — output of V_strong
- `gate_strong` — junction of R_strong and C_gate_strong

#### Step 5: Configure Component Values

**V_weak (weak driver source):**
- Double-click and set `Value` to:
  ```
  PULSE(0 3.3 0 10n 10n 5u 10u)
  ```

**V_strong (strong driver source):**
- Set `Value` to:
  ```
  PULSE(0 15 0 10n 10n 5u 10u)
  ```

**Pulse parameters explained:**
| Parameter | Value | Meaning |
|-----------|-------|---------|
| V1 | 0 | Initial voltage |
| V2 | 3.3 or 15 | Pulse voltage |
| Tdelay | 0 | Start immediately |
| Trise | 10n | 10ns rise time |
| Tfall | 10n | 10ns fall time |
| Ton | 5u | 5µs pulse width |
| Tperiod | 10u | 10µs period (100kHz) |

**R_weak:** Set `Value` to `1k`

**R_strong:** Set `Value` to `5`

**C_gate_weak:** Set `Value` to `2.7n`

**C_gate_strong:** Set `Value` to `2.7n`

#### Step 6: Add Simulation Directive

Add text with **"Simulation directive"** checked:
```spice
.tran 1n 20u
```

This runs a 20µs transient with 1ns resolution—sufficient to capture the fast edges.

> **[PHOTO PLACEHOLDER: Complete gate drive comparison schematic in KiCad]**

#### Step 7: Run and Plot

1. Open Simulator (`F5`)
2. Run simulation
3. Add signals: `V(gate_weak)` and `V(gate_strong)`
4. Both will appear on the same plot for easy comparison

**What you should see:**
- `V(gate_weak)`: Slow exponential rise, τ = 1kΩ × 2.7nF = 2.7µs
- `V(gate_strong)`: Fast exponential rise, τ = 5Ω × 2.7nF = 13.5ns

> **[PHOTO PLACEHOLDER: Overlaid waveforms showing dramatic rise time difference]**

#### Step 8: Measure Rise Times

Use cursors to measure 10%–90% rise time:

**For weak drive (3.3V output):**
- 10% level: 0.33V
- 90% level: 2.97V
- Place cursor A at 0.33V crossing
- Place cursor B at 2.97V crossing
- Read Δt from cursor panel
- **Expected: ~6µs**

**For strong drive (15V output):**
- 10% level: 1.5V
- 90% level: 13.5V
- **Expected: ~30ns**

---

### Running as Standalone Netlist

```bash
ngspice simulation/testbenches/sim_03_gate_drive.cir

# In ngspice:
ngspice> run
ngspice> plot v(gate_weak) v(gate_strong)

# Measure rise times automatically
ngspice> meas tran Trise_weak TRIG v(gate_weak) VAL=0.33 RISE=1 TARG v(gate_weak) VAL=2.97 RISE=1
ngspice> meas tran Trise_strong TRIG v(gate_strong) VAL=1.5 RISE=1 TARG v(gate_strong) VAL=13.5 RISE=1
```

---

**Step 2: Analyze Rise Times**

Run the simulation and measure the 10%-90% rise time for both cases:

| Drive Type | Resistance | Voltage | Expected Rise Time |
|------------|------------|---------|-------------------|
| Weak (MCU) | 1kΩ | 3.3V | ~6µs (τ = RC = 2.7µs) |
| Strong (Driver) | 5Ω | 15V | ~30ns |

> **[PHOTO PLACEHOLDER: Waveform comparison showing weak vs strong gate drive rise times]**

**Step 3: Calculate Switching Losses**

If the IGBT dwells in linear region for 6µs at Vce=200V, Ic=20A, and fsw=35kHz:

$$P_{loss} = 200V \times 20A \times 6\mu s \times 35kHz = 840W \text{ (catastrophic!)}$$

With proper gate drive (30ns dwell):

$$P_{loss} = 200V \times 20A \times 30ns \times 35kHz = 4.2W \text{ (acceptable)}$$

### Extended Exercise: Gate Resistor Optimization

Sweep the gate resistor from 2Ω to 20Ω and plot switching loss vs. EMI (dV/dt). Document the optimal value that balances efficiency against electromagnetic emissions.

```spice
.param Rgate=2
.step param Rgate 2 20 2
```

> **[PHOTO PLACEHOLDER: Chart showing switching loss and dV/dt vs gate resistance]**

### Validation Checkpoint

- [ ] Quantified switching loss difference: >100x between weak and strong drive
- [ ] Gate resistor sweep completed with documented optimal range
- [ ] Student can explain Miller plateau mechanism

---

## Lesson 04: IGBT Characterization — The IKW40N120H3 Model

### Objective

Create, import, and validate a functional SPICE subcircuit for the primary power switch. Characterize switching losses, tail current, and thermal behavior through simulation.

### Theory: IGBT vs. MOSFET

IGBTs combine a MOSFET input (voltage-controlled, high input impedance) with a BJT output (low Vce(sat) at high currents). Key differences affecting simulation:

- **Tail Current:** Minority carrier devices exhibit current "tail" at turn-off
- **Temperature Coefficient:** Positive for Vce(sat)—self-balancing in parallel
- **Switching Speed:** "High Speed 3" technology minimizes Eoff

The IKW40N120H3 datasheet specifies:

| Parameter | Value |
|-----------|-------|
| Vce(sat) @ 40A, 25°C | ~2.05V |
| Eoff @ 600V, 40A, 150°C | ~0.9mJ |
| RθJC | 0.35 K/W |
| Ciss | ~2700pF |

### Simulation Exercise: Model Acquisition and Validation

**Step 1: Obtain SPICE Model**

Download the manufacturer-provided SPICE model from Infineon's website. Place the `.lib` file in `/simulation/models/`. If a vendor model is unavailable, create a behavioral model:

```spice
.subckt IKW40N120H3 C G E
* Simplified IGBT model for educational use
M1 C G E E IGBT_MOS
Q1 C G E BJT_OUT
.model IGBT_MOS NMOS(VTO=5.8 KP=15 LAMBDA=0.01)
.model BJT_OUT NPN(BF=10 IS=1e-12)
.ends
```

**Step 2: Double Pulse Test Setup**

The Double Pulse Test is the industry-standard method for characterizing switching behavior. Create the testbench:

```spice
* Double Pulse Test for IKW40N120H3
Vbus bus 0 DC 400
L_load bus drain 100u
D_fwd drain bus FREEWHEEL

X1 drain gate 0 IKW40N120H3

* Gate drive: two pulses, second pulse captures turn-on
Vgate gate_in 0 PULSE(0 15 0 10n 10n 3u 10u)
R_gate gate_in gate 5

.include models/IKW40N120H3.lib
.model FREEWHEEL D(IS=1e-12 RS=0.01)
.tran 1n 15u
.end
```

---

### Building the Double Pulse Test in KiCad

The Double Pulse Test (DPT) is the gold standard for characterizing power semiconductors. This circuit applies two drive pulses: the first builds up current in the inductor, and the turn-off of the first pulse captures turn-off characteristics. The second pulse captures turn-on into an established current.

#### Step 1: Create New Schematic

Create: `sim_04_double_pulse_test.kicad_sch`

#### Step 2: Place Components

| Component | Library:Symbol | Reference | Purpose |
|-----------|---------------|-----------|---------|
| Voltage Source | `Simulation_SPICE:VSOURCE` | Vbus | 400V DC bus |
| Voltage Source | `Simulation_SPICE:VSOURCE` | Vgate | Gate pulse source |
| Inductor | `Simulation_SPICE:L` | L_load | Current buildup inductor |
| Diode | `Simulation_SPICE:D` | D_fwd | Freewheeling diode |
| Resistor | `Simulation_SPICE:R` | R_gate | Gate resistor |
| IGBT | Custom symbol (see below) | X1 | Device under test |
| Ground | `power:GND` | | Reference |

**Circuit topology:**
```
        Vbus (400V)
            |
       +----+----+
       |         |
    L_load     D_fwd
    (100µH)    (flyback)
       |         |
       +----+----+
            |
         [drain]
            |
      +-----+-----+
      |     C     |
      |    IGBT   |
      G     X1    E
      |           |
   R_gate        GND
   (5Ω)
      |
   Vgate
      |
     GND
```

#### Step 3: Create Custom IGBT Symbol (if needed)

If using a manufacturer subcircuit model, create a symbol:

1. **Symbol Editor → File → New Symbol**
2. Create in your project library: `Induction_Core_v1.kicad_sym`
3. Name: `IKW40N120H3`
4. Draw outline (rectangle) with pins:
   - Pin 1: `C` (Collector) — top
   - Pin 2: `G` (Gate) — left
   - Pin 3: `E` (Emitter) — bottom

5. **Edit symbol properties** (important!):
   ```
   Sim.Device = SUBCKT
   Sim.Pins = 1=C 2=G 3=E
   Sim.Library = {SPICE_LIB_DIR}/IKW40N120H3.lib
   Sim.Name = IKW40N120H3
   ```

> **[PHOTO PLACEHOLDER: IGBT symbol properties showing Sim.* fields]**

**Alternative: Using the behavioral model**

If you don't have a manufacturer model, add this as a SPICE directive on your schematic instead of a symbol:

```spice
.subckt IKW40N120H3 C G E
M1 C G E E IGBT_MOS
Q1 C G E BJT_OUT
.model IGBT_MOS NMOS(VTO=5.8 KP=15 LAMBDA=0.01)
.model BJT_OUT NPN(BF=10 IS=1e-12)
.ends
```

Then use a generic 3-pin component configured to reference this subcircuit.

#### Step 4: Wire the Circuit

1. Connect Vbus positive to one end of L_load
2. Connect L_load other end to D_fwd cathode AND IGBT collector (node: `drain`)
3. Connect D_fwd anode back to Vbus positive (freewheeling path)
4. Connect IGBT emitter to GND
5. Connect Vgate through R_gate to IGBT gate
6. Connect Vbus negative and Vgate negative to GND

#### Step 5: Add Net Labels

Essential labels for probing:
- `bus` — the 400V rail
- `drain` — IGBT collector / inductor output (critical for Vce measurement)
- `gate` — IGBT gate (after R_gate)
- `gate_in` — Vgate output (before R_gate)

#### Step 6: Configure Sources

**Vbus (DC bus supply):**
```
Value: DC 400
```

**Vgate (double pulse):**
For a proper double-pulse test, you need two pulses. Use PWL (piecewise linear) for precise control:

```
Value: PWL(0 0 100n 15 3u 15 3.1u 0 7u 0 7.1u 15 10u 15 10.1u 0 15u 0)
```

This creates:
- 0–100ns: Ramp to 15V (first pulse starts)
- 100ns–3µs: Hold at 15V (first pulse on)
- 3µs–3.1µs: Ramp to 0V (first pulse turn-off — **capture this!**)
- 3.1µs–7µs: Hold at 0V (off time, current freewheels)
- 7µs–7.1µs: Ramp to 15V (second pulse turn-on — **capture this!**)
- 7.1µs–10µs: Hold at 15V (second pulse on)
- 10µs–10.1µs: Ramp to 0V (second pulse off)

**Alternative using PULSE:**
For simpler setup (single pulse period, captures one turn-on/turn-off):
```
Value: PULSE(0 15 0 10n 10n 3u 10u)
```

#### Step 7: Configure Passive Components

**L_load:** `Value: 100u`

**R_gate:** `Value: 5`

**D_fwd:** Configure as fast diode
- `Value: FREEWHEEL`
- Add model directive:
  ```spice
  .model FREEWHEEL D(IS=1e-12 RS=0.01 TT=50n)
  ```

#### Step 8: Add All Directives

Add these as simulation directive text blocks:

```spice
.include {SPICE_LIB_DIR}/IKW40N120H3.lib
```

```spice
.model FREEWHEEL D(IS=1e-12 RS=0.01 TT=50n)
```

```spice
.tran 1n 15u
```

```spice
.options reltol=0.003
```

The last directive helps with convergence in power electronics simulations.

> **[PHOTO PLACEHOLDER: Complete Double Pulse Test schematic in KiCad]**

#### Step 9: Run Simulation

1. Open Simulator (`F5`)
2. Click Run
3. Simulation may take 10-30 seconds due to the fast transients

#### Step 10: Analyze Turn-Off (First Pulse)

Add these signals:
- `V(drain)` — IGBT Vce (collector-emitter voltage)
- `V(gate)` — Gate voltage
- `I(L_load)` — Collector current (same as inductor current)

**Zoom to first turn-off (around 3µs):**
1. In plot, use mouse scroll to zoom
2. Or right-click → Set Time Range: 2.5µs to 4.5µs

**Observe:**
- Vce rises as IGBT turns off
- Current "tail" as minority carriers recombine
- Any voltage overshoot (must stay below 1200V!)

#### Step 11: Measure Switching Energy

Add a measurement directive:

```spice
.meas tran Eoff INTEG V(drain)*I(L_load) FROM=2.9u TO=3.5u
```

Or calculate manually:
1. Plot `V(drain)*I(L_load)` (instantaneous power)
2. Integrate the area under the curve during switching
3. This gives turn-off energy in Joules

> **[PHOTO PLACEHOLDER: Waveforms showing Vce, Ic, and instantaneous power during turn-off]**

#### Step 12: Analyze Turn-On (Second Pulse)

Zoom to second pulse turn-on (around 7µs).

**Observe:**
- Current rises first (into clamped inductor)
- Vce falls after current is established
- Turn-on losses (overlap of V and I)

---

### Running as Standalone Netlist

Save as `sim_04_double_pulse.cir`:

```bash
ngspice simulation/testbenches/sim_04_double_pulse.cir

# In ngspice interactive:
ngspice> run
ngspice> plot v(drain) v(gate)
ngspice> plot i(L_load)

# Plot instantaneous power
ngspice> plot v(drain)*i(L_load)

# Measure turn-off energy
ngspice> meas tran Eoff INTEG v(drain)*i(L_load) FROM=2.9u TO=3.5u

# Measure peak Vce
ngspice> meas tran Vce_peak MAX v(drain)

# Measure tail current duration (90% to 10% of peak)
ngspice> let Ipeak = maximum(i(L_load))
ngspice> meas tran t90 WHEN i(L_load)=0.9*Ipeak FALL=1
ngspice> meas tran t10 WHEN i(L_load)=0.1*Ipeak FALL=1
ngspice> print t10-t90
```

---

> **[PHOTO PLACEHOLDER: Schematic diagram of Double Pulse Test circuit]**

**Step 3: Analyze Turn-Off Characteristics**

Focus on the first pulse turn-off event. Measure:

1. **Tail current duration:** Time from 90% to 10% of peak Ic
2. **Vce overshoot:** Peak voltage during switching (must stay below 1200V rating)
3. **Eoff calculation:** Integrate P = Vce × Ic during turn-off

Use ngspice's measurement capability:

```spice
.meas tran Eoff INTEG V(drain)*I(X1.C) FROM=3.9u TO=4.5u
```

> **[PHOTO PLACEHOLDER: Waveforms showing Vce, Ic, and instantaneous power during turn-off]**

**Step 4: Validate Against Datasheet**

Compare simulation results with datasheet values:

| Parameter | Datasheet | Simulation |
|-----------|-----------|------------|
| Eoff @ 40A | 0.9 mJ | [measured] |
| Vce(sat) @ 40A | 2.05 V | [measured] |
| Tail time | ~200 ns | [measured] |

If simulation deviates by more than 20% from datasheet, adjust model parameters or obtain an updated model from the manufacturer.

### Extended Exercise: SOA Verification

Create a Safe Operating Area (SOA) plot by sweeping Vce and Ic. Overlay the datasheet SOA curve and verify all operating points remain within safe limits.

> **[PHOTO PLACEHOLDER: SOA plot with simulated operating points overlaid on datasheet limits]**

### Validation Checkpoint

- [ ] Eoff within 20% of datasheet specification
- [ ] Tail current duration documented
- [ ] Vce overshoot remains below 80% of rating (960V)
- [ ] Model file committed to `/simulation/models/`

---

## Lesson 05: Gate Driver Characterization — The UCC21550

### Objective

Simulate the propagation delay, isolation barrier characteristics, and dead-time generation of the gate driver IC. Validate that hardware-enforced dead time prevents shoot-through under all conditions.

### Theory: Isolation and CMTI

The UCC21550 provides galvanic isolation between the control logic (referenced to system ground) and the gate drive outputs (high-side referenced to switching node). Key specifications:

| Parameter | Value | Significance |
|-----------|-------|--------------|
| CMTI | >100V/ns | Prevents false triggering from dV/dt |
| Propagation delay | 30ns typical | Matched between channels |
| UVLO | ~12V | Prevents weak gate drive |
| Hardware dead time | Programmable | Fail-safe against software bugs |

The hardware dead-time feature is critical—it provides a fail-safe against software bugs that might otherwise cause simultaneous conduction (shoot-through).

### Simulation Exercise: Dead Time Verification

**Step 1: Create UCC21550 Behavioral Model**

Since detailed SPICE models for gate drivers are often unavailable, create a behavioral model:

```spice
.subckt UCC21550 INA INB OUTA OUTB VDD1 VDD2 GND1 GND2 DT
* Behavioral model - captures delay and dead time
* Calculate dead time from Rdt: tdt ≈ Rdt × 50pF

* Input buffers with propagation delay
A_ina [INA] [ina_del] buf tpd=30n
A_inb [INB] [inb_del] buf tpd=30n

* Dead time logic (simplified)
B_outa OUTA GND1 V = V(ina_del) > 1.5 & V(inb_del) < 1.5 ? V(VDD2) : 0
B_outb OUTB GND2 V = V(inb_del) > 1.5 & V(ina_del) < 1.5 ? V(VDD2) : 0
.ends
```

**Step 2: Dead Time Sweep Testbench**

Create a testbench that intentionally provides overlapping input pulses (simulating a software failure):

```spice
* Dead Time Verification Test
Vdd1 vdd1 0 DC 5
Vdd2 vdd2 0 DC 15

* Intentionally overlapping pulses (DANGEROUS without dead time!)
Vina ina 0 PULSE(0 5 0 10n 10n 500n 1u)
Vinb inb 0 PULSE(0 5 20n 10n 10n 500n 1u)  ; Note: overlaps!

* Dead time resistor (sweep this)
.param Rdt=20k
Rdt dt 0 {Rdt}

X1 ina inb outa outb vdd1 vdd2 0 0 dt UCC21550

.step param Rdt 10k 100k 10k
.tran 100p 2u
.end
```

> **[PHOTO PLACEHOLDER: Schematic of dead time test circuit]**

**Step 3: Analyze Results**

For each Rdt value, measure the minimum time between OUTA falling and OUTB rising (and vice versa). Create a table:

| Rdt (kΩ) | Dead Time (ns) | Overlap? | Status |
|----------|----------------|----------|--------|
| 10 | [measured] | [Y/N] | [SAFE/DANGER] |
| 20 | [measured] | [Y/N] | [SAFE/DANGER] |
| 50 | [measured] | [Y/N] | [SAFE/DANGER] |
| 100 | [measured] | [Y/N] | [SAFE/DANGER] |

Select an Rdt value that provides **at least 300ns dead time** to account for component tolerances and IGBT tail current.

> **[PHOTO PLACEHOLDER: Waveform showing OUTA and OUTB with dead time gap clearly visible]**

### Extended Exercise: CMTI Stress Test

Add a fast dV/dt transient to the high-side reference and verify the driver does not glitch:

```spice
* Add switching node voltage transient
Vsw sw 0 PULSE(0 400 500n 5n 5n 400n 1u)  ; 80V/ns
```

### Validation Checkpoint

- [ ] Dead time vs. Rdt relationship documented
- [ ] Minimum Rdt for 300ns dead time identified
- [ ] No overlap under intentional software fault condition
- [ ] CMTI test shows no false triggering at 80V/ns

---

## Lesson 06: Wide-Vin Buck Converter — The LMR51430

### Objective

Simulate the 24V→5V auxiliary power supply, verifying stability, transient response, and start-up behavior. This supply powers all digital logic and must maintain regulation under load transients.

### Theory: Buck Converter Fundamentals

The buck converter steps down voltage through switching action. Key design equations:

$$D = \frac{V_{out}}{V_{in}} = \frac{5V}{24V} \approx 0.21$$

$$L = \frac{V_{out} \times (1-D)}{\Delta I_L \times f_{sw}}$$

$$C_{out} = \frac{\Delta I_L}{8 \times f_{sw} \times \Delta V_{out}}$$

For the LMR51430 at fsw = 1.1MHz with 30% ripple current target and 50mV output ripple:

- L ≈ 10µH
- Cout ≈ 22µF (ceramic, low ESR)

### Simulation Exercise: Transient Response Validation

**Step 1: Obtain/Create SPICE Model**

Texas Instruments provides TINA-TI models for most power ICs. Download and convert, or use the averaged model approach:

```spice
* LMR51430 Averaged Model (simplified)
.subckt LMR51430 VIN SW GND FB
* Internal error amplifier
E_ea comp 0 VALUE = {10000 * (0.8 - V(FB))}
* PWM comparator (averaged as controlled source)
B_sw SW GND V = V(VIN) * LIMIT(V(comp)/3.3, 0, 0.95)
.ends
```

**Step 2: Complete Circuit Testbench**

```spice
* LMR51430 24V to 5V Buck Converter
Vin vin 0 DC 24

X1 vin sw 0 fb LMR51430

* Output LC filter
L1 sw vout 10u IC=0
C1 vout 0 22u IC=5

* Feedback divider (sets 5V output)
R1 vout fb 100k
R2 fb 0 25k

* Dynamic load (step from 100mA to 600mA)
I_load vout 0 PWL(0 0.1 1m 0.1 1.001m 0.6 2m 0.6)

.tran 1u 3m UIC
.end
```

---

### Building the Buck Converter in KiCad

This simulation uses an averaged model of the buck converter IC. Averaged models replace the switching behavior with an equivalent DC transfer function—this runs much faster than cycle-by-cycle simulation while still capturing transient response.

#### Step 1: Create New Schematic

Create: `sim_06_buck_converter.kicad_sch`

#### Step 2: Create the LMR51430 Averaged Model

First, create the subcircuit file. In `/simulation/models/`, create `LMR51430_avg.lib`:

```spice
* LMR51430 Averaged Model (simplified)
* This model captures the control loop behavior without switching

.subckt LMR51430 VIN SW GND FB
* Internal error amplifier
* High gain amplifies difference between FB and 0.8V reference
E_ea comp 0 VALUE = {10000 * (0.8 - V(FB))}

* PWM modulator (averaged as voltage-controlled voltage source)
* Output voltage = Vin * Duty, where Duty is controlled by error amp
B_sw SW GND V = V(VIN) * LIMIT(V(comp)/3.3, 0.05, 0.95)

* Note: LIMIT clamps duty cycle between 5% and 95%
.ends LMR51430
```

Save this file in your models directory.

#### Step 3: Create LMR51430 Symbol

1. **Symbol Editor → File → New Symbol**
2. Library: Your project library
3. Symbol name: `LMR51430`
4. Draw a rectangle with 4 pins:
   - Pin 1: `VIN` (Input voltage) — left
   - Pin 2: `SW` (Switch output) — right
   - Pin 3: `GND` (Ground) — bottom
   - Pin 4: `FB` (Feedback) — right, below SW

5. **Symbol properties:**
   ```
   Sim.Device = SUBCKT
   Sim.Pins = 1=VIN 2=SW 3=GND 4=FB
   Sim.Library = {SPICE_LIB_DIR}/LMR51430_avg.lib
   Sim.Name = LMR51430
   ```

> **[PHOTO PLACEHOLDER: LMR51430 symbol with pin configuration]**

#### Step 4: Place Components

| Component | Value | Purpose |
|-----------|-------|---------|
| `VSOURCE` Vin | DC 24 | Input supply |
| `LMR51430` X1 | — | Buck controller |
| `L` L1 | 10u | Output inductor |
| `C` C1 | 22u | Output capacitor |
| `R` R1 | 100k | Upper feedback resistor |
| `R` R2 | 25k | Lower feedback resistor |
| `ISOURCE` I_load | PWL(...) | Dynamic load |
| `GND` | — | Reference |

**Circuit layout:**
```
   Vin (24V)
      |
    [VIN]
      |
   LMR51430 ----[SW]---- L1 ----+---- vout
      |                  10µH   |
    [GND]                      C1  22µF
      |                         |
    [FB]                       GND
      |
      +---- R1 (100k) ---- vout
      |
      +---- R2 (25k) ----- GND
      
   I_load connected from vout to GND
```

#### Step 5: Wire the Circuit

1. Connect Vin positive to LMR51430 VIN pin
2. Connect LMR51430 SW pin to L1
3. Connect L1 to output node (label as `vout`)
4. Connect C1 from vout to GND
5. Connect feedback divider: R1 from vout to FB, R2 from FB to GND
6. Connect LMR51430 FB pin to the R1/R2 junction (label as `fb`)
7. Connect LMR51430 GND to GND
8. Connect I_load from vout to GND (current flows OUT of vout)

#### Step 6: Configure the Load Step

The current source simulates a load transient:

**I_load configuration:**
```
Value: PWL(0 0.1 1m 0.1 1.001m 0.6 2m 0.6)
```

This creates:
- 0–1ms: 100mA load (light load)
- 1ms–1.001ms: Ramp to 600mA (1µs transition)
- 1.001ms–end: 600mA load (heavy load)

**Important:** In SPICE, a positive current source value means current flows **into** the positive terminal. Since we want current to flow FROM vout TO ground (loading the supply), connect the current source with positive terminal at vout.

#### Step 7: Set Initial Conditions

For faster simulation startup, set initial conditions on energy storage elements:

**L1 properties:**
- `Value`: `10u`
- Add to value or as directive: `IC=0` (start with zero current)

**C1 properties:**
- `Value`: `22u` 
- Add: `IC=5` (start pre-charged to 5V)

Alternatively, add as directive:
```spice
.ic V(vout)=5
```

#### Step 8: Add Simulation Directives

```spice
.include {SPICE_LIB_DIR}/LMR51430_avg.lib
```

```spice
.tran 1u 3m UIC
```

The `UIC` (Use Initial Conditions) flag tells the simulator to use the IC= values rather than calculating DC operating point first.

> **[PHOTO PLACEHOLDER: Complete buck converter schematic in KiCad]**

#### Step 9: Run Simulation

1. Open Simulator (`F5`)
2. Run simulation
3. This should complete in a few seconds

#### Step 10: Plot and Analyze

**Add signals:**
- `V(vout)` — Output voltage (should regulate to 5V)
- `V(fb)` — Feedback node (should be 0.8V at regulation)
- `I(L1)` — Inductor current

**Key measurements:**

1. **Startup behavior (0–500µs):**
   - Verify monotonic rise to 5V
   - Check for overshoot (should be < 5.5V)

2. **Steady-state regulation (500µs–1ms):**
   - Output should be 5.0V ±2%
   - Feedback should be 0.8V

3. **Load step response (at 1ms):**
   - Measure voltage dip below 5V
   - **Critical:** Must stay above 4.75V (ESP32 minimum)
   - Measure recovery time to return within 2% of 5V

> **[PHOTO PLACEHOLDER: Buck converter waveforms showing startup and load step]**

#### Step 11: Cursor Measurements

**Measure load step dip:**
1. Zoom to 0.9ms–1.5ms timeframe
2. Place cursor at minimum voltage point after load step
3. Read voltage — should be > 4.75V

**Measure recovery time:**
1. Place cursor A at load step instant (1ms)
2. Place cursor B when voltage returns to 4.9V (within 2%)
3. Read Δt — should be < 100µs for well-designed supply

---

### Running as Standalone Netlist

Save the complete netlist as `sim_06_buck.cir`:

```spice
* LMR51430 24V to 5V Buck Converter
Vin vin 0 DC 24

* Include the model
.include models/LMR51430_avg.lib

X1 vin sw 0 fb LMR51430

* Output LC filter
L1 sw vout 10u IC=0
C1 vout 0 22u IC=5

* Feedback divider (sets 5V output: Vout = 0.8 * (1 + R1/R2) = 0.8 * 5 = 4V... wait)
* Correction: Vout = Vref * (1 + R1/R2) = 0.8 * (1 + 100k/25k) = 0.8 * 5 = 4V
* For 5V output: R1/R2 = (5/0.8 - 1) = 5.25, so R1=105k, R2=20k
* Or keep R2=25k, R1 = 5.25 * 25k = 131.25k ≈ 130k
R1 vout fb 130k
R2 fb 0 25k

* Dynamic load (step from 100mA to 600mA)
I_load vout 0 PWL(0 0.1 1m 0.1 1.001m 0.6 2m 0.6)

.tran 1u 3m UIC
.end
```

**Note:** I corrected the feedback resistor values in the standalone netlist. The original values (100k/25k) would give 4V output. For 5V output with 0.8V reference, use 130k/25k.

```bash
ngspice simulation/testbenches/sim_06_buck.cir

# In ngspice:
ngspice> run
ngspice> plot v(vout)
ngspice> plot i(L1)

# Measure load step response
ngspice> meas tran Vdip MIN v(vout) FROM=1m TO=1.5m
ngspice> meas tran Trecovery WHEN v(vout)=4.9 RISE=1 FROM=1m
```

---

> **[PHOTO PLACEHOLDER: Schematic of LMR51430 buck converter testbench]**

**Step 3: Analyze Start-up and Load Step**

Run the simulation and measure:

1. **Start-up time:** Time for Vout to reach 90% of target (should be <1ms)
2. **Overshoot:** Peak voltage during start-up (must stay below 5.5V)
3. **Load step dip:** Voltage drop during 100mA→600mA step
4. **Recovery time:** Time to return within ±2% of setpoint

> **[PHOTO PLACEHOLDER: Waveform showing start-up and load transient response]**

**Step 4: Verify Brown-out Margin**

**Critical requirement:** During load step, Vout must not dip below 4.75V (ESP32 minimum operating voltage). If the simulation shows excessive droop:

- Increase output capacitance
- Add ceramic capacitors in parallel for low ESR
- Verify feedback loop compensation

### Extended Exercise: Input Voltage Sweep

The 24V rail may vary with AC line fluctuations. Sweep Vin from 20V to 28V and verify regulation:

```spice
.step param Vin 20 28 2
```

### Validation Checkpoint

- [ ] Output voltage stable at 5.0V ±2%
- [ ] Load step dip remains above 4.75V
- [ ] Start-up monotonic with no overshoot above 5.5V
- [ ] Line regulation verified across 20V–28V input

---

## Lesson 07: Low-Noise 3.3V Regulation — The LDO and Pi-Filter

### Objective

Design and simulate the low-noise 3.3V rail that powers the precision ADC. The switching noise from the buck converter must be attenuated below the ADC's noise floor.

### Theory: PSRR and Filtering

The buck converter generates switching ripple at 1.1MHz. This noise must not corrupt ADC readings. The defense strategy employs two mechanisms in series:

- **Pi-Filter (passive):** C-L-C network attenuates high-frequency noise
- **LDO (active):** High PSRR provides additional rejection

**Combined attenuation target: >60dB at 1.1MHz**

### Simulation Exercise: Filter Design

**Step 1: Pi-Filter Component Selection**

Design a pi-filter with corner frequency well below the switching frequency:

$$f_{corner} = \frac{1}{2\pi \sqrt{L \times C}} \approx 50kHz$$

For fc = 50kHz with C = 10µF: L = 1µH (ferrite bead)

**Step 2: Combined Filter + LDO Simulation**

```spice
* 5V to 3.3V LDO with Pi-Filter Input
* Input: 5V with 50mVpp ripple at 1.1MHz
Vin 5v_noisy 0 DC 5 AC 0.025 SIN(5 0.025 1.1MEG)

* Pi-filter
C1 5v_noisy 0 10u
L1 5v_noisy 5v_clean 1u
C2 5v_clean 0 10u

* LDO (simplified model with PSRR)
* Typical LDO: 60dB PSRR at 1kHz, rolling off at higher freq
E_ldo 3v3 0 VALUE = {3.3 + V(5v_clean,3.3)/1000}
R_out 3v3 3v3_out 0.1
C_out 3v3_out 0 10u

.ac dec 100 1k 10MEG
.end
```

> **[PHOTO PLACEHOLDER: Schematic of pi-filter and LDO circuit]**

**Step 3: AC Analysis**

Run AC analysis and plot the transfer function from 5v_noisy to 3v3_out. Verify attenuation at 1.1MHz exceeds 60dB.

> **[PHOTO PLACEHOLDER: Bode plot showing combined filter + LDO attenuation]**

### Validation Checkpoint

- [ ] 60dB attenuation at 1.1MHz achieved
- [ ] 3.3V output ripple < 1mVpp
- [ ] Component values documented for BOM

---

## Lesson 08: Isolated High-Side Supply — The TI UCC14140-Q1

### Objective

Simulate the isolated DC/DC converter that powers the high-side gate driver. Verify isolation capacitance is low enough to prevent dV/dt induced noise injection and understand the voltage regulation architecture.

### Key Concepts

The high-side IGBT gate requires a floating 15V–22V supply referenced to the switching node (which swings from 0V to 400V). The UCC14140-Q1 is purpose-built for this application, providing galvanic isolation with exceptionally low coupling capacitance (<3.5pF) and high CMTI (>150 kV/µs).

**Why UCC14140-Q1 vs. discrete isolated DC/DC modules:**

| Parameter | UCC14140-Q1 | Typical Discrete Module |
|-----------|-------------|------------------------|
| Isolation capacitance | <3.5pF | ~10pF |
| CMTI | >150 kV/µs | ~50 kV/µs |
| Output voltage | 15–25V adjustable | Fixed |
| Negative bias option | Yes (COM-VEE) | No |
| Integrated transformer | Yes | Yes |
| Protection features | UVLO, OVP, OTP, soft-start | Basic |

The UCC14140-Q1 uses a proprietary high-frequency switching architecture (10–22 MHz carrier) with spread-spectrum modulation to minimize EMI emissions while achieving high density.

### Theory: Dual-Output Architecture

The UCC14140-Q1 can provide two independently regulated outputs:

1. **VDD-VEE (Main output):** 15V to 25V, adjustable via resistor divider on FBVDD
2. **COM-VEE (Auxiliary output):** 2.5V to (VDD-VEE), adjustable via FBVEE

For IGBT applications, a typical configuration is:
- VDD-VEE = 22V (positive gate bias)
- COM-VEE = 4V (creating -4V negative turn-off bias)
- Net gate swing: +18V (on) to -4V (off)

The negative turn-off bias is critical for SiC FETs and beneficial for IGBTs to prevent parasitic turn-on during high dV/dt events.

> **[PHOTO PLACEHOLDER: Block diagram showing UCC14140-Q1 dual-output isolated supply topology]**

### Design Calculations

**Step 1: Set VDD-VEE Output Voltage**

The output voltage is set by the FBVDD resistor divider:

$$V_{DD-VEE} = V_{REF} \times \frac{R_{FBVDD\_TOP} + R_{FBVDD\_BOT}}{R_{FBVDD\_BOT}}$$

Where $V_{REF} = 2.5V$. For VDD-VEE = 22V:

$$\frac{R_{FBVDD\_TOP}}{R_{FBVDD\_BOT}} = \frac{22V}{2.5V} - 1 = 7.8$$

Using standard values: $R_{FBVDD\_TOP} = 78k\Omega$, $R_{FBVDD\_BOT} = 10k\Omega$

**Step 2: Set COM-VEE Output Voltage (Optional Negative Bias)**

For COM-VEE = 4V (creating VDD-COM = 18V, COM-VEE = -4V referenced to COM):

$$\frac{R_{FBVEE\_TOP}}{R_{FBVEE\_BOT}} = \frac{4V}{2.5V} - 1 = 0.6$$

Using standard values: $R_{FBVEE\_TOP} = 6k\Omega$, $R_{FBVEE\_BOT} = 10k\Omega$

**Step 3: Calculate RLIM Resistor**

The RLIM resistor limits the source/sink current for the COM-VEE regulator. For gate driver loads with capacitive switching:

$$R_{LIM} = \frac{V_{VDD-COM}}{I_{MAX}} - R_{LIM\_INT}$$

Where $R_{LIM\_INT} \approx 30\Omega$ (internal switch resistance). For a target peak current of 100mA:

$$R_{LIM} = \frac{18V}{0.1A} - 30\Omega = 150\Omega$$

Typical values range from 51Ω to 1kΩ depending on load requirements.

### Simulation Exercise

**Part A: Isolation Barrier Coupling Analysis**

Model the isolation barrier as a small capacitor and apply 100V/ns dV/dt. The UCC14140-Q1's low 3.5pF barrier capacitance significantly reduces coupled noise:

```spice
* UCC14140-Q1 Isolation barrier coupling model
* Compare: 3.5pF (UCC14140) vs 10pF (discrete module)

.param C_barrier=3.5p  ; UCC14140-Q1 specification

* Isolation barrier capacitance
C_iso hs_gnd sw_node {C_barrier}

* Switching node transient (100V/ns = 400V in 4ns)
V_sw sw_node 0 PULSE(0 400 0 4n 4n 10u 20u)

* 22V rail with local decoupling (10µF ceramic)
V_22v vdd_rail hs_gnd DC 22
R_esr vdd_rail vdd_cap 0.01  ; Ceramic ESR
C_local vdd_cap hs_gnd 10u

* Measure coupled current
.tran 1n 30u

* Key measurements:
.meas tran I_coupled_peak MAX I(C_iso)
.meas tran V_rail_deviation MAX abs(V(vdd_cap)-22)

.end
```

**Expected Results:**
- Peak coupled current: ~350µA (vs ~1mA with 10pF)
- Rail voltage deviation: <0.1V

> **[PHOTO PLACEHOLDER: Waveform comparing coupled current for 3.5pF vs 10pF isolation capacitance]**

**Part B: Behavioral Model for System Simulation**

Create a simplified behavioral model capturing the key UCC14140-Q1 characteristics:

```spice
* UCC14140-Q1 Behavioral Model for System Simulation
.subckt UCC14140_BEHAVIORAL VIN GNDP VDD VEE COM ENA PG
+ PARAMS: VOUT_VDD=22 VOUT_COM=4

* Input supply (8-18V operating range)
* UVLO at 7.4V falling, 8.2V rising

* Main output VDD-VEE with soft-start
* Rise time ~3ms typical
B_vdd VDD VEE V = IF(V(ENA,GNDP)>2.1 & V(VIN,GNDP)>8, 
+   {VOUT_VDD} * (1 - exp(-TIME/1m)), 0)

* COM-VEE output tracks main output
B_com COM VEE V = IF(V(VDD,VEE)>12, {VOUT_COM}, 0)

* Power-good output (open-drain, active low)
* Goes low when outputs within ±10%
B_pg PG GNDP V = IF(V(VDD,VEE)>{VOUT_VDD*0.9} & 
+   V(VDD,VEE)<{VOUT_VDD*1.1} & V(COM,VEE)>{VOUT_COM*0.9}, 0, 5)

* Isolation barrier (reflected to primary)
C_iso GNDP VEE 3.5p

.ends UCC14140_BEHAVIORAL
```

**Part C: Complete High-Side Supply Testbench**

```spice
* UCC14140-Q1 High-Side Supply with Gate Driver Load
.include UCC14140_behavioral.sub

* 12V input supply (from auxiliary buck)
Vin vin 0 DC 12

* UCC14140-Q1 module
X1 vin 0 vdd vee com ena pg UCC14140_BEHAVIORAL 
+ PARAMS: VOUT_VDD=22 VOUT_COM=4

* Enable after 1ms
Vena ena 0 PULSE(0 5 1m 100u 100u 100m 200m)

* Gate driver quiescent load (5mA typical)
R_iq vdd com 3.6k

* Gate charge load: Qg=270nC @ 35kHz = 9.45mA average
* Model as pulsed current source
I_gate com vee PULSE(0 50m 5m 10n 10n 5u 28.5u)

* Switching node voltage (for CMTI stress)
V_sw sw_node 0 PULSE(0 400 5m 5n 5n 14u 28.5u)
C_sw vee sw_node 3.5p

* Decoupling capacitors (per datasheet recommendations)
C_vdd vdd vee 10u IC=0
C_com com vee 1u IC=0

.tran 10u 20m UIC
.end
```

**Verification Points:**

1. **Startup sequence:** VDD-VEE should reach regulation within 5ms, COM-VEE follows
2. **Power-good timing:** PG goes low after both rails stable (typ. <28ms from enable)
3. **Load regulation:** <1.3% deviation under pulsed gate charge load
4. **CMTI immunity:** No glitches on outputs during 80V/ns switching transients

> **[PHOTO PLACEHOLDER: Startup waveform showing VDD-VEE, COM-VEE, and PG timing]**

### External Component Selection

| Component | Value | Purpose | Notes |
|-----------|-------|---------|-------|
| C_IN | 20µF + 0.1µF | Input decoupling | X7R ceramic, place close to pins |
| C_OUT1 | 10µF + 0.1µF | VDD-VEE decoupling | X7R ceramic |
| C_OUT2 | 4.7µF | VDD-COM decoupling | At gate driver |
| C_OUT3 | 1µF | COM-VEE decoupling | At gate driver |
| R_FBVDD_TOP | 78kΩ | Sets VDD-VEE | 1% tolerance |
| R_FBVDD_BOT | 10kΩ | Sets VDD-VEE | 1% tolerance |
| R_FBVEE_TOP | 6kΩ | Sets COM-VEE | 1% tolerance |
| R_FBVEE_BOT | 10kΩ | Sets COM-VEE | 1% tolerance |
| R_LIM | 150Ω | Current limit | Size for 0.25W |
| C_FBVDD | 330pF | Noise filter | C0G/NP0 |
| C_FBVEE | 330pF | Noise filter | C0G/NP0 |

### Layout Considerations

Critical PCB layout guidelines for the UCC14140-Q1:

1. **Maintain isolation gap:** 8mm minimum clearance between primary and secondary copper on all layers
2. **Thermal vias:** Place thermal via arrays under the device (both GNDP and VEE sides) connecting to internal/bottom copper planes
3. **Feedback routing:** Route FBVDD and FBVEE sense traces directly from load point (gate driver capacitors) for best regulation accuracy
4. **VEEA isolation:** Keep VEEA pin isolated from VEE power plane; connect only through feedback resistor network

> **[PHOTO PLACEHOLDER: Layout example showing isolation gap and thermal via placement]**

### Validation Checkpoint

- [ ] Coupled noise current < 500µA during 100V/ns transient (3.5pF spec)
- [ ] VDD-VEE rail deviation < 0.2V during 100V/ns switching transient
- [ ] Output ripple < 100mV under pulsed gate charge load
- [ ] Startup sequence completes in < 10ms
- [ ] Power dissipation calculated and thermal design verified against SOA curves
- [ ] FBVDD/FBVEE resistor values calculated for target output voltages

---

## Lesson 09: AC Input Stage — Rectification and Soft-Start

### Objective

Simulate the AC mains input stage including rectification, EMI filtering, and inrush current limiting. Validate that the soft-start circuit prevents destructive inrush current.

### Theory: Inrush Current

When empty DC link capacitors are connected to rectified mains, the peak inrush current can exceed 100A—enough to trip breakers, weld relay contacts, and stress capacitors. The soft-start circuit uses a PTC thermistor (or NTC + bypass relay) to limit this current.

$$I_{inrush(peak)} = \frac{V_{peak}}{ESR} \approx \frac{340V}{0.1\Omega} = 3400A \text{ (without limiting!)}$$

### Simulation Exercise

Model the rectifier, DC link capacitor (470µF), and soft-start circuit. Simulate power-on and verify:

```spice
* AC Input with Soft-Start
V_ac ac_in 0 SIN(0 170 60)  ; 120Vrms, 60Hz

* Bridge rectifier (simplified)
D1 ac_in rect_pos DIODE
D2 0 rect_pos DIODE
D3 rect_neg ac_in DIODE
D4 rect_neg 0 DIODE

* Soft-start NTC (models as time-varying resistor)
* Cold: 10Ω, Hot: 0.5Ω with 200ms time constant
B_ntc rect_pos ntc_out I = V(rect_pos, ntc_out) / (0.5 + 9.5*exp(-TIME/0.2))

* DC link capacitor
C_dc ntc_out rect_neg 470u IC=0

.model DIODE D(IS=1e-10 RS=0.05)
.tran 100u 1s UIC
.end
```

**Verify:**

- [ ] Peak inrush current < 20A
- [ ] DC bus reaches 310V within 500ms
- [ ] Bypass relay engages after bus stabilizes

> **[PHOTO PLACEHOLDER: Waveforms showing inrush current limiting during startup]**

---

## Lesson 10: High-Voltage Bus Monitoring — Isolated Sensing

### Objective

Design and simulate the isolated voltage sensing circuit for the 310V DC bus. This measurement enables power calculation, over-voltage protection, and PFC feedback (future enhancement).

### Theory: Resistive Divider with Isolated Amplifier

The 310V bus must be scaled to a safe level (<3.3V) for MCU ADC input while maintaining galvanic isolation. The solution uses:

- High-value resistive divider (multiple resistors in series for voltage rating)
- Isolated amplifier (AMC1200) to cross the isolation boundary

### Simulation Exercise

Design the resistive divider for 310V → 200mV scaling:

```spice
* High-voltage sensing with isolation
V_bus hv_bus 0 DC 310

* Resistive divider (3x 1MΩ in series for voltage rating)
R1a hv_bus div1 1MEG
R1b div1 div2 1MEG
R1c div2 sense_in 1MEG
R2 sense_in hv_gnd 2k

* sense_in voltage = 310V * 2k / (3M + 2k) ≈ 206mV
```

Simulate the complete sensing chain including the isolated amplifier bandwidth limitations.

### Validation Checkpoint

- [ ] Sensing accuracy better than ±2%
- [ ] Bandwidth sufficient for 120Hz ripple measurement
- [ ] Isolation voltage rating verified against specifications

---

# Phase II: Power Stage Simulation & Resonant Tank Design

With individual components characterized, this phase integrates them into the complete resonant tank circuit. Simulation validates the operating frequency range, circulating currents, and zero-voltage switching conditions.

---

## Lesson 11: Resonance Theory — The Half-Bridge Topology

### Objective

Mathematically derive and simulate the LC resonant tank parameters to achieve the target frequency window (30kHz–40kHz).

### Theory: Series Resonance

The induction coil forms an inductor; when combined with the resonant capacitor bank, a series LC tank results. At resonance:

$$f_r = \frac{1}{2\pi\sqrt{L_{coil} \times C_{res}}}$$

For an induction coil with Lcoil ≈ 50µH (measured with pan) and target fr = 35kHz:

$$C_{res} = \frac{1}{4\pi^2 \times f_r^2 \times L_{coil}} \approx 413nF$$

### Simulation Exercise: Tank Frequency Response

**Step 1: Create Tank Circuit**

```spice
* Resonant Tank AC Analysis
V_ac in 0 AC 1
C_res in tank 470n
L_coil tank 0 50u
R_loss tank 0 2  ; ESR + reflected load

.ac dec 100 10k 100k
.end
```

---

### Building the Resonant Tank in KiCad

This simulation uses AC analysis to find the resonant frequency of the LC tank. AC analysis sweeps frequency and measures the magnitude and phase response.

#### Step 1: Create New Schematic

Create: `sim_11_resonant_tank.kicad_sch`

#### Step 2: Place Components

| Component | Reference | Value | Purpose |
|-----------|-----------|-------|---------|
| `VSOURCE` | V_ac | AC 1 | AC stimulus (1V amplitude) |
| `C` | C_res | 470n | Resonant capacitor |
| `L` | L_coil | 50u | Induction coil inductance |
| `R` | R_loss | 2 | Combined ESR + load resistance |
| `GND` | — | — | Reference |

**Circuit topology (series RLC):**
```
    V_ac (AC 1V)
        |
      [in]
        |
      C_res
      470nF
        |
      [tank]
        |
    +---+---+
    |       |
  L_coil  R_loss
   50µH     2Ω
    |       |
    +---+---+
        |
       GND
```

#### Step 3: Wire the Circuit

1. Connect V_ac positive to C_res (label this node `in`)
2. Connect C_res other terminal to L_coil AND R_loss (label this node `tank`)
3. Connect L_coil and R_loss to GND
4. Connect V_ac negative to GND

The inductor and resistor are in parallel because:
- L_coil represents the induction coil
- R_loss represents the equivalent resistance from ESR and coupled pan load

#### Step 4: Configure the AC Source

**V_ac properties:**
```
Value: AC 1
```

This sets up a 1V AC stimulus for frequency sweep. The "AC 1" means 1V magnitude, 0° phase.

For combined DC bias + AC analysis, you could use:
```
Value: DC 0 AC 1
```

#### Step 5: Add AC Analysis Directive

Add as simulation directive text:

```spice
.ac dec 100 10k 100k
```

**Parameters explained:**
| Parameter | Value | Meaning |
|-----------|-------|---------|
| `dec` | — | Decade sweep (logarithmic) |
| `100` | — | 100 points per decade |
| `10k` | 10kHz | Start frequency |
| `100k` | 100kHz | Stop frequency |

**Alternative sweep types:**
```spice
.ac lin 1000 10k 100k    ; Linear sweep, 1000 total points
.ac oct 50 10k 100k      ; Octave sweep, 50 points per octave
```

> **[PHOTO PLACEHOLDER: Resonant tank schematic in KiCad]**

#### Step 6: Run AC Analysis

1. Open Simulator (`F5`)
2. Click Run
3. The simulation performs frequency sweep (very fast, <1 second)

#### Step 7: Plot Frequency Response

**Add signals:**
- `V(tank)` — Voltage at the tank node

**Understanding the display:**

For AC analysis, KiCad's simulator shows:
- **Magnitude plot** (top): Voltage vs. frequency in dB or linear
- **Phase plot** (bottom): Phase angle vs. frequency in degrees

**At resonance:**
- The impedance of L and C cancel
- Only R_loss remains
- Current is maximum
- Voltage across L or C peaks

To see the current (which shows resonance more clearly):
- Plot `I(V_ac)` — current from the source

> **[PHOTO PLACEHOLDER: Bode plot showing resonant peak at ~33kHz]**

#### Step 8: Find Resonant Frequency

**Method 1: Visual inspection**
- Look for the peak in the magnitude plot
- Read frequency from x-axis at peak

**Method 2: Use cursor**
1. Click on the magnitude plot
2. Move cursor to the peak
3. Read frequency from cursor display

**Method 3: Add measurement directive**
```spice
.meas ac Fres WHEN mag(V(tank))=MAX
```

**Theoretical calculation for verification:**

$$f_r = \frac{1}{2\pi\sqrt{LC}} = \frac{1}{2\pi\sqrt{50\mu H \times 470nF}} = 32.8kHz$$

Your simulation should show a peak near **33kHz**.

#### Step 9: Measure Q Factor

The Q factor indicates how "sharp" the resonance is:

$$Q = \frac{f_r}{BW_{3dB}}$$

**To measure bandwidth:**
1. Find the peak magnitude value
2. Find the -3dB point (peak magnitude × 0.707 in linear, or peak - 3dB in dB)
3. Find frequencies f1 and f2 where magnitude equals -3dB point
4. BW = f2 - f1

**Add measurement directives:**
```spice
.meas ac Vpeak MAX mag(V(tank))
.meas ac F_low WHEN mag(V(tank))=Vpeak/sqrt(2) RISE=1
.meas ac F_high WHEN mag(V(tank))=Vpeak/sqrt(2) FALL=1
```

For this circuit with R_loss = 2Ω:
- At resonance, impedance ≈ 2Ω (just the loss resistance)
- Q ≈ (2π × 33kHz × 50µH) / 2Ω ≈ 5.2

#### Step 10: Parameter Sweep (Optional)

To see how different load resistances affect Q, add a parameter sweep:

```spice
.param Rloss=2
.step param Rloss 1 10 1
.ac dec 100 10k 100k
```

Then change R_loss value to: `{Rloss}`

This runs 10 simulations with R_loss from 1Ω to 10Ω, showing how heavier loading (more pan coupling) reduces Q and broadens the resonance.

> **[PHOTO PLACEHOLDER: Multiple traces showing Q reduction with increasing load resistance]**

---

### Running as Standalone Netlist

Save as `sim_11_resonant_tank.cir`:

```spice
* Resonant Tank AC Analysis
* Calculates resonant frequency and Q factor

V_ac in 0 AC 1
C_res in tank 470n
L_coil tank 0 50u
R_loss tank 0 2

* AC sweep from 10kHz to 100kHz
.ac dec 100 10k 100k

* Measurements
.meas ac Fres MAX_AT mag(V(tank))
.meas ac Vpeak MAX mag(V(tank))
.meas ac F_low WHEN mag(V(tank))=Vpeak*0.707 RISE=1
.meas ac F_high WHEN mag(V(tank))=Vpeak*0.707 FALL=1
.meas ac BW PARAM='F_high-F_low'
.meas ac Q PARAM='Fres/BW'

.end
```

```bash
ngspice simulation/testbenches/sim_11_resonant_tank.cir

# In ngspice:
ngspice> run
ngspice> plot mag(v(tank))           ; Magnitude vs frequency
ngspice> plot db(v(tank))            ; dB scale
ngspice> plot ph(v(tank))*180/pi     ; Phase in degrees
ngspice> plot mag(i(V_ac))           ; Current magnitude (shows resonance clearly)

# Measurements are printed automatically
```

---

### Transient Analysis Alternative

While AC analysis finds resonant frequency efficiently, you can also verify with transient analysis:

```spice
* Resonant Tank Transient (Ring-down test)
V_pulse in 0 PULSE(0 10 0 1n 1n 100n 1m)
C_res in tank 470n
L_coil tank 0 50u
R_loss tank 0 2

.tran 10n 200u
.end
```

This pulses the tank and lets it ring. The oscillation frequency is the natural resonant frequency, and the decay rate indicates Q.

---

**Step 2: Identify Resonant Peak**

Plot impedance magnitude vs. frequency. The minimum impedance point indicates resonance. Document:

- Resonant frequency (should be ~35kHz)
- Q factor (bandwidth measurement)
- Impedance at resonance (determines current magnitude)

> **[PHOTO PLACEHOLDER: Impedance vs. frequency plot showing resonant peak]**

### Extended Exercise: Pan Loading Effect

The pan acts as a transformer-coupled resistive load. Model different pan materials (stainless steel, cast iron, aluminum) as different coupling coefficients and equivalent resistances. Document how resonant frequency shifts with pan type.

| Pan Material | Coupling (k) | R_equiv | Frequency Shift |
|--------------|--------------|---------|-----------------|
| Cast Iron | 0.9 | 0.3Ω | [measured] |
| Stainless Steel | 0.85 | 0.8Ω | [measured] |
| Aluminum (non-magnetic) | 0.3 | 2Ω | [measured] |

### Validation Checkpoint

- [ ] Resonant frequency within 30–40kHz range
- [ ] Q factor documented (typical: 5–15 with pan)
- [ ] Capacitor bank value finalized

---

## Lesson 12: Capacitor Bank Design — Handling Reactive Power

### Objective

Design and simulate the capacitor bank to handle the massive reactive power (30A+ circulating current) while minimizing losses and ensuring reliability.

### Theory: ESR and Ripple Current

At resonance, the tank circulating current can reach 30A or more. The capacitor bank must handle this ripple current without overheating:

$$P_{cap\_loss} = I_{rms}^2 \times ESR$$

Using multiple parallel capacitors reduces effective ESR and distributes thermal load.

### Simulation Exercise

Model a bank of 10× 47nF 1200V MKP capacitors in parallel. Include realistic ESR values (typically 5–10mΩ per capacitor) and simulate power dissipation at full load.

```spice
* Capacitor bank model (10x 47nF with ESR)
.subckt CAP_BANK pos neg
C1 pos n1 47n
R1 n1 neg 8m
C2 pos n2 47n
R2 n2 neg 8m
* ... repeat for all 10 capacitors
* Total: 470nF, ~0.8mΩ ESR
.ends
```

> **[PHOTO PLACEHOLDER: Schematic showing parallel capacitor bank with ESR models]**

### Validation Checkpoint

- [ ] Capacitor power dissipation calculated
- [ ] Ripple current per capacitor within rating
- [ ] Capacitor BOM finalized with voltage/current ratings

---

## Lesson 13: Pan Load Modeling — The Transformer Equivalent

### Objective

Create a SPICE model of the induction coil + pan system as a transformer-coupled load. Validate the model against expected power delivery.

### Theory: Coupled Inductors

The induction coil (primary) couples magnetically to the pan (secondary). The pan's resistance appears as a reflected load on the primary:

$$R_{reflected} = k^2 \times \frac{L_{primary}}{L_{secondary}} \times R_{pan}$$

Where k is the coupling coefficient (0.7–0.9 for typical cookware).

### Simulation Exercise

```spice
* Transformer-Coupled Pan Model
L1 coil_hot coil_cold 50u
L2 pan_hot pan_cold 5u
K1 L1 L2 0.85
R_pan pan_hot pan_cold 0.5

* Complete tank with half-bridge drive
Vbus bus 0 DC 310
V_drive drive 0 PULSE(0 1 0 100n 100n 14u 28.5u)  ; 35kHz

* Half-bridge (simplified)
S_high bus coil_hot drive 0 SW
S_low coil_hot 0 drive_inv 0 SW
E_inv drive_inv 0 VALUE = {1 - V(drive)}

C_res coil_cold 0 470n

.model SW SW VT=0.5 RON=0.1
.tran 10n 500u UIC
.end
```

> **[PHOTO PLACEHOLDER: Waveforms showing coil current and power delivery to pan model]**

### Validation Checkpoint

- [ ] Power to pan model matches target (1500–2000W)
- [ ] Circulating current within IGBT ratings
- [ ] Model responds correctly to coupling coefficient changes

---

## Lesson 14: Full Half-Bridge Simulation

### Objective

Integrate all power stage components—IGBTs, gate drivers, resonant tank, and load—into a complete simulation. Verify operation across the full power range.

### Simulation Exercise: Complete Power Stage

Build the complete half-bridge simulation including:

- Both IGBTs with validated models from Lesson 04
- Gate driver with dead-time from Lesson 05
- Resonant tank with pan model from Lesson 13
- DC bus from Lesson 09

> **[PHOTO PLACEHOLDER: Complete half-bridge power stage schematic]**

Sweep operating frequency from 30kHz to 50kHz and plot:

- Output power vs. frequency
- IGBT losses vs. frequency
- Tank current phase vs. frequency (for ZVS verification)

> **[PHOTO PLACEHOLDER: Plots showing power and efficiency vs. frequency]**

### Validation Checkpoint

- [ ] 1500W+ power delivery achieved in simulation
- [ ] IGBT junction temperature estimates within limits
- [ ] ZVS condition identified (current leads voltage)

---

## Lesson 15: Zero Voltage Switching (ZVS) Analysis

### Objective

Analyze and optimize the circuit for Zero Voltage Switching—the critical efficiency technique that minimizes switching losses.

### Theory: ZVS Mechanism

ZVS occurs when the IGBT turns on while its collector-emitter voltage is zero (or very low). This is achieved by operating slightly above resonance, where the tank current lags the voltage, allowing the current to discharge the output capacitance before turn-on.

At ZVS, turn-on losses approach zero:

$$E_{on(ZVS)} \approx 0 \quad \text{(compared to } E_{on(hard)} = \frac{1}{2}CV^2 \text{)}$$

### Simulation Exercise

Zoom in on the switching transitions. Verify that Vce falls to near zero before gate voltage rises. Measure the phase angle between drive voltage and tank current.

Key measurements:
- Vce at turn-on instant (target: <50V)
- Phase angle (target: 10-30° lagging)
- Turn-on loss (integrate Vce × Ic during turn-on)

> **[PHOTO PLACEHOLDER: Detailed waveforms showing ZVS transition with Vce, Vge, and Itank]**

### Validation Checkpoint

- [ ] ZVS achieved across 80–100% power range
- [ ] Required phase angle documented
- [ ] Loss reduction quantified vs. hard switching

---

## Lesson 16: Snubber Design and Voltage Spike Suppression

### Objective

Design RC snubbers to suppress voltage spikes caused by parasitic inductance during switching transitions.

### Theory: Parasitic Inductance

Even small amounts of stray inductance (10–50nH) in the power loop cause significant voltage spikes during fast switching:

$$V_{spike} = L_{stray} \times \frac{di}{dt}$$

At 30A switched in 50ns: 

$$V_{spike} = 30nH \times \frac{30A}{50ns} = 18V$$

### Simulation Exercise

Add realistic parasitic inductances to the model and verify snubber effectiveness:

```spice
* Add parasitics
L_stray1 bus igbt_c 30n
L_stray2 igbt_e 0 20n

* RC snubber across IGBT
R_snub igbt_c snub_node 10
C_snub snub_node igbt_e 1n
```

Compare Vce waveforms with and without snubber. Document the optimal R and C values.

> **[PHOTO PLACEHOLDER: Vce comparison showing voltage spikes with and without snubber]**

### Validation Checkpoint

- [ ] Voltage spike reduced to safe level (<100V overshoot)
- [ ] Snubber power dissipation calculated
- [ ] Optimal snubber values documented

---

## Lesson 17: Current Sensing — The Current Transformer

### Objective

Design and simulate the current sensing circuit for phase detection and power measurement.

### Theory: Current Transformer Operation

A current transformer (CT) provides isolated, scaled current measurement. With a 1:1000 turns ratio and 100Ω burden resistor, 30A primary current produces:

$$V_{sense} = \frac{I_{primary}}{N} \times R_{burden} = \frac{30A}{1000} \times 100\Omega = 3V$$

### Simulation Exercise

Model the CT and signal conditioning circuit. Include core saturation effects for accuracy at low currents.

```spice
* Current transformer model
* Primary: 1 turn (the power conductor)
* Secondary: 1000 turns
L_ct_pri ct_in ct_out 100n
L_ct_sec sec_p sec_n 100m
K_ct L_ct_pri L_ct_sec 0.995

R_burden sec_p sense_out 100
* sec_n connects to sense ground
```

> **[PHOTO PLACEHOLDER: CT output waveform showing current sensing signal]**

### Validation Checkpoint

- [ ] Sensing accuracy verified at 10%, 50%, 100% load
- [ ] Phase delay through CT documented
- [ ] Burden resistor power rating specified

---

## Lesson 18: Thermal Modeling and Heatsink Requirements

### Objective

Calculate thermal requirements and verify heatsink adequacy through thermal simulation.

### Theory: Thermal Resistance Network

The thermal path from IGBT junction to ambient forms a resistance network:

$$T_j = T_{amb} + P_{diss} \times (R_{\theta JC} + R_{\theta CS} + R_{\theta SA})$$

For Pdiss = 40W, Tamb = 30°C, Tj(max) = 110°C:

$$R_{\theta SA(max)} = \frac{T_{j(max)} - T_{amb}}{P_{diss}} - R_{\theta JC} - R_{\theta CS}$$

$$R_{\theta SA(max)} = \frac{110 - 30}{40} - 0.35 - 0.5 = 1.15 \text{ K/W}$$

### Simulation Exercise

Create a thermal simulation (using thermal network in SPICE or dedicated thermal tools) to verify the selected heatsink maintains junction temperature below 100°C under worst-case conditions.

```spice
* Thermal equivalent circuit
I_power 0 tj 40          ; 40W power dissipation
R_jc tj tc 0.35          ; Junction to case
R_cs tc ts 0.5           ; Case to heatsink (with compound)
R_sa ts tamb 1.0         ; Heatsink to ambient
V_amb tamb 0 DC 30       ; 30°C ambient

.op
* Check: V(tj) should be < 110
```

> **[PHOTO PLACEHOLDER: Thermal simulation showing temperature distribution]**

### Validation Checkpoint

- [ ] Heatsink thermal resistance specified
- [ ] Tj(max) < 100°C at full power
- [ ] Airflow requirements documented

---

# Phase III: Control System & Sensing Simulation

This phase develops and simulates the complete control system including temperature sensing, user interface, and safety interlocks—all in software before hardware implementation.

---

## Lesson 19: ESP32-S3 Peripheral Simulation

### Objective

Understand ESP32-S3 peripherals (MCPWM, ADC, GPIO) and create behavioral models for system simulation.

### Key Peripherals

| Peripheral | Function | Key Specification |
|------------|----------|-------------------|
| MCPWM | Motor Control PWM | Hardware dead-time insertion |
| ADC | Analog-to-Digital | 12-bit SAR, up to 2 Msps |
| PCNT | Pulse Counter | Encoder input |
| TWDT | Task Watchdog | Firmware safety |

### Simulation Exercise

Create behavioral Verilog or Python models of MCPWM output and verify timing against gate driver requirements.

```python
# Python behavioral model of MCPWM
import numpy as np

def mcpwm_output(frequency, duty_cycle, dead_time_ns, duration_us):
    """Generate complementary PWM with dead time."""
    dt = 1e-9  # 1ns resolution
    t = np.arange(0, duration_us * 1e-6, dt)
    period = 1.0 / frequency
    
    # High-side PWM
    pwm_h = ((t % period) < (duty_cycle * period)).astype(float)
    
    # Low-side PWM (complementary with dead time)
    pwm_l = ((t % period) > (duty_cycle * period + dead_time_ns * 1e-9)).astype(float)
    pwm_l &= ((t % period) < (period - dead_time_ns * 1e-9))
    
    return t, pwm_h, pwm_l
```

### Validation Checkpoint

- [ ] PWM timing matches requirements
- [ ] Dead time correctly implemented
- [ ] ADC sampling rate adequate for control loop

---

## Lesson 20: Temperature Sensing — NTC Thermistor Interface

### Objective

Design and simulate the "through-glass" infrared temperature sensor interface with appropriate filtering for noise rejection.

### Theory: Anti-Aliasing Filter

The induction field generates significant high-frequency noise (30–60kHz) on sensor cables. A low-pass filter with aggressive cutoff rejects this noise:

$$f_c = \frac{1}{2\pi \times R \times C} \approx 10Hz \quad (R=15k\Omega, C=1\mu F)$$

### Simulation Exercise

Model the complete sensing chain: NTC thermistor → filter → external ADC (ADS1115). Inject 35kHz noise and verify rejection.

```spice
* NTC sensing with anti-aliasing filter
* NTC modeled as temperature-dependent resistor
* At 25°C: 10kΩ, B=3950K

.param TEMP=25
B_ntc ntc_hot ntc_cold I = V(ntc_hot, ntc_cold) / (10k * exp(3950 * (1/(273+{TEMP}) - 1/298)))

* Voltage divider with reference
V_ref ref 0 DC 3.3
R_ref ref ntc_hot 10k

* Anti-aliasing filter
R_filt ntc_cold filt_out 15k
C_filt filt_out 0 1u

* Inject 35kHz noise
V_noise ntc_cold noise_inj SIN(0 0.1 35k)

.tran 10u 100m
```

> **[PHOTO PLACEHOLDER: ADC output showing clean temperature reading despite injected noise]**

### Validation Checkpoint

- [ ] 35kHz noise attenuated by >60dB
- [ ] Temperature reading stable to ±0.5°C
- [ ] Response time adequate for control loop

---

## Lesson 21: RTD Probe Interface with Isolation

### Objective

Design the user-accessible RTD probe interface with galvanic isolation for safety.

### Safety Requirement

The RTD probe is touched by the user and immersed in food. Complete galvanic isolation is mandatory to prevent electric shock. The circuit uses:

- **MAX31865:** RTD-to-digital converter with excitation and fault detection
- **ADuM1250:** I2C isolator for data lines

### Simulation Exercise

Simulate the MAX31865 fault detection (open/short circuit detection) and verify firmware response to fault conditions.

```python
# MAX31865 Fault Detection Simulation
class MAX31865_Sim:
    def __init__(self):
        self.fault_status = 0x00
    
    def check_faults(self, rtd_resistance):
        """Simulate fault detection logic."""
        self.fault_status = 0x00
        
        # Open circuit: resistance too high
        if rtd_resistance > 4000:  # > 4kΩ indicates open
            self.fault_status |= 0x04  # RTD High Threshold
        
        # Short circuit: resistance too low
        if rtd_resistance < 50:  # < 50Ω indicates short
            self.fault_status |= 0x08  # RTD Low Threshold
        
        return self.fault_status
    
    def requires_shutdown(self):
        """Any fault requires immediate shutdown."""
        return self.fault_status != 0x00
```

### Validation Checkpoint

- [ ] Open circuit detected within 100ms
- [ ] Short circuit detected within 100ms
- [ ] Firmware correctly triggers HARD_STOP on fault

---

## Lesson 22: Hardware Safety Interlocks

### Objective

Design hardware-based safety circuits that operate independently of firmware.

### The "Kill Switch" Circuit

A dual comparator (LM393) monitors over-current and over-temperature conditions. When triggered, it directly disables the gate driver—no firmware involvement required.

```spice
* Hardware Interlock Simulation

* Over-current comparator
V_ref_oc ref_oc 0 DC 2.5  ; Trip at 40A (3V sense = 30A, so 2.5V ≈ 25A margin)
V_sense sense 0 PWL(0 0 1m 2 1.5m 3.5 2m 3.5)  ; Ramp up to fault

* LM393 comparator model
.subckt LM393_COMP inp inm out
E_comp out 0 VALUE = {IF(V(inp) > V(inm), 0, 5)}
.ends

X_comp sense ref_oc disable LM393_COMP

* Gate driver disable input
B_gate_en gate_en 0 V = V(disable) < 2.5 ? 15 : 0
```

Verify that the interlock responds within 1µs of over-current condition.

> **[PHOTO PLACEHOLDER: Timing diagram showing fast interlock response]**

### Validation Checkpoint

- [ ] Response time < 1µs
- [ ] No firmware dependency
- [ ] Comparator thresholds correctly set

---

## Lesson 23: Fan Control with Tachometer Feedback

### Objective

Design the active cooling control system with fan failure detection.

### Critical Safety Rule

```c
// This rule is non-negotiable
if (Target_Power > 0 && Fan_RPM == 0) {
    EMERGENCY_SHUTDOWN();
    fault_code = FAULT_FAN_FAILURE;
}
```

A failed fan while the system is delivering power leads to thermal runaway. The tachometer feedback provides early warning.

### Simulation Exercise

Model the fan tachometer signal and verify detection logic:

```python
# Fan tachometer simulation
def simulate_fan_tach(rpm, duration_s, sample_rate=10000):
    """Generate tachometer pulses for a given RPM."""
    # Typical 4-pin fan: 2 pulses per revolution
    pulse_freq = rpm * 2 / 60  # Hz
    
    t = np.arange(0, duration_s, 1/sample_rate)
    tach = (np.sin(2 * np.pi * pulse_freq * t) > 0).astype(int)
    
    return t, tach

def detect_fan_failure(tach_signal, sample_rate, timeout_ms=500):
    """Detect fan failure by absence of pulses."""
    # Count edges in timeout window
    samples_in_window = int(timeout_ms * sample_rate / 1000)
    edges = np.diff(tach_signal[-samples_in_window:])
    edge_count = np.sum(np.abs(edges))
    
    # Minimum 2 edges expected in 500ms for any reasonable RPM
    return edge_count < 2
```

### Validation Checkpoint

- [ ] Fan failure detected within 500ms
- [ ] False positives avoided during normal operation
- [ ] PWM speed control verified

---

## Lesson 24: User Interface — Encoder and Display

### Objective

Design the human-machine interface with hardware debouncing.

### Hardware Debouncing

Rotary encoder signals require filtering to remove contact bounce. An RC filter (10kΩ, 10nF) provides clean edges with τ = 100µs.

```spice
* Encoder debounce filter
* Raw encoder signal with bounce
V_enc_raw enc_a_raw 0 PWL(0 0 1m 0 1.001m 3.3 1.002m 0 1.003m 3.3 1.01m 3.3)

* RC debounce filter
R_deb enc_a_raw enc_a_filt 10k
C_deb enc_a_filt 0 10n

.tran 1u 20m
```

### Simulation Exercise

Model encoder bounce and verify filter effectiveness through simulation.

> **[PHOTO PLACEHOLDER: Waveform showing encoder bounce before and after filtering]**

### Validation Checkpoint

- [ ] Bounce eliminated
- [ ] Response time acceptable (<1ms)
- [ ] No missed transitions during fast rotation

---

## Lesson 25: Zero Crossing Detection

### Objective

Design the AC mains zero-crossing detector for synchronized operation.

### Application

Synchronizing switching events with AC zero-crossings reduces EMI and enables soft-start sequencing.

### Circuit Design

```spice
* Zero-crossing detector using H11AA1 optocoupler
V_ac ac_hot ac_neutral SIN(0 170 60)

* Input resistors (limit LED current to ~5mA peak)
R_in1 ac_hot opto_anode 33k
R_in2 ac_neutral opto_anode 33k

* Optocoupler model (simplified)
D_opto opto_anode opto_cathode LED
B_photo zc_out 0 V = IF(I(D_opto) > 1m, 0, 3.3)

.model LED D(IS=1e-20 N=1.8)
.tran 100u 50m
```

### Validation Checkpoint

- [ ] ZC pulse generated at each zero crossing
- [ ] Pulse width appropriate for MCU capture
- [ ] Isolation maintained

---

## Lesson 26: Mixed-Signal Integration Simulation

### Objective

Simulate the complete control system with all analog and digital blocks integrated.

### Simulation Exercise

Create a system-level simulation that includes:

- Temperature sensing and PID control
- PWM generation and power stage model
- Safety interlock response
- User input processing

This can be done in Python/NumPy or a mixed-signal simulator:

```python
# System-level simulation framework
class InductionSystem:
    def __init__(self):
        self.temp_setpoint = 100.0  # °C
        self.current_temp = 25.0
        self.power_output = 0.0
        self.pid = PIDController(Kp=5.0, Ki=0.1, Kd=1.0)
        self.state = "IDLE"
        
    def update(self, dt):
        """Main control loop - runs at 100Hz."""
        # Read sensors
        measured_temp = self.read_temperature()
        fan_ok = self.check_fan()
        
        # Safety checks
        if not fan_ok and self.power_output > 0:
            self.emergency_shutdown("FAN_FAILURE")
            return
            
        if measured_temp > 250:  # °C
            self.emergency_shutdown("OVER_TEMP")
            return
        
        # PID control
        if self.state == "HEATING":
            error = self.temp_setpoint - measured_temp
            self.power_output = self.pid.compute(error, dt)
            self.power_output = max(0, min(100, self.power_output))
```

### Validation Checkpoint

- [ ] Closed-loop temperature control demonstrated in simulation
- [ ] Safety interlocks trigger correctly
- [ ] All timing requirements verified

---

# Phase IV: Firmware Development & Algorithm Validation

This phase develops the control algorithms in software, using simulation models to validate behavior before deploying to hardware.

---

## Lesson 27: Pan Detection Algorithm

### Objective

Implement the "pulse-and-measure" pan detection algorithm.

### The "Ping" Algorithm

The MCU injects a small energy pulse and measures the decay time:

| Decay Cycles | Interpretation |
|--------------|----------------|
| ≤5 cycles | Pan present (energy absorbed) |
| ≥20 cycles | No pan (energy rings) |

### Implementation

```c
typedef enum {
    PAN_UNKNOWN,
    PAN_PRESENT,
    PAN_ABSENT
} pan_status_t;

pan_status_t detect_pan(void) {
    // Inject single low-energy pulse
    mcpwm_set_duty(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, 10.0);  // 10% duty
    vTaskDelay(pdMS_TO_TICKS(1));  // 1ms pulse
    mcpwm_set_duty(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, 0.0);
    
    // Measure decay time
    uint32_t start = esp_timer_get_time();
    int cycles = 0;
    
    while (gpio_get_level(CURRENT_SENSE_ZC) == 0 && cycles < 30) {
        // Wait for zero crossing
    }
    
    while (cycles < 30) {
        if (gpio_get_level(CURRENT_SENSE_ZC)) {
            cycles++;
            while (gpio_get_level(CURRENT_SENSE_ZC));  // Wait for low
        }
        
        if ((esp_timer_get_time() - start) > 1000) break;  // 1ms timeout
    }
    
    if (cycles <= 5) return PAN_PRESENT;
    if (cycles >= 20) return PAN_ABSENT;
    return PAN_UNKNOWN;  // Retry needed
}
```

### Simulation Exercise

Model both cases in simulation and verify the detection algorithm works reliably.

### Validation Checkpoint

- [ ] Detection reliable for cast iron
- [ ] Detection reliable for stainless steel
- [ ] Aluminum correctly rejected
- [ ] No false positives with empty coil

---

## Lesson 28: PID Temperature Control

### Objective

Implement and tune the PID control loop for precision temperature regulation.

### Target Performance

| Metric | Target |
|--------|--------|
| Overshoot | Zero (critical for precision cooking) |
| Steady-state error | ≤0.5°C |
| Response time | <60 seconds to setpoint |

### Implementation

```c
typedef struct {
    float Kp, Ki, Kd;
    float integral;
    float prev_error;
    float integral_limit;
} pid_controller_t;

float pid_compute(pid_controller_t *pid, float setpoint, float measured, float dt) {
    float error = setpoint - measured;
    
    // Proportional term
    float P = pid->Kp * error;
    
    // Integral term with anti-windup
    pid->integral += error * dt;
    pid->integral = fmaxf(-pid->integral_limit, fminf(pid->integral_limit, pid->integral));
    float I = pid->Ki * pid->integral;
    
    // Derivative term (on measurement to avoid derivative kick)
    float derivative = (pid->prev_error - error) / dt;  // Note: negative for measurement
    float D = pid->Kd * derivative;
    pid->prev_error = error;
    
    // Combined output
    float output = P + I + D;
    return fmaxf(0.0f, fminf(100.0f, output));  // Clamp 0-100%
}
```

### Simulation Exercise

Create a thermal model of the system (pan + contents + environment) and tune PID parameters in simulation.

```python
# Thermal model for PID tuning
class ThermalModel:
    def __init__(self):
        self.temp = 25.0  # Current temperature
        self.mass = 2.0   # kg (water + pan)
        self.cp = 4186    # J/kg·K (water)
        self.h_loss = 15  # W/K (convection + radiation)
        self.ambient = 25.0
        
    def update(self, power_watts, dt):
        """Update temperature based on power input."""
        # Heat input
        Q_in = power_watts * dt
        
        # Heat loss to environment
        Q_loss = self.h_loss * (self.temp - self.ambient) * dt
        
        # Temperature change
        dT = (Q_in - Q_loss) / (self.mass * self.cp)
        self.temp += dT
        
        return self.temp
```

> **[PHOTO PLACEHOLDER: Step response showing temperature control with tuned PID]**

### Validation Checkpoint

- [ ] Zero overshoot achieved
- [ ] Steady-state error < 0.5°C
- [ ] Tuned Kp, Ki, Kd values documented

---

## Lesson 29: Phase-Locked Loop for ZVS Tracking

### Objective

Implement the software PLL that maintains zero-voltage switching across load variations.

### Theory

As pan loading changes, the optimal operating frequency shifts. The PLL adjusts frequency to maintain the desired phase relationship between drive and current.

### Implementation

```c
typedef struct {
    float frequency;      // Current operating frequency
    float phase_target;   // Target phase angle (radians)
    float Kp, Ki;         // PI gains
    float integral;
    float freq_min, freq_max;
} zvs_pll_t;

void zvs_pll_update(zvs_pll_t *pll, float measured_phase, float dt) {
    // Phase error (positive = current lagging = increase frequency)
    float phase_error = pll->phase_target - measured_phase;
    
    // Wrap phase error to [-π, π]
    while (phase_error > M_PI) phase_error -= 2 * M_PI;
    while (phase_error < -M_PI) phase_error += 2 * M_PI;
    
    // PI control
    float P = pll->Kp * phase_error;
    pll->integral += phase_error * dt;
    float I = pll->Ki * pll->integral;
    
    // Update frequency
    pll->frequency += P + I;
    pll->frequency = fmaxf(pll->freq_min, fminf(pll->freq_max, pll->frequency));
    
    // Apply new frequency to MCPWM
    mcpwm_set_frequency(MCPWM_UNIT_0, MCPWM_TIMER_0, (uint32_t)pll->frequency);
}
```

### Validation Checkpoint

- [ ] PLL locks within 100ms of load change
- [ ] ZVS maintained across 50-100% load
- [ ] Frequency limits prevent unsafe operation

---

## Lesson 30: Watchdog Timer Implementation

### Objective

Implement firmware safety mechanisms including the Task Watchdog Timer.

### Safety Requirement

```c
#include "esp_task_wdt.h"

#define WDT_TIMEOUT_S 2

void app_main(void) {
    // Initialize watchdog
    esp_task_wdt_config_t wdt_config = {
        .timeout_ms = WDT_TIMEOUT_S * 1000,
        .trigger_panic = true,
    };
    esp_task_wdt_init(&wdt_config);
    esp_task_wdt_add(NULL);  // Add current task
    
    while (1) {
        // Normal operation
        control_loop();
        
        // Reset watchdog - MUST be called every iteration
        esp_task_wdt_reset();
        
        vTaskDelay(pdMS_TO_TICKS(10));  // 100Hz loop
    }
}
```

If the watchdog is not reset within 2 seconds, the system reboots to a safe OFF state.

### Validation Checkpoint

- [ ] WDT triggers on infinite loop
- [ ] System boots to safe state after WDT reset
- [ ] Normal operation does not trigger WDT

---

## Lesson 31: State Machine Design

### Objective

Design a robust, safety-critical state machine for induction cooker operation with comprehensive error handling, recovery sequences, and validation.

---

### Overview

The induction cooker state machine coordinates all system operations including power-on self-test, pan detection, heating control, safety monitoring, and fault recovery. This lesson provides a complete implementation with:
- Detailed state transition logic
- Entry/exit actions for each state
- Error recovery sequences
- Timing constraints
- Complete C implementation
- Unit test framework

---

### Complete State Diagram

```
                        POWER ON
                            │
                            ▼
                    ┌───────────────┐
                    │  STATE_INIT   │────────┐
                    │ (Power-On)    │        │ Self-test failed
                    └───────┬───────┘        │
                            │                │
                       Self-test OK          │
                            │                │
                            ▼                │
                    ┌───────────────┐        │
              ┌────▶│  STATE_IDLE   │        │
              │     │ (Standby)     │        │
              │     └───────┬───────┘        │
              │             │                │
              │        User pressed         │
              │        START button          │
              │             │                │
              │             ▼                │
              │     ┌───────────────┐        │
              │     │STATE_PAN_DET  │        │
              │     │ (Pan Detect)  │        │
              │     └───┬───────┬───┘        │
              │         │       │            │
              │    Pan found   No pan        │
              │         │       │(timeout)   │
              │         │       └────────┐   │
              │         ▼                │   │
              │     ┌───────────────┐    │   │
              │     │STATE_PREHEAT  │    │   │
              │     │ (Preheat)     │    │   │
              │     └───────┬───────┘    │   │
              │             │            │   │
              │       Temp reached       │   │
              │        setpoint          │   │
              │             ▼            │   │
              │     ┌───────────────┐    │   │
              │     │ STATE_HEATING │    │   │
              │     │ (Active Heat) │    │   │
              │     └──┬────────┬───┘    │   │
              │        │        │        │   │
              │   User STOP   Pan gone   │   │
              │        │        │        │   │
              │        │        ▼        │   │
              │        │    ┌───────────────┐│
              │        │    │STATE_NO_PAN   ││
              │        │    │(Pan Removed)  ││
              │        │    └───────┬───────┘│
              │        │            │        │
              │        │       Timeout (3s)  │
              │        │            │        │
              │        ▼            ▼        │
              │     ┌──────────────────┐    │
              │     │ STATE_COOLDOWN   │    │
              │     │ (Cool Down)      │    │
              │     └────────┬─────────┘    │
              │              │              │
              │         Temp < 50°C         │
              │              │              │
              └──────────────┘              │
                                            │
              ┌─────────────────────────────┘
              │     ANY CRITICAL FAULT
              │    (Overtemp, Overcurrent,
              │     Fan failure, etc.)
              ▼
        ┌────────────┐
        │STATE_FAULT │
        │ (Lockout)  │
        └──────┬─────┘
               │
          User reset &
        fault cleared
               │
               └──────▶ STATE_INIT
```

---

### State Definitions

#### STATE_INIT (Initialization)

**Purpose:** Power-on self-test (POST) to verify all systems functional before allowing operation.

**Entry Actions:**
1. Initialize hardware peripherals (ADC, PWM, SPI, I2C)
2. Reset all global variables and state flags
3. Turn on status LED (blinking pattern during POST)
4. Set watchdog timer to 5 seconds

**State Logic:**
```c
// Run comprehensive self-test
bool post_passed = true;

post_passed &= test_adc_channels();        // Verify temperature sensors
post_passed &= test_pwm_output();          // Verify gate driver PWM
post_passed &= test_fan_tachometer();      // Verify fan responds
post_passed &= test_safety_interlocks();   // Verify comparators active
post_passed &= test_pan_detection();       // Verify coil current sensing
post_passed &= test_display();             // Verify display communication
post_passed &= test_eeprom();              // Verify calibration data readable

if (post_passed) {
    transition_to(STATE_IDLE);
} else {
    fault_code = FAULT_SELF_TEST_FAILED;
    transition_to(STATE_FAULT);
}
```

**Exit Actions:**
1. Display "READY" message
2. Enable user interface
3. Set status LED to steady green

**Timing:** 100-500 ms typical

**Failure Modes:** → STATE_FAULT if any self-test fails

---

#### STATE_IDLE (Standby)

**Purpose:** Low-power standby awaiting user input.

**Entry Actions:**
1. Disable PWM outputs (no switching)
2. Turn off resonant tank drive
3. Set fan to minimum speed (thermal monitoring only)
4. Enable sleep mode for peripherals (reduce quiescent current)
5. Display last temperature or clock

**State Logic:**
```c
// Monitor for user input
if (button_pressed(BUTTON_START) && target_temp_valid()) {
    transition_to(STATE_PAN_DET);
}

// Continuous background monitoring
monitor_heatsink_temp();  // Ensure IGBTs cool from previous session
monitor_fan_health();     // Check fan still works

// Allow settings changes
if (button_pressed(BUTTON_TEMP_UP)) {
    target_temperature += 5;
    update_display();
}
```

**Exit Actions:**
1. Record start time timestamp
2. Wake up all peripherals
3. Reset PID controller integrals

**Timing:** Indefinite (waiting for user)

**Next States:**
- → STATE_PAN_DET (user pressed START)
- → STATE_FAULT (critical fault detected even in standby)

---

#### STATE_PAN_DET (Pan Detection)

**Purpose:** Verify ferromagnetic cookware present before applying power.

**Entry Actions:**
1. Display "PLACE PAN" message
2. Enable low-power resonant drive (~5% duty cycle, 500W max)
3. Start pan detection timer (timeout = 5 seconds)
4. Reset pan detection confidence counter

**State Logic:**
```c
// Run pan detection algorithm (from Lesson 27)
pan_status_t result = detect_pan_presence();

if (result == PAN_PRESENT) {
    pan_detect_confidence++;
    if (pan_detect_confidence >= 3) {  // Require 3 consecutive confirmations
        transition_to(STATE_PREHEAT);
    }
} else {
    pan_detect_confidence = 0;
}

// Timeout if no pan detected within 5 seconds
if (elapsed_time > 5000) {
    display_message("NO PAN - PLACE PAN AND PRESS START");
    transition_to(STATE_IDLE);
}

// Allow user to cancel
if (button_pressed(BUTTON_STOP)) {
    transition_to(STATE_IDLE);
}
```

**Exit Actions:**
1. If pan found: Record initial pan impedance for tracking
2. If timeout: Clear any partial detection results

**Timing:** 0.1-5 seconds (100 ms per pan check, up to 5 second timeout)

**Next States:**
- → STATE_PREHEAT (pan detected)
- → STATE_IDLE (timeout or user cancel)
- → STATE_FAULT (pan detection hardware failure)

---

#### STATE_PREHEAT (Preheat to Target)

**Purpose:** Rapidly heat cookware to target temperature with aggressive power.

**Entry Actions:**
1. Display "PREHEATING"
2. Enable full PWM drive (up to 100% power)
3. Initialize PID controller with aggressive tuning (Kp=2.0, Ki=0.1, Kd=0.5)
4. Enable ZVS frequency tracking (Lesson 29)
5. Reset overshoot prevention timer

**State Logic:**
```c
// Aggressive heating control
float temp_error = target_temp - current_temp;

if (temp_error > 50.0) {
    // Far from target: full power
    set_power_level(100);
} else if (temp_error > 10.0) {
    // Getting close: reduce power to prevent overshoot
    set_power_level(50);
} else {
    // Very close: switch to PID control
    transition_to(STATE_HEATING);
}

// Safety checks (run every cycle)
check_safety_interlocks();

// Allow user to stop
if (button_pressed(BUTTON_STOP)) {
    transition_to(STATE_COOLDOWN);
}

// Detect pan removal during preheat
if (detect_pan_presence() == PAN_ABSENT) {
    transition_to(STATE_NO_PAN);
}
```

**Exit Actions:**
1. Switch PID to precision tuning (Kp=1.0, Ki=0.05, Kd=0.2)
2. Log preheat time for performance analysis

**Timing:** Variable (30-120 seconds depending on target temp and pan mass)

**Next States:**
- → STATE_HEATING (target reached)
- → STATE_NO_PAN (pan removed)
- → STATE_COOLDOWN (user stop)
- → STATE_FAULT (safety fault)

---

#### STATE_HEATING (Precision Temperature Control)

**Purpose:** Maintain precise temperature using PID control.

**Entry Actions:**
1. Display "HEATING - XXX°C"
2. Enable precision PID control
3. Start cooking timer if configured
4. Set watchdog to 1 second

**State Logic:**
```c
// Run PID temperature controller (from Lesson 28)
float pid_output = pid_update(target_temp, current_temp);
set_power_level(pid_output);  // 0-100%

// Track PLL for ZVS optimization (from Lesson 29)
update_pll_frequency();

// Safety monitoring
if (current_temp > (target_temp + 10)) {
    // Thermal runaway detected
    fault_code = FAULT_THERMAL_RUNAWAY;
    transition_to(STATE_FAULT);
}

check_safety_interlocks();  // Hardware comparator checks

// User interaction
if (button_pressed(BUTTON_STOP)) {
    transition_to(STATE_COOLDOWN);
}

if (button_pressed(BUTTON_TEMP_UP)) {
    target_temp += 5;
    update_display();
}

// Pan removal detection
static uint8_t pan_absent_count = 0;
if (detect_pan_presence() == PAN_ABSENT) {
    pan_absent_count++;
    if (pan_absent_count > 10) {  // 10 consecutive samples (debounce)
        transition_to(STATE_NO_PAN);
    }
} else {
    pan_absent_count = 0;
}

// Cooking timer expiration
if (cooking_timer_enabled && (cooking_time_remaining == 0)) {
    display_message("COMPLETE");
    transition_to(STATE_COOLDOWN);
}
```

**Exit Actions:**
1. Record final temperature and cooking time
2. Save session data to EEPROM for analytics

**Timing:** Indefinite (until user stops or event occurs)

**Next States:**
- → STATE_NO_PAN (pan removed)
- → STATE_COOLDOWN (user stop or timer done)
- → STATE_FAULT (safety fault)

---

#### STATE_NO_PAN (Pan Removed During Operation)

**Purpose:** Pause heating when pan removed, giving user chance to replace it.

**Entry Actions:**
1. Immediately reduce power to 0%
2. Display "PAN REMOVED - REPLACE WITHIN 3 SECONDS"
3. Start countdown timer (3 seconds)
4. Beep/alert user

**State Logic:**
```c
// Check if pan replaced
if (detect_pan_presence() == PAN_PRESENT) {
    // Verify it's the same pan (impedance match within 10%)
    if (pan_impedance_matches()) {
        transition_to(STATE_PREHEAT);  // Resume heating
    } else {
        display_message("DIFFERENT PAN DETECTED");
        transition_to(STATE_COOLDOWN);
    }
}

// Countdown timeout
if (countdown_timer == 0) {
    transition_to(STATE_COOLDOWN);
}

// Allow immediate cancel
if (button_pressed(BUTTON_STOP)) {
    transition_to(STATE_COOLDOWN);
}
```

**Exit Actions:**
1. Clear countdown timer
2. Log pan removal event

**Timing:** 0-3 seconds (user has 3 seconds to replace pan)

**Next States:**
- → STATE_PREHEAT (pan replaced quickly)
- → STATE_COOLDOWN (timeout or user stop)
- → STATE_FAULT (safety fault)

---

#### STATE_COOLDOWN (Active Cooling After Operation)

**Purpose:** Ensure safe cooldown before returning to standby.

**Entry Actions:**
1. Disable all PWM drive (power = 0%)
2. Set fan to maximum speed
3. Display "COOLING - XX°C"
4. Disable user START button (prevent immediate restart)

**State Logic:**
```c
// Monitor cooldown progress
float cooldown_temp = read_heatsink_temperature();

if (cooldown_temp < SAFE_IDLE_TEMP) {  // 50°C typical
    transition_to(STATE_IDLE);
}

// Display countdown or temperature
update_display_temperature(cooldown_temp);

// Safety check: if temp rises during cooldown, fault!
if (cooldown_temp > cooldown_start_temp + 5) {
    fault_code = FAULT_COOLDOWN_OVERHEAT;
    transition_to(STATE_FAULT);
}

// Watchdog monitoring
feed_watchdog();
```

**Exit Actions:**
1. Reduce fan to minimum speed
2. Log session statistics (total energy, time, max temp)
3. Re-enable START button

**Timing:** 30-180 seconds (depends on final temperature)

**Next States:**
- → STATE_IDLE (safe temperature reached)
- → STATE_FAULT (cooldown failure or new fault)

---

#### STATE_FAULT (Lockout - Requires User Intervention)

**Purpose:** Safe shutdown state for critical faults that require user acknowledgment.

**Entry Actions:**
1. **IMMEDIATELY** set power to 0%
2. **IMMEDIATELY** disable all PWM outputs
3. Set fan to maximum speed
4. Activate fault LED (red, flashing)
5. Display fault code and description
6. Log fault to EEPROM with timestamp

**State Logic:**
```c
// Ensure power remains off
set_power_level(0);
disable_all_pwm();

// Display fault information
display_fault_code(fault_code);
display_fault_message(get_fault_string(fault_code));

// Flash LED pattern indicating fault type
update_fault_led_pattern();

// Wait for user acknowledgment
if (button_pressed(BUTTON_RESET)) {
    // Check if fault condition has cleared
    if (fault_cleared()) {
        fault_code = FAULT_NONE;
        transition_to(STATE_INIT);  // Full re-initialization
    } else {
        display_message("FAULT STILL PRESENT - SERVICE REQUIRED");
        // Remain in fault state
    }
}

// Watchdog still active (prevent infinite lockup)
feed_watchdog();

// Monitor critical temperature even in fault state
if (read_heatsink_temperature() > CRITICAL_TEMP) {
    // Hardware thermal shutdown via comparator should have triggered
    // This is backup software check
    trigger_emergency_shutdown();
}
```

**Exit Actions:**
1. Clear fault flags
2. Reset fault counters
3. Log fault recovery to EEPROM

**Timing:** Indefinite (requires user reset)

**Next States:**
- → STATE_INIT (user reset and fault cleared)
- (Remains in STATE_FAULT if fault persists)

---

### Fault Codes and Recovery

| Fault Code | Description | Recovery Action | Auto-Recoverable? |
|------------|-------------|-----------------|-------------------|
| `FAULT_OVER_TEMP` | Heatsink >100°C | Wait for cool <70°C | No (user reset) |
| `FAULT_OVER_CURRENT` | DC bus current >35A | Check for short circuit | No |
| `FAULT_FAN_FAILURE` | Fan tachometer = 0 | Replace/fix fan | No |
| `FAULT_PROBE_OPEN` | RTD resistance >10kΩ | Reconnect probe | No |
| `FAULT_PROBE_SHORT` | RTD resistance <10Ω | Check probe wiring | No |
| `FAULT_THERMAL_RUNAWAY` | Temp rising with power off | Investigate control loop | No |
| `FAULT_SELF_TEST_FAILED` | POST failed | Power cycle, check hardware | No |
| `FAULT_WATCHDOG_RESET` | Software crash | Firmware bug | Yes (automatic) |
| `FAULT_COOLDOWN_OVERHEAT` | Temp rising in cooldown | Check fan, thermal path | No |
| `FAULT_PAN_DETECT_HW` | Pan detection hardware issue | Check coil current sensor | No |

---

### Timing Diagram for Critical Transition

**Transition: HEATING → NO_PAN → COOLDOWN**

```
Time:     0ms   100ms  200ms  300ms  3000ms 3100ms
          │     │      │      │      │      │
Power:   100% ─┐
              │
              └──────────────────0%──────────────────▶
                ▲
                │ Pan removed detected

Pan Det:  OK ───┘
          └─────┴──────┴────ABSENT───────────────────▶
                ▲
                │ Debounce (10 samples @ 10ms)

State:   HEATING│NO_PAN        │COOLDOWN
         ───────┴──────────────┴─────────────────────▶
                ▲              ▲
                │              │
             Power OFF    Timeout (3s)
             Immediate

Display: "185°C"│"PAN REMOVED"│"COOLING 95°C"
         ───────┴──────────────┴─────────────────────▶

Fan:     50% ───┴──────────────┴──── 100% ───────────▶
                                     ▲
                                     │ Max speed for cooldown
```

**Key Timing Requirements:**
- Power must go to 0% within 100 ms of pan removal detection
- Pan removal debounce: 10 consecutive absent readings (100 ms total)
- User has 3 seconds to replace pan before entering cooldown
- Fan ramps to 100% within 500 ms of entering cooldown

---

### Complete Implementation

```c
/* ============================================================================
 * State Machine Implementation for Induction Cooker
 * File: state_machine.c
 * ============================================================================ */

#include <stdint.h>
#include <stdbool.h>
#include "state_machine.h"
#include "peripherals.h"
#include "safety.h"
#include "pan_detect.h"
#include "pid_control.h"

/* State definitions */
typedef enum {
    STATE_INIT,          // Power-on self-test
    STATE_IDLE,          // Standby (no heating)
    STATE_PAN_DET,       // Pan detection
    STATE_PREHEAT,       // Aggressive heating to target
    STATE_HEATING,       // Precision PID control
    STATE_NO_PAN,        // Pan removed (brief pause)
    STATE_COOLDOWN,      // Active cooling after stop
    STATE_FAULT          // Lockout (requires user reset)
} system_state_t;

/* Fault codes */
typedef enum {
    FAULT_NONE = 0,
    FAULT_OVER_TEMP,
    FAULT_OVER_CURRENT,
    FAULT_FAN_FAILURE,
    FAULT_PROBE_OPEN,
    FAULT_PROBE_SHORT,
    FAULT_THERMAL_RUNAWAY,
    FAULT_SELF_TEST_FAILED,
    FAULT_WATCHDOG_RESET,
    FAULT_COOLDOWN_OVERHEAT,
    FAULT_PAN_DETECT_HW
} fault_code_t;

/* State machine context */
static struct {
    system_state_t current_state;
    system_state_t previous_state;
    fault_code_t fault_code;
    uint32_t state_entry_time;
    uint32_t state_duration;

    // State-specific data
    uint8_t pan_detect_confidence;
    uint8_t pan_absent_count;
    float initial_pan_impedance;
    float cooldown_start_temp;
    uint16_t countdown_timer_ms;

    // User inputs
    float target_temperature;
    uint32_t cooking_time_ms;
    bool cooking_timer_enabled;

} sm_ctx = {
    .current_state = STATE_INIT,
    .previous_state = STATE_INIT,
    .fault_code = FAULT_NONE,
};

/* Forward declarations */
static void state_init_entry(void);
static void state_init_update(void);
static void state_idle_entry(void);
static void state_idle_update(void);
static void state_pan_det_entry(void);
static void state_pan_det_update(void);
static void state_preheat_entry(void);
static void state_preheat_update(void);
static void state_heating_entry(void);
static void state_heating_update(void);
static void state_no_pan_entry(void);
static void state_no_pan_update(void);
static void state_cooldown_entry(void);
static void state_cooldown_update(void);
static void state_fault_entry(void);
static void state_fault_update(void);

static void transition_to(system_state_t new_state);
static bool run_self_test(void);
static void check_safety_interlocks(void);
static bool fault_cleared(void);
static const char* get_fault_string(fault_code_t code);

/* ============================================================================
 * Public API
 * ============================================================================ */

void state_machine_init(void) {
    sm_ctx.current_state = STATE_INIT;
    sm_ctx.fault_code = FAULT_NONE;
    sm_ctx.target_temperature = 100.0f;  // Default
    transition_to(STATE_INIT);
}

void state_machine_update(void) {
    // Update state duration
    uint32_t now = get_time_ms();
    sm_ctx.state_duration = now - sm_ctx.state_entry_time;

    // Run current state update function
    switch (sm_ctx.current_state) {
        case STATE_INIT:     state_init_update();     break;
        case STATE_IDLE:     state_idle_update();     break;
        case STATE_PAN_DET:  state_pan_det_update();  break;
        case STATE_PREHEAT:  state_preheat_update();  break;
        case STATE_HEATING:  state_heating_update();  break;
        case STATE_NO_PAN:   state_no_pan_update();   break;
        case STATE_COOLDOWN: state_cooldown_update(); break;
        case STATE_FAULT:    state_fault_update();    break;
    }
}

void state_machine_set_target_temp(float temp_celsius) {
    if (temp_celsius >= 50.0f && temp_celsius <= 250.0f) {
        sm_ctx.target_temperature = temp_celsius;
    }
}

system_state_t state_machine_get_state(void) {
    return sm_ctx.current_state;
}

fault_code_t state_machine_get_fault(void) {
    return sm_ctx.fault_code;
}

/* ============================================================================
 * STATE_INIT Implementation
 * ============================================================================ */

static void state_init_entry(void) {
    // Initialize all peripherals
    peripherals_init();

    // Visual feedback
    led_set_pattern(LED_BLINK_FAST);
    display_show_message("SELF TEST");

    // Set watchdog
    watchdog_set_timeout(5000);  // 5 second timeout for POST
}

static void state_init_update(void) {
    // Run power-on self-test
    bool post_passed = run_self_test();

    if (post_passed) {
        transition_to(STATE_IDLE);
    } else {
        sm_ctx.fault_code = FAULT_SELF_TEST_FAILED;
        transition_to(STATE_FAULT);
    }
}

static bool run_self_test(void) {
    bool passed = true;

    // Test ADC channels
    passed &= test_adc_calibration();
    if (!passed) return false;

    // Test PWM output
    passed &= test_pwm_generation();
    if (!passed) return false;

    // Test fan
    passed &= test_fan_operation();
    if (!passed) return false;

    // Test safety interlocks
    passed &= test_hardware_comparators();
    if (!passed) return false;

    // Test temperature sensors
    passed &= test_rtd_sensor();
    if (!passed) return false;

    // Test display
    passed &= test_display_communication();
    if (!passed) return false;

    // Test EEPROM
    passed &= test_eeprom_read();
    if (!passed) return false;

    return true;
}

/* ============================================================================
 * STATE_IDLE Implementation
 * ============================================================================ */

static void state_idle_entry(void) {
    // Disable power output
    pwm_set_duty_cycle(0);
    power_set_level(0);

    // Minimum fan speed
    fan_set_speed(FAN_SPEED_MIN);

    // Visual feedback
    led_set_pattern(LED_STEADY_GREEN);
    display_show_message("READY");

    // Enable sleep mode for power savings
    peripherals_enter_low_power();

    // Set watchdog to longer timeout
    watchdog_set_timeout(10000);  // 10 seconds in idle
}

static void state_idle_update(void) {
    // Check for start button
    if (button_is_pressed(BUTTON_START) && sm_ctx.target_temperature > 0) {
        transition_to(STATE_PAN_DET);
        return;
    }

    // Handle temperature adjustment
    if (button_is_pressed(BUTTON_TEMP_UP)) {
        sm_ctx.target_temperature += 5.0f;
        if (sm_ctx.target_temperature > 250.0f) {
            sm_ctx.target_temperature = 250.0f;
        }
        display_update_temperature(sm_ctx.target_temperature);
    }

    if (button_is_pressed(BUTTON_TEMP_DOWN)) {
        sm_ctx.target_temperature -= 5.0f;
        if (sm_ctx.target_temperature < 50.0f) {
            sm_ctx.target_temperature = 50.0f;
        }
        display_update_temperature(sm_ctx.target_temperature);
    }

    // Background monitoring
    float heatsink_temp = read_heatsink_temperature();
    monitor_fan_health();

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * STATE_PAN_DET Implementation
 * ============================================================================ */

static void state_pan_det_entry(void) {
    // Wake up from low power
    peripherals_exit_low_power();

    // Enable low-power detection mode
    power_set_level(5);  // 5% power for detection

    // Visual feedback
    display_show_message("PLACE PAN");
    led_set_pattern(LED_BLINK_SLOW);

    // Reset detection state
    sm_ctx.pan_detect_confidence = 0;
    sm_ctx.countdown_timer_ms = 5000;  // 5 second timeout

    // Set watchdog
    watchdog_set_timeout(2000);
}

static void state_pan_det_update(void) {
    // Run pan detection
    pan_status_t result = detect_pan_presence();

    if (result == PAN_PRESENT) {
        sm_ctx.pan_detect_confidence++;
        if (sm_ctx.pan_detect_confidence >= 3) {
            // Record initial pan impedance for tracking
            sm_ctx.initial_pan_impedance = get_pan_impedance();
            transition_to(STATE_PREHEAT);
            return;
        }
    } else {
        sm_ctx.pan_detect_confidence = 0;
    }

    // Check for timeout
    if (sm_ctx.state_duration > sm_ctx.countdown_timer_ms) {
        display_show_message("NO PAN");
        delay_ms(2000);
        transition_to(STATE_IDLE);
        return;
    }

    // Check for cancel
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_IDLE);
        return;
    }

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * STATE_PREHEAT Implementation
 * ============================================================================ */

static void state_preheat_entry(void) {
    // Enable full power
    power_enable();

    // Initialize PID with aggressive tuning
    pid_set_tuning(2.0f, 0.1f, 0.5f);  // Kp, Ki, Kd

    // Enable ZVS tracking
    pll_enable();

    // Visual feedback
    display_show_message("PREHEATING");
    led_set_pattern(LED_STEADY_ORANGE);

    // Fan to moderate speed
    fan_set_speed(FAN_SPEED_MEDIUM);

    // Set watchdog
    watchdog_set_timeout(1000);
}

static void state_preheat_update(void) {
    // Read current temperature
    float current_temp = read_pan_temperature();
    float temp_error = sm_ctx.target_temperature - current_temp;

    // Aggressive power control
    if (temp_error > 50.0f) {
        power_set_level(100);  // Full power
    } else if (temp_error > 10.0f) {
        power_set_level(50);   // Reduce to prevent overshoot
    } else {
        // Close to target: switch to precision control
        transition_to(STATE_HEATING);
        return;
    }

    // Safety checks
    check_safety_interlocks();

    // Check for pan removal
    if (detect_pan_presence() == PAN_ABSENT) {
        transition_to(STATE_NO_PAN);
        return;
    }

    // Check for stop button
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    // Update display
    display_update_temperature(current_temp);

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * STATE_HEATING Implementation
 * ============================================================================ */

static void state_heating_entry(void) {
    // Switch to precision PID tuning
    pid_set_tuning(1.0f, 0.05f, 0.2f);
    pid_reset_integral();

    // Visual feedback
    display_show_message("HEATING");
    led_set_pattern(LED_STEADY_GREEN);

    // Fan to automatic control
    fan_set_auto_mode(true);

    // Set watchdog
    watchdog_set_timeout(1000);
}

static void state_heating_update(void) {
    // Read current temperature
    float current_temp = read_pan_temperature();

    // Run PID controller
    float pid_output = pid_update(sm_ctx.target_temperature, current_temp);
    power_set_level((uint8_t)pid_output);  // 0-100%

    // Update PLL for ZVS tracking
    pll_update();

    // Safety checks
    check_safety_interlocks();

    // Thermal runaway detection
    if (current_temp > (sm_ctx.target_temperature + 10.0f)) {
        sm_ctx.fault_code = FAULT_THERMAL_RUNAWAY;
        transition_to(STATE_FAULT);
        return;
    }

    // Pan removal detection (with debouncing)
    if (detect_pan_presence() == PAN_ABSENT) {
        sm_ctx.pan_absent_count++;
        if (sm_ctx.pan_absent_count > 10) {  // 10 consecutive samples
            transition_to(STATE_NO_PAN);
            return;
        }
    } else {
        sm_ctx.pan_absent_count = 0;
    }

    // User input
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    if (button_is_pressed(BUTTON_TEMP_UP)) {
        sm_ctx.target_temperature += 5.0f;
        if (sm_ctx.target_temperature > 250.0f) {
            sm_ctx.target_temperature = 250.0f;
        }
    }

    if (button_is_pressed(BUTTON_TEMP_DOWN)) {
        sm_ctx.target_temperature -= 5.0f;
        if (sm_ctx.target_temperature < 50.0f) {
            sm_ctx.target_temperature = 50.0f;
        }
    }

    // Timer check
    if (sm_ctx.cooking_timer_enabled && sm_ctx.cooking_time_ms == 0) {
        display_show_message("COMPLETE");
        delay_ms(2000);
        transition_to(STATE_COOLDOWN);
        return;
    }

    // Update display
    display_update_temperature(current_temp);

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * STATE_NO_PAN Implementation
 * ============================================================================ */

static void state_no_pan_entry(void) {
    // Immediately cut power
    power_set_level(0);

    // Alert user
    display_show_message("PAN REMOVED");
    led_set_pattern(LED_BLINK_FAST);
    buzzer_beep(500);  // 500 ms beep

    // Start countdown
    sm_ctx.countdown_timer_ms = 3000;  // 3 second window

    // Set watchdog
    watchdog_set_timeout(5000);
}

static void state_no_pan_update(void) {
    // Check if pan replaced
    if (detect_pan_presence() == PAN_PRESENT) {
        // Verify impedance matches (within 10%)
        float current_impedance = get_pan_impedance();
        float impedance_error = fabsf(current_impedance - sm_ctx.initial_pan_impedance) /
                               sm_ctx.initial_pan_impedance;

        if (impedance_error < 0.10f) {
            // Same pan: resume heating
            transition_to(STATE_PREHEAT);
            return;
        } else {
            // Different pan detected
            display_show_message("DIFFERENT PAN");
            delay_ms(2000);
            transition_to(STATE_COOLDOWN);
            return;
        }
    }

    // Check timeout
    if (sm_ctx.state_duration > sm_ctx.countdown_timer_ms) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    // Update countdown display
    uint16_t seconds_remaining = (sm_ctx.countdown_timer_ms - sm_ctx.state_duration) / 1000;
    display_update_countdown(seconds_remaining);

    // Check for immediate cancel
    if (button_is_pressed(BUTTON_STOP)) {
        transition_to(STATE_COOLDOWN);
        return;
    }

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * STATE_COOLDOWN Implementation
 * ============================================================================ */

static void state_cooldown_entry(void) {
    // Disable all power
    power_set_level(0);
    pwm_set_duty_cycle(0);

    // Maximum fan speed
    fan_set_speed(FAN_SPEED_MAX);

    // Record starting temperature
    sm_ctx.cooldown_start_temp = read_heatsink_temperature();

    // Visual feedback
    display_show_message("COOLING");
    led_set_pattern(LED_BLINK_SLOW);

    // Disable start button
    button_set_enabled(BUTTON_START, false);

    // Set watchdog
    watchdog_set_timeout(2000);
}

static void state_cooldown_update(void) {
    // Read temperature
    float current_temp = read_heatsink_temperature();

    // Check if cool enough
    if (current_temp < 50.0f) {
        transition_to(STATE_IDLE);
        return;
    }

    // Safety check: temperature should NOT rise during cooldown
    if (current_temp > (sm_ctx.cooldown_start_temp + 5.0f)) {
        sm_ctx.fault_code = FAULT_COOLDOWN_OVERHEAT;
        transition_to(STATE_FAULT);
        return;
    }

    // Update display
    display_update_temperature(current_temp);

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * STATE_FAULT Implementation
 * ============================================================================ */

static void state_fault_entry(void) {
    // EMERGENCY SHUTDOWN
    power_set_level(0);
    pwm_disable_all();

    // Maximum cooling
    fan_set_speed(FAN_SPEED_MAX);

    // Alert user
    led_set_pattern(LED_FAULT);
    display_show_fault(sm_ctx.fault_code);
    buzzer_beep_continuous();

    // Log to EEPROM
    eeprom_log_fault(sm_ctx.fault_code, get_time_ms());

    // Set watchdog to ensure we don't lock up forever
    watchdog_set_timeout(5000);
}

static void state_fault_update(void) {
    // Ensure power stays off
    power_set_level(0);

    // Display fault info
    display_show_message(get_fault_string(sm_ctx.fault_code));

    // Check for user reset
    if (button_is_pressed(BUTTON_RESET)) {
        if (fault_cleared()) {
            // Fault condition has cleared: reinitialize
            sm_ctx.fault_code = FAULT_NONE;
            transition_to(STATE_INIT);
            return;
        } else {
            // Fault persists
            display_show_message("FAULT PERSISTS");
            buzzer_beep(1000);
        }
    }

    // Monitor critical temperature even in fault
    if (read_heatsink_temperature() > 125.0f) {
        // Hardware shutdown should have triggered
        // This is software backup
        trigger_hardware_shutdown();
    }

    // Feed watchdog
    watchdog_feed();
}

/* ============================================================================
 * Helper Functions
 * ============================================================================ */

static void transition_to(system_state_t new_state) {
    // Record previous state
    sm_ctx.previous_state = sm_ctx.current_state;
    sm_ctx.current_state = new_state;
    sm_ctx.state_entry_time = get_time_ms();
    sm_ctx.state_duration = 0;

    // Call entry function for new state
    switch (new_state) {
        case STATE_INIT:     state_init_entry();     break;
        case STATE_IDLE:     state_idle_entry();     break;
        case STATE_PAN_DET:  state_pan_det_entry();  break;
        case STATE_PREHEAT:  state_preheat_entry();  break;
        case STATE_HEATING:  state_heating_entry();  break;
        case STATE_NO_PAN:   state_no_pan_entry();   break;
        case STATE_COOLDOWN: state_cooldown_entry(); break;
        case STATE_FAULT:    state_fault_entry();    break;
    }
}

static void check_safety_interlocks(void) {
    // Over-temperature check
    if (read_heatsink_temperature() > 100.0f) {
        sm_ctx.fault_code = FAULT_OVER_TEMP;
        transition_to(STATE_FAULT);
    }

    // Over-current check
    if (read_dc_bus_current() > 35.0f) {
        sm_ctx.fault_code = FAULT_OVER_CURRENT;
        transition_to(STATE_FAULT);
    }

    // Fan failure check
    if (!is_fan_running()) {
        sm_ctx.fault_code = FAULT_FAN_FAILURE;
        transition_to(STATE_FAULT);
    }

    // RTD probe checks
    float rtd_resistance = read_rtd_resistance();
    if (rtd_resistance > 10000.0f) {
        sm_ctx.fault_code = FAULT_PROBE_OPEN;
        transition_to(STATE_FAULT);
    }
    if (rtd_resistance < 10.0f) {
        sm_ctx.fault_code = FAULT_PROBE_SHORT;
        transition_to(STATE_FAULT);
    }
}

static bool fault_cleared(void) {
    switch (sm_ctx.fault_code) {
        case FAULT_OVER_TEMP:
            return (read_heatsink_temperature() < 70.0f);

        case FAULT_FAN_FAILURE:
            return is_fan_running();

        case FAULT_PROBE_OPEN:
        case FAULT_PROBE_SHORT:
            float rtd_resistance = read_rtd_resistance();
            return (rtd_resistance > 50.0f && rtd_resistance < 500.0f);

        case FAULT_SELF_TEST_FAILED:
            return run_self_test();

        default:
            return false;  // Most faults require power cycle
    }
}

static const char* get_fault_string(fault_code_t code) {
    switch (code) {
        case FAULT_OVER_TEMP:          return "OVER TEMP";
        case FAULT_OVER_CURRENT:       return "OVER CURRENT";
        case FAULT_FAN_FAILURE:        return "FAN FAILED";
        case FAULT_PROBE_OPEN:         return "PROBE OPEN";
        case FAULT_PROBE_SHORT:        return "PROBE SHORT";
        case FAULT_THERMAL_RUNAWAY:    return "THERMAL RUNAWAY";
        case FAULT_SELF_TEST_FAILED:   return "SELF TEST FAIL";
        case FAULT_WATCHDOG_RESET:     return "WATCHDOG RESET";
        case FAULT_COOLDOWN_OVERHEAT:  return "COOLDOWN FAULT";
        case FAULT_PAN_DETECT_HW:      return "PAN DETECT HW";
        default:                       return "UNKNOWN FAULT";
    }
}
```

---

### Unit Test Framework

```c
/* ============================================================================
 * State Machine Unit Tests
 * File: test_state_machine.c
 * ============================================================================ */

#include "unity.h"
#include "state_machine.h"
#include "mock_peripherals.h"
#include "mock_sensors.h"

void setUp(void) {
    state_machine_init();
    mock_peripherals_reset();
}

void tearDown(void) {
    // Cleanup
}

/* Test: Normal startup sequence */
void test_normal_startup_sequence(void) {
    // Initial state should be INIT
    TEST_ASSERT_EQUAL(STATE_INIT, state_machine_get_state());

    // Mock successful self-test
    mock_self_test_result(true);

    // Update state machine
    state_machine_update();

    // Should transition to IDLE
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/* Test: Self-test failure */
void test_self_test_failure(void) {
    // Mock failed self-test
    mock_self_test_result(false);

    // Update state machine
    state_machine_update();

    // Should transition to FAULT
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_SELF_TEST_FAILED, state_machine_get_fault());
}

/* Test: Pan detection success */
void test_pan_detection_success(void) {
    // Start in IDLE
    force_state(STATE_IDLE);

    // Mock start button press
    mock_button_press(BUTTON_START);
    state_machine_update();

    // Should enter PAN_DET
    TEST_ASSERT_EQUAL(STATE_PAN_DET, state_machine_get_state());

    // Mock pan present (3 times for confidence)
    for (int i = 0; i < 3; i++) {
        mock_pan_detection(PAN_PRESENT);
        state_machine_update();
    }

    // Should transition to PREHEAT
    TEST_ASSERT_EQUAL(STATE_PREHEAT, state_machine_get_state());
}

/* Test: Pan removal during heating */
void test_pan_removal_during_heating(void) {
    // Start in HEATING state
    force_state(STATE_HEATING);

    // Mock pan removal (11 times to exceed debounce threshold)
    for (int i = 0; i < 11; i++) {
        mock_pan_detection(PAN_ABSENT);
        state_machine_update();
        delay_ms(10);
    }

    // Should transition to NO_PAN
    TEST_ASSERT_EQUAL(STATE_NO_PAN, state_machine_get_state());
}

/* Test: Over-temperature fault */
void test_over_temperature_fault(void) {
    // Start in HEATING
    force_state(STATE_HEATING);

    // Mock over-temperature condition
    mock_heatsink_temperature(105.0f);
    state_machine_update();

    // Should transition to FAULT
    TEST_ASSERT_EQUAL(STATE_FAULT, state_machine_get_state());
    TEST_ASSERT_EQUAL(FAULT_OVER_TEMP, state_machine_get_fault());

    // Verify power is off
    TEST_ASSERT_EQUAL(0, get_power_level());
}

/* Test: Cooldown sequence */
void test_cooldown_sequence(void) {
    // Start in COOLDOWN
    force_state(STATE_COOLDOWN);
    mock_heatsink_temperature(80.0f);

    // Gradually reduce temperature
    for (float temp = 80.0f; temp > 45.0f; temp -= 1.0f) {
        mock_heatsink_temperature(temp);
        state_machine_update();
        delay_ms(100);

        // Should still be in COOLDOWN
        TEST_ASSERT_EQUAL(STATE_COOLDOWN, state_machine_get_state());
    }

    // Temperature below threshold
    mock_heatsink_temperature(45.0f);
    state_machine_update();

    // Should transition to IDLE
    TEST_ASSERT_EQUAL(STATE_IDLE, state_machine_get_state());
}

/* Test: State persistence during noise */
void test_state_persistence_during_noise(void) {
    // Start in HEATING
    force_state(STATE_HEATING);
    mock_pan_temperature(100.0f);

    // Introduce momentary pan detection glitches (below debounce threshold)
    for (int i = 0; i < 5; i++) {
        mock_pan_detection(PAN_ABSENT);
        state_machine_update();
        delay_ms(10);
    }

    // Should still be in HEATING (debounce prevents false transitions)
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());

    // Restore pan detection
    mock_pan_detection(PAN_PRESENT);
    state_machine_update();

    // Still HEATING
    TEST_ASSERT_EQUAL(STATE_HEATING, state_machine_get_state());
}

/* Main test runner */
int main(void) {
    UNITY_BEGIN();

    RUN_TEST(test_normal_startup_sequence);
    RUN_TEST(test_self_test_failure);
    RUN_TEST(test_pan_detection_success);
    RUN_TEST(test_pan_removal_during_heating);
    RUN_TEST(test_over_temperature_fault);
    RUN_TEST(test_cooldown_sequence);
    RUN_TEST(test_state_persistence_during_noise);

    return UNITY_END();
}
```

> **[PHOTO PLACEHOLDER: State machine diagram with color-coded states and transition conditions]**

> **[PHOTO PLACEHOLDER: Oscilloscope capture showing power output during HEATING → NO_PAN transition]**

---

### Validation Checkpoint

- [ ] All state transitions implemented and tested
- [ ] No unreachable states (verify with static analysis)
- [ ] All fault conditions lead to safe STATE_FAULT
- [ ] Entry/exit actions defined for each state
- [ ] Debouncing implemented for critical inputs
- [ ] Timing requirements met (power-off < 100ms, etc.)
- [ ] Watchdog properly fed in all states
- [ ] Unit tests pass with >90% code coverage
- [ ] State machine tested with fault injection
- [ ] Recovery sequences validated

---

## Lesson 32: Firmware Integration Testing

### Objective

Integrate all firmware modules and validate against simulation models.

### Test Cases

| Test | Procedure | Expected Result |
|------|-----------|-----------------|
| Normal sequence | Power on → Place pan → Set temp → Heat | Reaches setpoint within 60s |
| Pan removal | Heat to 100°C → Remove pan | Stops heating within 500ms |
| Over-temp | Block airflow | Shuts down at 110°C |
| Fan failure | Disconnect fan | Emergency shutdown |
| Power-on self-test | Normal boot | All peripherals pass |

### Test Harness

```c
// Firmware test harness (runs on target)
void run_integration_tests(void) {
    TEST_ASSERT(test_adc_calibration());
    TEST_ASSERT(test_pwm_output());
    TEST_ASSERT(test_fan_control());
    TEST_ASSERT(test_temperature_sensing());
    TEST_ASSERT(test_safety_interlocks());
    TEST_ASSERT(test_state_machine());
    
    printf("All integration tests passed!\n");
}
```

### Validation Checkpoint

- [ ] All test cases pass
- [ ] Code coverage > 80%
- [ ] No memory leaks detected

---

# Phase V: PCB Design & Manufacturing Preparation

Only after all simulations pass do we proceed to physical PCB design. Every component value and placement decision is informed by the preceding simulation work.

---

## Lesson 33: 4-Layer Stack-up and Design Rules

### Objective

Configure the PCB stack-up and design rules for power electronics requirements.

### Stack-up Configuration

| Layer | Name | Function | Copper Weight |
|-------|------|----------|---------------|
| L1 | Top | Components, high-current traces | 2 oz |
| L2 | GND | Continuous ground plane | 1 oz |
| L3 | PWR | Power planes (24V, 5V, 15V_iso) | 1 oz |
| L4 | Bottom | Signal routing, aux components | 1 oz |

### Design Rules

| Rule | Value | Justification |
|------|-------|---------------|
| HV clearance | >6mm | Across isolation boundary |
| HV trace width | 5mm min | 30A current handling |
| Signal trace | 6 mil min | Standard capability |
| Via size | 0.3mm drill | Thermal vias under IGBTs |

> **[PHOTO PLACEHOLDER: KiCad stack-up editor showing 4-layer configuration]**

### Validation Checkpoint

- [ ] Stack-up defined in KiCad
- [ ] Net classes configured
- [ ] Design rules imported

---

## Lesson 34: Power Stage Layout — Minimizing Loop Inductance

### Objective

Layout the power stage with minimal parasitic inductance.

### The Laminated Bus Technique

Route DC+ and DC- on adjacent layers (L1 and L4, or using internal planes), directly overlapping, to create a low-inductance bus structure. The magnetic fields cancel, reducing loop inductance.

### Layout Guidelines

1. Place DC link capacitors adjacent to IGBT module
2. Route DC+ and DC- with maximum overlap
3. Minimize loop area: capacitor → high-side IGBT → low-side IGBT → capacitor
4. Keep gate drive traces short and away from power traces

> **[PHOTO PLACEHOLDER: PCB layout showing laminated bus structure]**

### Validation Checkpoint

- [ ] Power loop area minimized
- [ ] DC+/DC- overlap maximized
- [ ] Gate drive routing verified

---

## Lesson 35: Isolation Boundary and Creepage

### Objective

Implement proper isolation boundaries and safety clearances.

### The "Moat" Technique

Draw a physical slot (cutout) along the isolation boundary to prevent surface contamination from bridging high and low voltage domains.

### Clearance Requirements

| Boundary | Clearance | Creepage |
|----------|-----------|----------|
| HV to LV | 6mm | 8mm |
| Across slot | 3mm + slot | N/A |
| HV to heatsink | 4mm | 6mm |

> **[PHOTO PLACEHOLDER: PCB showing isolation slot and creepage distances]**

### Validation Checkpoint

- [ ] Isolation slot drawn on Edge.Cuts
- [ ] Clearances meet requirements
- [ ] No copper pours crossing boundary

---

## Lesson 36: Thermal Relief and Heat Spreading

### Objective

Design thermal management features into the PCB.

### Key Techniques

1. **Solid copper connections** (not thermal relief spokes) for IGBT tabs
2. **Thermal vias** under power components (array of 0.3mm vias)
3. **Airflow alignment** with component placement
4. **Copper pours** on all layers under hot components

### Via Array Specification

```
IGBT thermal via array:
- Via diameter: 0.3mm
- Via pitch: 1.0mm
- Array size: 5x5 minimum
- Fill: Plugged and plated (optional)
```

### Validation Checkpoint

- [ ] Thermal vias placed under IGBTs
- [ ] No thermal relief on power pads
- [ ] Airflow path unobstructed

---

## Lesson 37: Design Rule Check and Manufacturing Files

### Objective

Finalize design for manufacturing.

### DRC Checklist

- [ ] Clearance violations: 0
- [ ] Unconnected nets: 0
- [ ] Via-in-pad violations: 0
- [ ] Silk screen overlap: 0
- [ ] Courtyard violations: 0

### Manufacturing File Generation

```bash
#!/bin/bash
# generate_fab.sh

# Generate Gerbers
kicad-cli pcb export gerbers \
  --output output/gerbers/ \
  Induction_Core_v1.kicad_pcb

# Generate drill files
kicad-cli pcb export drill \
  --output output/gerbers/ \
  Induction_Core_v1.kicad_pcb

# Generate BOM
kicad-cli sch export bom \
  --output output/bom.csv \
  Induction_Core_v1.kicad_sch

# Generate pick-and-place
kicad-cli pcb export pos \
  --output output/pnp.csv \
  Induction_Core_v1.kicad_pcb
```

### Validation Checkpoint

- [ ] DRC passes with zero errors
- [ ] Gerbers reviewed in viewer
- [ ] BOM complete and accurate

---

## Lesson 38: 3D Mechanical Integration

### Objective

Verify mechanical fit and design the enclosure.

### Environmental Hardening

| Feature | Purpose |
|---------|---------|
| Louvered vents | Spill protection |
| Conformal coating | Humidity/corrosion resistance |
| Thermal isolation | Protect electronics from cooking heat |
| Tortuous air path | Prevent liquid ingress |

### Enclosure Checklist

- [ ] PCB mounting holes align
- [ ] Heatsink clearance adequate
- [ ] Fan airflow path clear
- [ ] User controls accessible
- [ ] Display visible
- [ ] Probe connector accessible

> **[PHOTO PLACEHOLDER: 3D render of PCB in enclosure with airflow arrows]**

---

# Phase VI: Hardware Assembly, Integration & Calibration

The final phase brings the validated design to physical reality. Having simulated every aspect, hardware bring-up should proceed smoothly.

---

## Lesson 39: Component Procurement and Inspection

### Objective

Procure components and verify authenticity.

### Critical Verification

| Component | Check |
|-----------|-------|
| IGBTs | Part marking, authorized distributor |
| Capacitors | Voltage rating, series number |
| ICs | Package matches datasheet |
| Magnetics | Inductance measurement |

### Counterfeit Avoidance

- Source only from authorized distributors (Digi-Key, Mouser, Arrow)
- Verify date codes are reasonable
- Compare package dimensions to datasheet
- For IGBTs: verify Infineon hologram if present

### Validation Checkpoint

- [ ] All components received
- [ ] Visual inspection passed
- [ ] Critical components verified

---

## Lesson 40: Low-Voltage Bring-up

### Objective

Power up and verify all low-voltage circuits before connecting high-voltage.

### Verification Sequence

| Step | Test | Expected |
|------|------|----------|
| 1 | Apply 24V input | No smoke, current < 100mA |
| 2 | Measure 5V rail | 5.0V ±2%, ripple < 50mVpp |
| 3 | Measure 3.3V rail | 3.3V ±2%, ripple < 10mVpp |
| 4 | ESP32 boot | Serial output visible |
| 5 | I2C scan | All sensors respond |
| 6 | Gate signals | Correct frequency, dead time |

> **[PHOTO PLACEHOLDER: Oscilloscope capture of gate driver outputs]**

### Validation Checkpoint

- [ ] All voltages within spec
- [ ] ESP32 boots and runs test firmware
- [ ] All I2C devices detected

---

## Lesson 41: The "Dim Bulb" Test

### Objective

Safely test the high-voltage stage.

### Procedure

Wire an incandescent light bulb (100W) in series with the AC input. If a short exists, the bulb illuminates brightly, limiting current and preventing damage.

| Bulb State | Interpretation |
|------------|----------------|
| Off | Very low current (good for startup) |
| Dim glow | Normal operating current |
| Bright | Excessive current (fault!) |

### Test Sequence

1. Install 100W bulb in series with AC input
2. Apply power with system in IDLE state
3. Bulb should be OFF or very dim
4. Command low power (10%)
5. Bulb should glow dimly
6. If bulb is bright at any point, remove power immediately

> **[PHOTO PLACEHOLDER: Test setup showing dim bulb tester configuration]**

### Validation Checkpoint

- [ ] Standby current acceptable
- [ ] Low-power operation verified
- [ ] No shorts detected

---

## Lesson 42: Full Power Testing

### Objective

Validate full power operation against simulation predictions.

### Verification

Compare measured values against simulation:

| Parameter | Simulation | Measured | Pass? |
|-----------|------------|----------|-------|
| Tank current (peak) | 30A | | |
| IGBT Vce (max) | 450V | | |
| Heatsink temp @ 1500W | 75°C | | |
| Power delivery | 1500W | | |

> **[PHOTO PLACEHOLDER: Comparison of simulated vs measured waveforms]**

### Validation Checkpoint

- [ ] All measurements within 20% of simulation
- [ ] Thermal limits not exceeded
- [ ] ZVS verified on oscilloscope

---

## Lesson 43: Temperature Calibration

### Objective

Calibrate the temperature sensing system.

### Two-Point Calibration

| Reference | Temperature | ADC Reading |
|-----------|-------------|-------------|
| Ice bath | 0.0°C | [measured] |
| Boiling water | 100.0°C* | [measured] |

*Adjust for altitude: subtract 0.5°C per 150m elevation

### Calibration Procedure

```c
// Store calibration coefficients in NVS
float cal_offset;  // °C offset at 0°C
float cal_scale;   // Scale factor

void calibrate_temperature(float raw_0c, float raw_100c) {
    // Two-point linear calibration
    cal_scale = 100.0f / (raw_100c - raw_0c);
    cal_offset = -raw_0c * cal_scale;
    
    // Store in non-volatile storage
    nvs_set_float("cal_scale", cal_scale);
    nvs_set_float("cal_offset", cal_offset);
}

float read_calibrated_temp(float raw) {
    return raw * cal_scale + cal_offset;
}
```

### Validation Checkpoint

- [ ] 0°C reference accurate
- [ ] 100°C reference accurate
- [ ] Mid-range accuracy verified (50°C)

---

## Lesson 44: Final Validation and Documentation

### Objective

Complete final testing and create documentation package.

### Final Test Suite

| Test | Procedure | Criteria |
|------|-----------|----------|
| Temperature accuracy | Compare to reference thermometer | ±0.5°C |
| Power control | Measure with power meter | ±5% |
| Safety interlock | Trigger each fault | Response < 1ms |
| Pan detection | Test with various cookware | 100% accuracy |
| Endurance | Run at 1500W for 4 hours | No thermal runaway |

### Documentation Package

- [ ] Complete schematic PDF
- [ ] BOM with supplier information
- [ ] Simulation files and results
- [ ] Firmware source code (with comments)
- [ ] Test results and calibration data
- [ ] Assembly instructions
- [ ] Operating manual

### Final Validation Checkpoint

- [ ] All tests pass
- [ ] Documentation complete
- [ ] System ready for use

---

# Appendix A: Component Glossary & Technical Justification

| Component | Description | Simple Explanation | Technical Justification |
|-----------|-------------|-------------------|------------------------|
| **IKW40N120H3** | 1200V 40A IGBT | The power switch that turns on/off 40,000 times per second | High Speed 3 technology for low Eoff. Vce(sat)≈2.05V. RθJC=0.35K/W |
| **UCC21550** | Isolated Gate Driver | Amplifies control signals while maintaining electrical isolation | CMTI >100V/ns. Hardware dead-time. 4A/6A drive current |
| **LMR51430** | Wide-Vin Buck | Efficiently converts 24V to 5V for digital circuits | 65V max input handles surges. 1.1MHz for small magnetics |
| **UCC14140-Q1** | Isolated DC/DC Module | Powers the floating high-side driver through magnetic isolation | 3kV isolation. <3.5pF coupling capacitance. >150kV/µs CMTI. Integrated transformer. Adjustable 15–25V output with optional negative bias. AEC-Q100 automotive qualified |
| **ESP32-S3** | Dual-Core MCU | The brain that controls timing, temperature, and user interface | MCPWM peripheral with <10ns dead-time resolution. Dual-core for safety |
| **MAX31865** | RTD Converter | Precision temperature measurement for the probe | 15-bit resolution. Built-in fault detection for safety shutdown |
| **ADuM1250** | I2C Isolator | Provides safety isolation for user-accessible probe | Bidirectional I2C. Critical safety component for user protection |

---

# Appendix B: Simulation File Index

All simulation files are organized in the `/simulation` directory:

```
/simulation/
├── /models/
│   ├── IKW40N120H3.lib           # IGBT model
│   ├── UCC21550_behavioral.sub   # Gate driver model
│   ├── UCC14140_behavioral.sub   # Isolated DC/DC module model
│   ├── LMR51430_avg.lib          # Buck converter model
│   └── thermal_network.sub       # Thermal equivalent circuit
├── /testbenches/
│   ├── 01_led_test.cir         # Basic validation (Lesson 02)
│   ├── 02_gate_charge.cir      # Gate drive comparison (Lesson 03)
│   ├── 03_double_pulse.cir     # IGBT characterization (Lesson 04)
│   ├── 04_dead_time.cir        # Driver dead time (Lesson 05)
│   ├── 05_buck_transient.cir   # Power supply (Lesson 06)
│   ├── 06_ldo_filter.cir       # Low-noise 3.3V (Lesson 07)
│   ├── 07_isolated_supply.cir  # High-side supply (Lesson 08)
│   ├── 08_soft_start.cir       # Inrush limiting (Lesson 09)
│   ├── 09_hv_sensing.cir       # Bus monitoring (Lesson 10)
│   ├── 10_tank_response.cir    # Resonant tank (Lesson 11)
│   ├── 11_cap_bank.cir         # Capacitor bank (Lesson 12)
│   ├── 12_pan_model.cir        # Transformer model (Lesson 13)
│   ├── 13_full_bridge.cir      # Complete power stage (Lesson 14)
│   ├── 14_zvs_analysis.cir     # ZVS verification (Lesson 15)
│   ├── 15_snubber.cir          # Voltage spike suppression (Lesson 16)
│   ├── 16_current_sense.cir    # CT modeling (Lesson 17)
│   └── 17_thermal.cir          # Thermal analysis (Lesson 18)
├── /python/
│   ├── pid_tuning.py           # PID simulation (Lesson 28)
│   ├── thermal_model.py        # System thermal model
│   ├── state_machine_test.py   # State machine validation
│   └── plot_results.py         # Waveform visualization
└── /results/
    └── [exported waveforms and data]
```

Each testbench file includes comments explaining the purpose, expected results, and validation criteria.

---

# Appendix C: KiCad Symbol Sources

KiCad symbols for all ICs can be acquired from the following sources:

| Component | Source |
|-----------|--------|
| **IKW40N120H3** | Infineon product page, SnapEDA, or Ultra Librarian |
| **UCC21550** | TI's official symbol library or Ultra Librarian |
| **LMR51430** | TI's official symbol library |
| **ESP32-S3** | Espressif official KiCad library (GitHub) |
| **MAX31865** | SnapEDA or Analog Devices |
| **ADuM1250** | SnapEDA or Analog Devices |
| **UCC14140-Q1** | TI's official symbol library or Ultra Librarian |

Alternatively, symbols can be generated using KiCad's built-in Symbol Editor based on datasheet pinouts.

---

# Appendix D: Safety Checklist

Before operating the completed system:

- [ ] Verified all isolation boundaries with megohmmeter (>10MΩ @ 500V)
- [ ] Verified earth ground continuity (<0.1Ω)
- [ ] Tested all hardware interlocks
- [ ] Verified watchdog timer operation
- [ ] Tested emergency stop function
- [ ] Verified over-temperature shutdown
- [ ] Tested fan failure detection
- [ ] Verified pan detection rejects incompatible cookware
- [ ] Tested probe fault detection (open/short)
- [ ] Verified conformal coating integrity (if applied)
- [ ] Documented all test results

---

*End of Curriculum*
