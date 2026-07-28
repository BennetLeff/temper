"""Re-export shim: geometry helpers moved into production code.

Now live at `temper_placer.requirements.validators._geometry`, alongside the
clearance validator, so the CP-SAT encoder can use them without production
importing from the test tree.

Every underscore-prefixed helper is re-exported **explicitly**. `import *` skips
names beginning with an underscore, so the star import below does not carry them.
When this shim was created (c8302fc5) only `_distance` was listed, which silently
broke five validator modules -- pick_and_place, ground_plane, layout_review,
switching_nodes and emi_filter all raised ImportError on load. Their test modules
catch ImportError and substitute placeholders, so the breakage surfaced as 62
tests skipping with the message "not yet implemented" rather than as an error.
The validators were implemented the whole time.

Keep this list complete. A missing name here disables a validator silently.
"""

from temper_placer.requirements.validators._geometry import *  # noqa: F401,F403
from temper_placer.requirements.validators._geometry import (  # noqa: F401
    _distance,
    _on_segment,
    _orientation,
    _point_in_rect,
    _point_to_polyline_distance,
    _point_to_segment_distance,
    _polyline_length,
    _polyline_min_distance,
    _polylines_intersect,
    _rects_overlap,
    _segment_to_segment_distance,
    _segments_intersect,
)
