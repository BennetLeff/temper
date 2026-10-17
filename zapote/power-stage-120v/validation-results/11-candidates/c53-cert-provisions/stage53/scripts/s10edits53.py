"""Stage 53 S10 candidate copper edits (planning model; patches21.edit_base53 will make the same ones).
Group 1: ovp_ok_hot In1 -> In2 (opens a, b)."""
EDITS = {
    "relayer_tracks": [
        ("ovp_ok_hot", ("In1.Cu", "In2.Cu"), (117.847, 55.095), (117.248, 55.695)),
        ("ovp_ok_hot", ("In1.Cu", "In2.Cu"), (117.248, 55.695), (114.448, 55.695)),
    ],
    # open (c): an In2 ocp_kelvin_p patch under the ocp_ok_hot launch and its B.Cu run (y 54.995), stitched by the
    # ocp_kelvin_p via at (119.028, 54.745)
    "add": [
        ("ocp_kelvin_p", "In2.Cu", [(113.8, 53.8), (119.6, 53.8), (119.6, 55.37), (113.8, 55.37)]),
    ],
}
