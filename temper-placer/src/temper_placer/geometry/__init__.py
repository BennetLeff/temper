"""
Geometry engine for temper-placer.

This module provides differentiable geometric primitives and operations:
- Signed Distance Functions (SDF) for shapes
- Overlap detection between component bounding boxes
- Boundary containment checking
- Zone membership testing
- Polygon operations (point-in-polygon, etc.)

All operations are implemented in JAX for automatic differentiation.
The SDF approach provides smooth gradients even when shapes don't overlap,
guiding the optimizer toward valid configurations.
"""

# Imports will be added as modules are implemented
# from temper_placer.geometry.primitives import Rectangle, Polygon, Circle
# from temper_placer.geometry.sdf import sdf_rectangle, sdf_polygon
# from temper_placer.geometry.overlap import compute_overlap_matrix, overlap_loss
# from temper_placer.geometry.boundary import boundary_violation_loss
# from temper_placer.geometry.zones import zone_membership_loss

__all__ = []
