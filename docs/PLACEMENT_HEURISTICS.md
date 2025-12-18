# PCB Placement Heuristics for Temper Induction Cooker

This document summarizes placement guidelines and heuristics extracted from component datasheets and power electronics best practices.

## 1. High-Priority Constraints (Safety & Function)

### 1.1 Isolation Barrier (Reinforced)
- **Components**: UCC21550, ADUM1250, UCC14140-Q1
- **Heuristic**: Maintain strictly ≥ 8.0mm creepage and clearance between primary (LV) and secondary (HV) sides.
- **Implementation**: Use board zones and KeepoutAreas to enforce the gap.

### 1.2 Gate Drive Loop
- **Components**: UCC21550 → IKW40N120H3 (IGBTs)
- **Heuristic**: Keep gate driver within 20mm of IGBT gate pins.
- **Heuristic**: Route gate and emitter-return traces as a differential pair to minimize loop area (< 20nH target).
- **Implementation**: use `CriticalPath` constraints with `max_length_mm: 20`.

### 1.3 High-Power Switching Node (SW)
- **Components**: Q1 Emitter, Q2 Collector, Resonant Tank connection.
- **Heuristic**: Minimize SW node copper area to reduce parasitic capacitance and EMI coupling.
- **Heuristic**: Keep sensitive analog circuitry (RTD, current sense) at least 20mm away from the SW node.
- **Implementation**: use `NoiseSensitiveIsolationLoss` with `min_distance_mm: 20`.

## 2. Component-Specific Heuristics

### 2.1 Decoupling Capacitors
- **Heuristic**: Place local decoupling (100nF ceramic) within 5mm of the IC power pins.
- **Heuristic**: Place bulk decoupling (1uF - 10uF) within 10mm.
- **Implementation**: use `DecouplingLoss` (auto-detect).

### 2.2 ESP32-S3 MCU
- **Heuristic**: Antenna area must extend beyond the board edge or have ≥ 15mm clearance from copper planes and components.
- **Heuristic**: Keep switching converters (LMR51430) at least 25mm away from the MCU to prevent RF interference.

### 2.3 Thermal Management
- **Heuristic**: Place IGBTs (Q1, Q2) along the top edge of the board for heatsink mounting.
- **Heuristic**: Maintain ≥ 10mm spacing between high-power components to prevent thermal hotspots.
- **Implementation**: use `ThermalLoss` with `prefer_edge: true`.

### 2.4 Resonant Capacitor (C_RES)
- **Heuristic**: Place as close as possible to the Induction Coil connector and the IGBT switch node to minimize high-frequency loop inductance.

## 3. Signal Integrity

### 3.1 Analog Sensing (MAX31865)
- **Heuristic**: Keep the RTD converter and its filter components away from the buck converter and gate drive signals.
- **Heuristic**: Route RTD traces as a differential pair.

### 3.2 Current Transformer (CT)
- **Heuristic**: Place the CT close to the power entry point or the resonant tank return path.
- **Heuristic**: Keep burden resistor immediately adjacent to CT pins.

## 4. Summary of Constraint Values

| Constraint | Value | Priority |
|------------|-------|----------|
| HV-LV Isolation Gap | 8.0 mm | Critical (P0) |
| Gate Drive Path Length | < 20 mm | High (P1) |
| Decoupling Cap Distance | < 5 mm | High (P1) |
| Noise Isolation (Analog) | > 20 mm | Medium (P2) |
| MCU Antenna Clearance | > 15 mm | High (P1) |
| Thermal Spacing | > 10 mm | Medium (P2) |
