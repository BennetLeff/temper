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
