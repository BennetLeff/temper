# REQ-REV-02: Layout Review Checklist

## 1. Physical & Mechanical
- [ ] Board dimensions match mechanical specification (100mm x 150mm).
- [ ] Mounting hole locations and sizes verified (M3 pattern).
- [ ] Connector positions verified for chassis accessibility.
- [ ] Component height restrictions checked (especially electrolytic caps).
- [ ] Edge clearance maintained for all components (min 3mm).

## 2. Component Placement
- [ ] Critical loop areas minimized (Gate drive, Commutation).
- [ ] High-power components (IGBTs, Diodes) placed for optimal heat dissipation.
- [ ] Sensitive analog components isolated from switching nodes (>10mm).
- [ ] Decoupling capacitors placed as close as possible to IC power pins (<3mm).
- [ ] Reference resistors (RTD) placed close to the ADC.
- [ ] Component orientations consistent for manufacturability (isomorphic groups aligned).

## 3. High Voltage & Isolation
- [ ] 10mm clearance maintained between HV and LV domains.
- [ ] Primary/Secondary isolation barrier clearly defined and unbroken.
- [ ] Creepage and clearance distances verified for 240VAC operation.
- [ ] Slotting used where necessary to increase creepage.

## 4. Power & Grounding
- [ ] Star grounding point for power and signal grounds verified.
- [ ] Power traces (DC Bus, Resonant Tank) sized for 15A continuous current.
- [ ] Multiple vias used for layer transitions on high-current paths.
- [ ] Ground plane integrity - no large slots or bottlenecks under critical signals.
- [ ] Thermal vias placed under heat-generating components.

## 5. Routing (if applicable)
- [ ] Differential pairs (SPI?) routed with matched length.
- [ ] Signal integrity - no high-speed traces near board edges or HV sections.
- [ ] Clean exit paths from all pads (no 'wiggles').
- [ ] Silk-screen markings clear and legible (DNP components marked).

## 6. Manufacturing & DRC
- [ ] KiCad DRC passes with zero errors.
- [ ] Netlist matches schematic (run KiCad netlist compare).
- [ ] All components have valid MPNs and footprints.
- [ ] Solder mask and paste mask layers verified.
- [ ] Edge.Cuts layer is closed and valid.

## Sign-off
**Date:** ________________  
**Reviewer:** ________________  
**Status:** [ ] Approved [ ] Conditionally Approved [ ] Rejected
