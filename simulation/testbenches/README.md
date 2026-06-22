# SPICE Testbench Template System

Generate SPICE testbenches from templates to eliminate boilerplate.

## Quick Start

```bash
python3 gen_testbench.py \
  --test-name "My Test" \
  --task-id "task-1" \
  --purpose "Test purpose" \
  --title "Test Title" \
  --component-lib "path/to/lib.lib" \
  --sections "* Circuit description
V1 in 0 DC 5" \
  --outputs "print v(out)" \
  --measurements "meas tran Vavg AVG v(out)" \
  -o output.cir
```

## Templates

Located in `templates/`:

- `template_header.spice` - File header with test name, task ID, purpose
- `template_options.spice` - Simulation options (RELTOL, ABSTOL, METHOD=TRAP)
- `template_control.spice` - Control block with run, outputs, measurements

## Example

Input circuit:
```spice
* Circuit Description
V1 vcc 0 DC 3.3
R1 vcc led 150
D1 led 0 LED_MODEL
.tran 10u 10m
```

Generates testbench with consistent header, options, and control block.

## Testbench Index

### sim_35: Runaway Boundary Map + Interlock Margin Verification

**File:** `sim_35_runaway_boundary.cir`
**Type:** Coupled electro-thermal transient
**Purpose:** Maps the thermal-runaway boundary of the half-bridge IKW40N120H3 IGBTs
across a 5-parameter sweep (VBUS, K, C_TOL, TAMB, FAN) and verifies
the existing hardware/firmware interlock fires with >=20 C margin.

**Approach:** Two-time-scale simulation -- behavioral half-bridge for the
electrical envelope (fast convergence), RC ladder thermal network
(RthetaJC + RthetaCH + RthetaHA) for junction/case/heatsink dynamics.

**Sweep:** 432 combinations (4 VBUS x 4 K x 3 C_TOL x 3 TAMB x 3 FAN).
Orchestrated by `sweep_runaway_boundary.sh`.

**Classification per sweep point:**
- `steady-state`: Tj < 125 C AND dTj/dt < 0 post-gate
- `runaway`: dTj/dt > +1 C/s post-gate AND Tj > 125 C
- `destructive`: Tj > 175 C at any point

**Toolchain:**
```bash
# Full sweep (may take hours)
./sweep_runaway_boundary.sh

# Visualization
python3 plot_runaway_boundary.py    # -> ../results/runaway_boundary_map.svg

# Margin report
python3 verify_interlock_margin.py  # -> ../results/runaway_interlock_margin.md

# CI regression gate (re-runs worst-3 corners)
./check_runaway_boundary.sh
```

**Inputs:** IKW40N120H3_thermal.sub, pan_load.sub, sweep_params.sp
**Outputs:** runaway_boundary_map.csv, runaway_boundary_map.svg, runaway_interlock_margin.md
**References:** docs/ELECTRICAL_VALIDATION_IMPACT.md, docs/FUNCTIONAL_TEST_CRITERIA.md SS 2.3, docs/plans/2026-06-22-010-feat-runaway-boundary-interlock-plan.md
