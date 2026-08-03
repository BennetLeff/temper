"""Defect shape: the R(+theta)/R(-theta) footprint-child rotation sign bug.

docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md: KiCad
rotates a footprint child (pad offset, courtyard vertex) by R(-theta); this
repo reimplemented the standard-math R(+theta)/CCW convention instead, in 12
places, concealing real clearance hazards on 18 production components. The 12
are consolidated into temper_placer.geometry.kicad_transform and guarded by
check_no_raw_rotation_trig.py; that gate reads a fixed GUARDED_FILES list at
the repo root and is not seed-parameterizable, so the incident is registered
UNVERIFIED (encodable via R42 gate-mutation tooling).
"""


def _rotate_local_to_world_unsound(x, y, theta):
    # BUG: R(+theta) -- the wrong convention for KiCad footprint children.
    import math

    return (
        x * math.cos(theta) - y * math.sin(theta),
        x * math.sin(theta) + y * math.cos(theta),
    )
