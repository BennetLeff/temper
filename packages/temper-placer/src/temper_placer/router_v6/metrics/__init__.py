"""
Router V6: Routing quality metrics.

Octilinear compliance measurement and diagonal cost incentive.
"""

from temper_placer.router_v6.metrics.octilinear import (
    add_diagonal_incentive,
    octilinear_compliance,
    octilinear_fraction,
)

__all__ = [
    "add_diagonal_incentive",
    "octilinear_compliance",
    "octilinear_fraction",
]
