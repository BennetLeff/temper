# Induction Cooking System Curriculum Overview

This document provides a structured overview, table of contents, and dependency mapping for the "Advanced Power Electronics Curriculum: Modular Design and Validation of a High-Precision Induction Cooking System".

## Curriculum Structure

The curriculum is organized into the following major sections and lessons:

### Executive Summary
*   [Executive Summary](#executive-summary)
*   [Core Philosophy: Simulation Before Silicon](#core-philosophy-simulation-before-silicon)
*   [Curriculum Structure](#curriculum-structure)

### KiCad Simulation Workflow Overview
*   [KiCad Simulation Workflow Overview](#kicad-simulation-workflow-overview)
*   [Two Simulation Approaches](#two-simulation-approaches)
*   [KiCad Simulation Symbol Library](#kicad-simulation-symbol-library)
*   [Essential KiCad Simulation Setup](#essential-kicad-simulation-setup)
*   [Working with External SPICE Models](#working-with-external-spice-models)
*   [Common Simulation Pitfalls and Solutions](#common-simulation-pitfalls-and-solutions)
*   [Helpful ngspice Options](#helpful-ngspice-options)
*   [Quick Reference: SPICE Source Specifications](#quick-reference-spice-source-specifications)

### Phase I: Simulation Environment & Component Characterization
*   [Lesson 01: The Engineering Environment & Hierarchical Project Architecture](#lesson-01-the-engineering-environment--hierarchical-project-architecture)
*   [Lesson 02: SPICE Fundamentals — The Passive Signaler](#lesson-02-spice-fundamentals--the-passive-signaler)
*   [Lesson 03: The Gate Charge Model — Understanding Switching Speed](#lesson-03-the-gate-charge-model--understanding-switching-speed)
*   [Lesson 04: IGBT Characterization — The IKW40N120H3 Model](#lesson-04-igbt-characterization--the-ikw40n120h3-model)
*   [Lesson 05: Gate Driver Characterization — The UCC21550](#lesson-05-gate-driver-characterization--the-ucc21550)
*   [Lesson 06: Wide-Vin Buck Converter — The LMR51430](#lesson-06-wide-vin-buck-converter--the-lmr51430)
*   [Lesson 07: Low-Noise 3.3V Regulation — The LDO and Pi-Filter](#lesson-07-low-noise-33v-regulation--the-ldo-and-pi-filter)
*   [Lesson 08: Isolated High-Side Supply — The TI UCC14140-Q1](#lesson-08-isolated-high-side-supply--the-ti-ucc14140-q1)
*   [Lesson 09: AC Input Stage — Rectification and Soft-Start](#lesson-09-ac-input-stage--rectification-and-soft-start)
*   [Lesson 10: High-Voltage Bus Monitoring — Isolated Sensing](#lesson-10-high-voltage-bus-monitoring--isolated-sensing)

### Phase II: Power Stage Simulation & Resonant Tank Design
*   [Lesson 11: Resonance Theory — The Half-Bridge Topology](#lesson-11-resonance-theory--the-half-bridge-topology)
*   [Lesson 12: Capacitor Bank Design — Handling Reactive Power](#lesson-12-capacitor-bank-design--handling-reactive-power)
*   [Lesson 13: Pan Load Modeling — The Transformer Equivalent](#lesson-13-pan-load-modeling--the-transformer-equivalent)
*   [Lesson 14: Full Half-Bridge Simulation](#lesson-14-full-half-bridge-simulation)
*   [Lesson 15: Zero Voltage Switching (ZVS) Analysis](#lesson-15-zero-voltage-switching-zvs-analysis)
*   [Lesson 16: Snubber Design and Voltage Spike Suppression](#lesson-16-snubber-design-and-voltage-spike-suppression)
*   [Lesson 17: Current Sensing — The Current Transformer](#lesson-17-current-sensing--the-current-transformer)
*   [Lesson 18: Thermal Modeling and Heatsink Requirements](#lesson-18-thermal-modeling-and-heatsink-requirements)

### Phase III: Control System & Sensing Simulation
*   [Lesson 19: ESP32-S3 Peripheral Simulation](#lesson-19-esp32-s3-peripheral-simulation)
*   [Lesson 20: Temperature Sensing — NTC Thermistor Interface](#lesson-20-temperature-sensing--ntc-thermistor-interface)
*   [Lesson 21: RTD Probe Interface with Isolation](#lesson-21-rtd-probe-interface-with-isolation)
*   [Lesson 22: Hardware Safety Interlocks](#lesson-22-hardware-safety-interlocks)
*   [Lesson 23: Fan Control with Tachometer Feedback](#lesson-23-fan-control-with-tachometer-feedback)
*   [Lesson 24: User Interface — Encoder and Display](#lesson-24-user-interface--encoder-and-display)
*   [Lesson 25: Zero Crossing Detection](#lesson-25-zero-crossing-detection)
*   [Lesson 26: Mixed-Signal Integration Simulation](#lesson-26-mixed-signal-integration-simulation)

### Phase IV: Firmware Development & Algorithm Validation
*   [Lesson 27: Pan Detection Algorithm](#lesson-27-pan-detection-algorithm)
*   [Lesson 28: PID Temperature Control](#lesson-28-pid-temperature-control)
*   [Lesson 29: Phase-Locked Loop for ZVS Tracking](#lesson-29-phase-locked-loop-for-zvs-tracking)
*   [Lesson 30: Watchdog Timer Implementation](#lesson-30-watchdog-timer-implementation)
*   [Lesson 31: State Machine Design](#lesson-31-state-machine-design)
*   [Lesson 32: Firmware Integration Testing](#lesson-32-firmware-integration-testing)

### Phase V: PCB Design & Manufacturing Preparation
*   [Lesson 33: 4-Layer Stack-up and Design Rules](#lesson-33-4-layer-stack-up-and-design-rules)
*   [Lesson 34: Power Stage Layout — Minimizing Loop Inductance](#lesson-34-power-stage-layout--minimizing-loop-inductance)
*   [Lesson 35: Isolation Boundary and Creepage](#lesson-35-isolation-boundary-and-creepage)
*   [Lesson 36: Thermal Relief and Heat Spreading](#lesson-36-thermal-relief-and-heat-spreading)
*   [Lesson 37: Design Rule Check and Manufacturing Files](#lesson-37-design-rule-check-and-manufacturing-files)
*   [Lesson 38: 3D Mechanical Integration](#lesson-38-3d-mechanical-integration)

### Phase VI: Hardware Assembly, Integration & Calibration
*   [Lesson 39: Component Procurement and Inspection](#lesson-39-component-procurement-and-inspection)
*   [Lesson 40: Low-Voltage Bring-up](#lesson-40-low-voltage-bring-up)
*   [Lesson 41: The "Dim Bulb" Test](#lesson-41-the-dim-bulb-test)
*   [Lesson 42: Full Power Testing](#lesson-42-full-power-testing)
*   [Lesson 43: Temperature Calibration](#lesson-43-temperature-calibration)
*   [Lesson 44: Final Validation and Documentation](#lesson-44-final-validation-and-documentation)

### Appendix A: Component Glossary & Technical Justification
*   [Appendix A: Component Glossary & Technical Justification](#appendix-a-component-glossary--technical-justification)
### Appendix B: Simulation File Index
*   [Appendix B: Simulation File Index](#appendix-b-simulation-file-index)
### Appendix C: KiCad Symbol Sources
*   [Appendix C: KiCad Symbol Sources](#appendix-c-kicad-symbol-sources)
### Appendix D: Safety Checklist
*   [Appendix D: Safety Checklist](#appendix-d-safety-checklist)


## Lesson Dependencies

This section outlines the dependencies between lessons. A lesson is listed as dependent if its understanding or implementation relies on concepts or results from previous lessons.

*   **Executive Summary:** No direct dependencies within the curriculum; foundational overview.
*   **KiCad Simulation Workflow Overview:** No direct dependencies; foundational for the entire simulation approach.

*   **Phase I: Simulation Environment & Component Characterization**
    *   **Lesson 01: The Engineering Environment & Hierarchical Project Architecture:** Foundational. Depends on understanding general EE concepts.
    *   **Lesson 02: SPICE Fundamentals — The Passive Signaler:** Depends on Lesson 01 (KiCad project setup, basic SPICE concepts).
    *   **Lesson 03: The Gate Charge Model — Understanding Switching Speed:** Depends on Lesson 01 (KiCad setup), Lesson 02 (basic SPICE, component models).
    *   **Lesson 04: IGBT Characterization — The IKW40N120H3 Model:** Depends on Lesson 01, Lesson 02, Lesson 03 (SPICE models, understanding switching).
    *   **Lesson 05: Gate Driver Characterization — The UCC21550:** Depends on Lesson 01, Lesson 02, Lesson 03, Lesson 04 (Gate driver characterization relies on understanding IGBT behavior and basic SPICE).
    *   **Lesson 06: Wide-Vin Buck Converter — The LMR51430:** Depends on Lesson 01, Lesson 02 (Basic SPICE, component models).
    *   **Lesson 07: Low-Noise 3.3V Regulation — The LDO and Pi-Filter:** Depends on Lesson 06 (Filter design for LDO, which is part of aux power), Lesson 02 (basic filter simulation).
    *   **Lesson 08: Isolated High-Side Supply — The TI UCC14140-Q1:** Depends on Lesson 01, Lesson 02, Lesson 03, Lesson 04, Lesson 05 (Isolated supply for gate drivers, understanding isolation and gate drive requirements).
    *   **Lesson 09: AC Input Stage — Rectification and Soft-Start:** Depends on Lesson 01, Lesson 02 (Basic simulation of AC input, rectifiers).
    *   **Lesson 10: High-Voltage Bus Monitoring — Isolated Sensing:** Depends on Lesson 01, Lesson 02, Lesson 09 (Isolated sensing for AC bus, HV considerations).

*   **Phase II: Power Stage Simulation & Resonant Tank Design**
    *   **Lesson 11: Resonance Theory — The Half-Bridge Topology:** Depends on Lesson 01 (KiCad simulation), Lesson 02 (SPICE fundamentals).
    *   **Lesson 12: Capacitor Bank Design — Handling Reactive Power:** Depends on Lesson 11 (Capacitor bank design based on resonant tank analysis).
    *   **Lesson 13: Pan Load Modeling — The Transformer Equivalent:** Depends on Lesson 01, Lesson 02, Lesson 11 (Pan load model integrated into resonant tank).
    *   **Lesson 14: Full Half-Bridge Simulation:** Depends on Lessons 04 (IGBT model), 05 (Gate driver), 08 (Isolated supply), 11 (Resonant tank), 12 (Capacitor bank), 13 (Pan load model). This is a major integration lesson.
    *   **Lesson 15: Zero Voltage Switching (ZVS) Analysis:** Depends on Lesson 14 (ZVS analysis on full power stage).
    *   **Lesson 16: Snubber Design and Voltage Spike Suppression:** Depends on Lesson 14 (Snubber design for full power stage).
    *   **Lesson 17: Current Sensing — The Current Transformer:** Depends on Lesson 14 (Current sensing for power stage).
    *   **Lesson 18: Thermal Modeling and Heatsink Requirements:** Depends on Lesson 04 (IGBT thermal data), Lesson 14 (Power loss data from full power stage simulation).

*   **Phase III: Control System & Sensing Simulation**
    *   **Lesson 19: ESP32-S3 Peripheral Simulation:** Depends on Lesson 01 (basic behavioral modeling).
    *   **Lesson 20: Temperature Sensing — NTC Thermistor Interface:** Depends on Lesson 01, Lesson 02 (NTC thermistor model, filter simulation).
    *   **Lesson 21: RTD Probe Interface with Isolation:** Depends on Lesson 01, Lesson 02, Lesson 08 (Isolation concepts from isolated supply).
    *   **Lesson 22: Hardware Safety Interlocks:** Depends on Lesson 01, Lesson 02 (Comparator simulation).
    *   **Lesson 23: Fan Control with Tachometer Feedback:** Depends on Lesson 01 (basic behavioral modeling).
    *   **Lesson 24: User Interface — Encoder and Display:** Depends on Lesson 01 (basic filter simulation).
    *   **Lesson 25: Zero Crossing Detection:** Depends on Lesson 01, Lesson 02 (Optocoupler simulation, AC signal handling).
    *   **Lesson 26: Mixed-Signal Integration Simulation:** Depends on Lessons 19-25 (Integration of all control and sensing blocks).

*   **Phase IV: Firmware Development & Algorithm Validation**
    *   **Lesson 27: Pan Detection Algorithm:** Depends on Lesson 17 (Current sensing for detection).
    *   **Lesson 28: PID Temperature Control:** Depends on Lesson 20 (Temperature sensing), Lesson 26 (Mixed-signal integration for simulation environment).
    *   **Lesson 29: Phase-Locked Loop for ZVS Tracking:** Depends on Lesson 15 (ZVS theory), Lesson 17 (Current sensing for phase detection), Lesson 19 (MCPWM peripheral).
    *   **Lesson 30: Watchdog Timer Implementation:** Foundational firmware safety, minimal external dependencies.
    *   **Lesson 31: State Machine Design:** Depends on Lessons 27, 28, 29, 30, and all safety lessons (21, 22, 23). Integrates all control logic.
    *   **Lesson 32: Firmware Integration Testing:** Depends on Lesson 31 (Testing the complete firmware).

*   **Phase V: PCB Design & Manufacturing Preparation**
    *   **Lesson 33: 4-Layer Stack-up and Design Rules:** Foundational PCB design.
    *   **Lesson 34: Power Stage Layout — Minimizing Loop Inductance:** Depends on Lesson 14 (Understanding power stage components), Lesson 33 (PCB design rules).
    *   **Lesson 35: Isolation Boundary and Creepage:** Depends on Lesson 08 (Isolation requirements), Lesson 33 (PCB design rules).
    *   **Lesson 36: Thermal Relief and Heat Spreading:** Depends on Lesson 18 (Thermal modeling), Lesson 33 (PCB design rules).
    *   **Lesson 37: Design Rule Check and Manufacturing Files:** Depends on Lessons 33-36 (All previous PCB design lessons).
    *   **Lesson 38: 3D Mechanical Integration:** Depends on Lessons 33-37 (Physical PCB layout).

*   **Phase VI: Hardware Assembly, Integration & Calibration**
    *   **Lesson 39: Component Procurement and Inspection:** Foundational, no direct lesson dependencies but relies on BOM from previous phases.
    *   **Lesson 40: Low-Voltage Bring-up:** Depends on Lessons 06, 07, 19 (Low-voltage power supplies and MCU operation).
    *   **Lesson 41: The "Dim Bulb" Test:** Depends on Lesson 09 (AC input stage).
    *   **Lesson 42: Full Power Testing:** Depends on Lessons 14, 15, 17, 18, 29 (Power stage, ZVS, current sensing, thermal, PLL validation).
    *   **Lesson 43: Temperature Calibration:** Depends on Lesson 20, 21 (Temperature sensing hardware).
    *   **Lesson 44: Final Validation and Documentation:** Depends on all previous lessons (Full system test and documentation).

*   **Appendices:**
    *   **Appendix A: Component Glossary & Technical Justification:** References components discussed throughout the curriculum.
    *   **Appendix B: Simulation File Index:** References simulation files from all lessons.
    *   **Appendix C: KiCad Symbol Sources:** References KiCad usage throughout the curriculum.
    *   **Appendix D: Safety Checklist:** References safety concepts from various lessons.