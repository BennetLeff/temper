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

DERIVED PER PAIRING, NOT WRITTEN (changed 2026-08-19)
-----------------------------------------------------
``MIN_BARRIER_WIDTH_MM`` used to be the literal ``12.6`` -- IEC 60335-1
Table 17 row **iv** (>250-400 V), PD3, doubled -- applied as ONE SCALAR
across a 27-net HV domain and a 35-net SELV domain.

``docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md`` (commit
``0cbc04248``) established from primary text that **the single scalar is the
defect, not its value**. Row iv suits a 230 V design. This is a 120 V design
whose doubler midpoint is Y-cap coupled to PE, so ``+170V_BUS`` is a
+/-170 V HALF-bus; IEC 60664-1 cl. 3.2.1.1 dimensions creepage on "the
long-term r.m.s. value", and 170 V d.c. with 120 V r.m.s. superimposed is
208.1 V r.m.s. -- row iii. The scalar was therefore **simultaneously ~1.6x
too generous for the DC-bus crossing and at least ~1.6x too small for the
resonant-tank crossing**:

===========================  ==========  ===========  ============  ============
pairing                      V (r.m.s.)  insulation   table/row     required
===========================  ==========  ===========  ============  ============
mains <-> SELV               120         reinforced   17, ii        4.8 mm
DC bus <-> SELV              170 d.c.    reinforced   17, iii       8.0 mm
bus rail-to-rail             340 d.c.    FUNCTIONAL   18, iii       5.0 mm
switching <-> SELV           ~170 @47k   reinforced   out of scope  NOT DETERMINABLE
tank <-> SELV                570.5 @47k  reinforced   17, vi + oos  >=20.0 mm, NOT DETERMINABLE
===========================  ==========  ===========  ============  ============

The per-pairing requirement now comes from a declared, dated,
digest-anchored set of facts::

    elec/insulation_manifest.yaml       groups, frequencies, and each
                                        PAIRING's long-term r.m.s. working
                                        voltage, each with a cited basis
      -> insulation.rs                  cross-domain -> reinforced,
                                        same-domain -> functional (cl.3.3.5)
      -> voltage_range_for(v_rms)       IEC 60664-1 cl. 3.2.1.1
      -> table_17_lookup / table_18_lookup
      -> x2 for reinforced              cl. 29.2.3
      -> Requirement{Determined | IndeterminateWithFloor}

``temper_placer.core.insulation_coordination`` is the loader; ask it
``requirement_for_nets(a, b)`` for a real per-pairing figure.

WHAT ``MIN_BARRIER_WIDTH_MM`` STILL MEANS -- AND WHY IT WENT UP
--------------------------------------------------------------
It is **not** the requirement of any one pairing. It is the width of the
single *geometric* barrier that separates the whole HV domain from the whole
SELV domain, and one physical barrier is governed by its **worst** crossing
(the determination, sec 6.1: *"They are the same physical barrier as rows 3
and 4 and are governed by whichever pairing is worst."*). That crossing is
``tank-out``/``tank.c_tank1-p2`` against SELV, so this figure moves
**12.6 mm -> 20.0 mm**. Lowering it to the DC-bus figure would have tightened
the only over-provisioned part of the barrier while leaving the
under-provisioned part untouched.

AND IT IS A FLOOR, NOT A REQUIREMENT
------------------------------------
:data:`MIN_BARRIER_WIDTH_IS_DETERMINATE` is ``False``. The tank and
switch-node crossings run at 47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz
scope ceiling; cl. 2.3 routes dimensioning above it to IEC 60664-4, which is
paywalled and was not obtained. 20.0 mm is the *proven lower bound* from the
<=30 kHz tables -- **a barrier that clears it is not thereby compliant**. Any
consumer that reports a verdict must report "cannot determine", never
"pass", while that flag is ``False``. Never make an indeterminate pairing
pass by giving it a number.

Never shrink either figure to make a gate pass.
"""

from __future__ import annotations

from temper_placer.core.insulation_coordination import (
    barrier_floor_mm as _barrier_floor_mm,
)
from temper_placer.core.insulation_coordination import (
    barrier_is_determinable as _barrier_is_determinable,
)

# The width of the single geometric HV<->SELV barrier: the worst enforceable
# floor over every barrier-crossing pairing. Derived -- see this module's
# docstring for the full chain and `elec/insulation_manifest.yaml` for the
# facts it is derived from.
#
# As declared today: SELV<->TANK, 570.5 Vrms, reinforced, Table 17 row vi
# (10.0 mm) x2 = 20.0 mm. Do not replace this call with its current answer;
# the call IS the mechanism that keeps the number and the declared working
# voltages from drifting apart.
MIN_BARRIER_WIDTH_MM: float = _barrier_floor_mm()

# False while ANY barrier-crossing pairing's requirement is not determinable.
# It is False today (the 47 kHz tank and switch-node crossings). While it is
# False, MIN_BARRIER_WIDTH_MM is a proven LOWER BOUND and clearing it is NOT
# compliance -- see this module's docstring.
MIN_BARRIER_WIDTH_IS_DETERMINATE: bool = _barrier_is_determinable()

__all__ = ["MIN_BARRIER_WIDTH_IS_DETERMINATE", "MIN_BARRIER_WIDTH_MM"]
