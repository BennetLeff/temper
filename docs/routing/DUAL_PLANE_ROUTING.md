# Power Plane Routing Strategy

## Overview

This document describes the power plane routing strategy for achieving **100% automated routing** on the Temper PCB.

## Problem

FreeRouter consistently left 1-2 incomplete connections when routing all nets:
- **GND** - High fanout (many decoupling caps, ICs)
- **_PLUS3V3** / **+3V3** - MCU VDD and peripheral power, spanning large distances

## Solution: Dual Power Planes

Exclude both GND and +3V3 from trace routing. These nets connect via:
- **In1.Cu** - Ground plane
- **In2.Cu** - 3.3V power plane (or mixed signal/power)

### Export Command

```bash
python3 export_dsn.py \
    pcb/temper_boundary_fixed.kicad_pcb \
    pcb/output.dsn \
    --exclude-nets GND,_PLUS3V3
```

### Routing Command

```bash
java -Djava.awt.headless=true -jar ~/tools/freerouting.jar \
    -de pcb/output.dsn \
    -do pcb/output.ses \
    -mp 50
```

## Results

| Metric | With All Nets | Dual Plane |
|--------|---------------|------------|
| Nets to route | 22 | 20 |
| Incomplete | 1-2 | **0** |
| Vias | 20 | 9 |
| Total wirelength | 1139mm | 1063mm |
| Clearance violations | 0 | 0 |

## Implementation Notes

### Bug Fix in dsn_exporter.py

The `--exclude-nets` argument requires matching both original and sanitized net names:
- Original: `+3V3` (from KiCad)
- Sanitized: `_PLUS3V3` (for SPECCTRA compatibility)

Fixed by checking both names in the exclusion logic.

### Trade-offs

**Pros:**
- 100% automated routing
- Fewer vias (cleaner signal integrity)
- Shorter total wirelength
- Power planes provide better decoupling

**Cons:**
- Requires inner layer planes in PCB stackup
- GND and 3V3 vias still needed for plane connections
- Manual via stitching may be needed for thermal relief

## See Also

- [GND_PLANE.md](./GND_PLANE.md) - Original GND-only plane approach
- [PLUS3V3_INCOMPLETE_ANALYSIS.md](./PLUS3V3_INCOMPLETE_ANALYSIS.md) - Analysis of the incomplete connection
