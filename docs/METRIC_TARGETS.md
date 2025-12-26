# Placement & Routing Metric Targets

This document defines the success criteria for the Temper placement optimizer, grounded in physical requirements.

## 1. Geometric Feasibility (Hard Constraint)

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| `overlap_count` | 4 | **0** | Components cannot physically occupy the same space. |
| `overlap_area_mm2` | 12.5 | **0.0** | Total collision area must be zero. |
| `zone_violation_count` | 0 | **0** | Components must respect electrical isolation zones. |
| `boundary_violation_count` | 0 | **0** | Components must stay on the board. |

## 2. Thermal Safety

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| `max_junction_temp_c` | 118.8 | **< 100.0** | 125°C is absolute max; 100°C provides 25°C safety margin for reliability. |
| `thermal_margin_c` | 31.2 | **> 50.0** | Difference between 150°C (failure) and estimated Tj. |
| `edge_distance_avg_mm` | 25.0 | **< 15.0** | Power devices must be near board edges for heatsink mounting. |

## 3. EMI / Loop Area

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| `gate_loop_area_mm2` | 45.2 | **< 25.0** | V_noise = L * di/dt. Reducing area reduces inductance and ringing. |
| `power_loop_area_mm2` | 120.5 | **< 80.0** | Main switching loop is primary EMI source. |

## 4. Routability

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| `max_congestion` | 1.10 | **< 0.85** | Utilization > 1.0 indicates unroutable bottlenecks. |
| `overflow_cells` | 12 | **0** | No cells should exceed routing capacity. |
| `completion_pct` | 92.5% | **100%** | All nets must be routed for a functional PCB. |

## 5. Signal Integrity (Post-Routing)

| Metric | Baseline | Target | Rationale |
|--------|----------|--------|-----------|
| `max_length_mismatch` | N/A | **< 2.0 mm** | Differential pairs/buses must have matched arrival times. |
| `total_wirelength_mm` | 1250 | **< 1000** | Minimizing wirelength reduces parasitic resistance and EMI. |
