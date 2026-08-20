"""
Rotation transforms — Rust-backed via temper_geometry.

Shim-debt cleanup (2026-08-19): the pure re-export lines (``x = _tg.x`` for
the rotation-matrix / pin-transform / batch kernels) were collapsed —
importers import those symbols from ``temper_geometry`` directly. This
module keeps only:

- ``get_rotated_bounds``: the re-export the pinned validation oracles
  (``tests/validation/_geometric_py_oracle.py`` and
  ``_validation_metrics_py_oracle.py``) import from this module path, and
- the rotation one-hot helpers whose default-arg logic stays Python-side
  (``n_angles=4`` / ``allowed=None`` are not Rust pyfunction defaults).
"""

import temper_geometry as _tg

# =============================================================================
# Pinned-oracle re-export (required by tests/validation/_*_py_oracle.py)
# =============================================================================

get_rotated_bounds = _tg.get_rotated_bounds

# =============================================================================
# Utility Functions (non-collapsible: have Python-side default logic)
# =============================================================================


def rotation_index_to_onehot(idx, n_angles=4):
    """Convert rotation index (0-3) to one-hot vector.

    Args:
        idx: Rotation index
        n_angles: Number of discrete angles (default 4)

    Returns:
        One-hot vector as list
    """
    return _tg.rotation_index_to_onehot(idx, n_angles)


def rotation_degrees_to_onehot(deg, allowed=None):
    """Convert rotation in degrees to one-hot vector.

    Args:
        deg: Rotation in degrees
        allowed: List of allowed angles in degrees (default [0, 90, 180, 270])

    Returns:
        One-hot vector
    """
    if allowed is None:
        allowed = [0.0, 90.0, 180.0, 270.0]
    return _tg.rotation_degrees_to_onehot(deg, allowed)


def onehot_to_rotation_degrees(onehot, allowed=None):
    """Convert one-hot rotation vector to degrees.

    Args:
        onehot: One-hot or soft rotation vector
        allowed: List of allowed angles in degrees (default [0, 90, 180, 270])

    Returns:
        Rotation in degrees
    """
    if allowed is None:
        allowed = [0.0, 90.0, 180.0, 270.0]
    return _tg.onehot_to_rotation_degrees(onehot, allowed)


def onehot_to_rotation_radians(onehot, allowed_rad=None):
    """Convert one-hot rotation vector to radians.

    Args:
        onehot: One-hot or soft rotation vector
        allowed_rad: List of allowed angles in radians

    Returns:
        Rotation in radians
    """
    if allowed_rad is None:
        allowed_rad = [0.0, 1.5707963267948966, 3.141592653589793, 4.71238898038469]
    return _tg.onehot_to_rotation_radians(onehot, allowed_rad)
