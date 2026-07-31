"""Single source of truth for the mains<->SELV physical isolation-barrier width.

Hoisted here (2026-07-29) out of ``scripts/check_isolation_keepout.py`` so it
can be imported by BOTH that gate and
``temper_placer.placer.cp_sat.isolation_barrier`` (the CP-SAT placer's
corridor-width constraint) without an illegal dependency direction:

- ``scripts/`` already imports from ``packages/temper-placer/src`` --
  ``check_isolation_keepout.py`` itself does
  ``from temper_placer.core.pad_geometry import pad_bounding_radius`` --
  because ``scripts/`` entry points run against the workspace venv, which
  has every ``packages/*`` member installed editable.
- The reverse -- ``packages/temper-placer/src`` importing from ``scripts/``
  -- is NOT an established or desirable direction:
  ``isolation_barrier.py``'s own ``load_domain_manifest_nets`` docstring
  already notes ``scripts/`` "is not a package this src/ tree can import"
  (no ``__init__.py``, no stable public surface, and pytest does not put
  ``scripts/`` on ``sys.path`` the way it puts ``packages/*/src`` there).
  A library's ``src/`` tree depending on a loose top-level script would
  also invert the natural layering: ``scripts/`` are top-level orchestration
  and CI gates that are *allowed* to depend on the packages, not the other
  way around.

Putting the constant in ``temper_placer.core`` keeps the existing
``scripts -> packages`` direction intact and gives
``packages/temper-placer``'s own consumer a normal intra-package import --
no new dependency edge is created in either direction.

See ``scripts/check_isolation_keepout.py``'s module docstring (section
"Which clearance figure: BASIC clearance through REINFORCED creepage") for
the full IEC 60335-1 derivation and the PD2 enclosure prerequisite. PD2 is
the selected production architecture, not a convenience override: the
gasketed PCB compartment must be kept outside the coil/heatsink airflow path
and verified before release. If that prerequisite fails, the PD3 fallback
figure must be selected in both enforcement points together. Never shrink
this figure to make a gate pass.
"""

from __future__ import annotations

# REINFORCED creepage, pollution degree 2, material group IIIb, <=400V
# working voltage -- 8.0mm at the selected PD2 production target. See
# scripts/check_isolation_keepout.py's module docstring for the full
# derivation and the mechanical prerequisite.
MIN_BARRIER_WIDTH_MM = 8.0

__all__ = ["MIN_BARRIER_WIDTH_MM"]
