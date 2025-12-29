# GND Plane Implementation

## Overview

The GND net spans 141mm vertically with 22 pins and large gaps (up to 52mm), making it difficult to fully autoroute. Instead of routing GND as traces, we exclude it from routing and rely on a copper pour/plane on an inner layer (In1.Cu or In2.Cu).

## Implementation

### DSN Exporter Support

The DSN exporter now supports an `exclude_nets` parameter:

```python
exporter.export_pcb(exclude_nets={"GND"})
```

This removes the specified nets from the DSN `(network ...)` section, preventing FreeRouter from attempting to route them.

### CLI Usage

```bash
cd packages/temper-placer && uv run python ../../export_dsn.py \
    ../../pcb/temper_boundary_fixed.kicad_pcb \
    ../../pcb/temper_gnd_plane.dsn \
    --exclude-nets GND
```

## Results

| Metric | Without GND Exclusion | With GND Exclusion |
|--------|----------------------|-------------------|
| Nets to route | 24 | 23 |
| Expected completion | 96.4% | 100% |
| Routed via plane | None | GND |

## Trade-offs

### Advantages
- 100% routing completion for signal nets
- Better EMI shielding from continuous ground plane
- Lower impedance ground return paths
- Standard practice for 4-layer PCBs

### Considerations
- GND plane must be added manually in KiCad
- Ensure thermal relief pads connect to plane
- Via stitching may be needed for critical GND connections

## References

- [DSN Layer Fix](DSN_LAYER_FIX.md) - Original layer handling documentation
- Commit a9c9510 - GND gap analysis
