provenance: commit=ddf4d9036de0b3481570c22d50a13748e807bc49 dirty=true

# PD2 production decision: protected PCB compartment is a release prerequisite

**Date:** 2026-07-30

**Decided by:** the project owner. This is a human architecture decision, not
a correction of an error and not a standards reinterpretation -- the PD3
analysis this decision supersedes-for-production remains correct for the
construction it examined (see "What this decision does not close" below).
It is recorded here so the basis is auditable: a design choice with a stated,
conditional basis, not a derived or measured result.

## Decision

The production architecture selects Pollution Degree 2 for the PCB
microenvironment. This is the IEC 60335-2-6 enclosure exception, not a claim
that the existing vented layout already qualifies. The board's enforced
reinforced-creepage target is therefore **8.0 mm** for the selected
architecture, with **12.6 mm** retained as the fallback if the enclosure
exception is not implemented or cannot be verified.

See `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md` for
the architecture-options analysis this decision was made against, and
`docs/evidence/2026-07-30-pollution-degree-determination.md` for the PD3
determination this decision is conditional on superseding (see below).

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

| Enforcement point | PD2 target | Status |
|---|---:|---|
| KiCad DRU generator (`HV_CREEPAGE_ENFORCED_MM`) | 8.0 mm | Aligned (this decision) |
| Physical isolation keepout (`MIN_BARRIER_WIDTH_MM`) | 8.0 mm | Aligned (this decision) |
| Placement corridor derived from the shared constant | 8.0 mm + design margin | Aligned (this decision) |
| REQ-SAFE-01 requirements validator (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`'s `IEC60335_REQUIREMENTS` matrix) | 8.0 mm reinforced / 4.0 mm basic | Aligned in a follow-up change (`fix/adopt-pd2-8mm-reinforced-creepage`) -- this decision record's original text left the validator at the PD3 fallback (12.6 mm/6.3 mm) while the other two enforcement points moved to PD2, an inconsistency in its own right; the follow-up closed it, and re-measured REQ-SAFE-01 (86 pairs/123 violations at 12.6mm -> 25 pairs/53 violations at 8.0mm on the same, unchanged `pcb/temper.kicad_pcb`; U3 and U7, this decision's original motivating blockers, now clear). |
| PD3 fallback if enclosure fails | 12.6 mm | Retained in every enforcement point above, never removed |

The PD3 candidate remains declared everywhere above so a future
reclassification can change every enforcement point deliberately. It must
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
