<!-- provenance: base=5794d22f7ec4fa63291715a7b0526c2f01c5591f; branch=codex/pd3-retarget; dirty=true -->

# PD2 production decision: protected PCB compartment is a release prerequisite

**Date:** 2026-07-30

## Decision

The production architecture selects Pollution Degree 2 for the PCB
microenvironment. This is the IEC 60335-2-6 enclosure exception, not a claim
that the existing vented layout already qualifies. The board's enforced
reinforced-creepage target is therefore **8.0 mm** for the selected
architecture, with **12.6 mm** retained as the fallback if the enclosure
exception is not implemented or cannot be verified.

## Mechanical conditions that earn the exception

The released appliance must have a covered, gasketed PCB compartment that is
separate from the coil/heatsink forced-air path. The compartment must prevent
grease, steam, and cooking aerosols from reaching exposed PCB insulation,
including through service openings and cable penetrations. The assembly
drawing must identify the cover, gasket interface, partition, and inspection
points, and production inspection must verify that the barrier is present and
intact.

The existing airflow and assembly documents now state these conditions. The
outer chassis being enclosed, or the glass cooktop gasket, is not sufficient:
the PCB's own insulation must be protected from the polluted airflow path.

## Coupled electrical enforcement

The following enforcement points must remain on the same selected figure:

| Enforcement point | PD2 target |
|---|---:|
| KiCad DRU generator (`HV_CREEPAGE_ENFORCED_MM`) | 8.0 mm |
| Physical isolation keepout (`MIN_BARRIER_WIDTH_MM`) | 8.0 mm |
| Placement corridor derived from the shared constant | 8.0 mm + design margin |
| PD3 fallback if enclosure fails | 12.6 mm |

The PD3 candidate remains declared in the generator so a future
reclassification can change both enforcement points deliberately. It must
not be silently removed or replaced with a smaller figure.

## What this decision does not close

The current board still has no named `MAINS_SELV_ISOLATION_BARRIER` keepout.
The physical keepout gate therefore remains red until a real board geometry
change supplies a full-layer, edge-to-edge barrier and places each domain on
the correct side. The current placement is interleaved; adding an arbitrary
vertical strip would produce far-side crossings and copper intrusions. This
decision therefore authorizes the PD2 target but does not claim that the
board is yet fabrication-ready.

The PD3 determination in
`docs/evidence/2026-07-30-pollution-degree-determination.md` remains valid
for the prior unsealed/vented layout. It is superseded for the intended
production architecture only after the enclosure conditions above are
implemented and verified.
