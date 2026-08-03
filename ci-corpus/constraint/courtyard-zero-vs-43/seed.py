"""Defect shape: CourtyardCheckStage reported 0 collisions; kicad-cli DRC
found 43 (27 courtyards_overlap + 16 pth_inside_courtyard) on the identical
board -- docs/solutions/logic-errors/
courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md. Same
root cause family as the rotation-sign class: courtyard rectangles were
computed with the wrong rotation convention, so the stage's own detector
could not see the overlaps its export then contained. The consolidating fix
is guarded by check_no_raw_rotation_trig.py (core/courtyard.py is in
GUARDED_FILES); this gate is not seed-parameterizable (fixed guarded-file
list at the repo root), so the incident is registered UNVERIFIED.
"""


def _courtyard_corners_unsound(cx, cy, w, h, theta):
    # BUG: standard-math R(+theta) instead of KiCad's R(-theta) child
    # rotation -- conceals overlaps that real DRC reports.
    import math

    return (
        cx + w / 2 * math.cos(theta) - h / 2 * math.sin(theta),
        cy + w / 2 * math.sin(theta) + h / 2 * math.cos(theta),
    )
