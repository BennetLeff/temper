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

DERIVED, NOT WRITTEN (changed here)
-----------------------------------
``MIN_BARRIER_WIDTH_MM`` used to be the literal ``12.6``, with the
alternative (``8.0``, pollution degree 2) named in this docstring and the
reasoning in an evidence document. Three structural gaps followed: nothing
connected the three, so every investigation re-derived the argument and some
got it wrong; the docstring's stated precondition ("the sealed, gasketed PCB
compartment ... verified before release") had **no mechanism behind it**; and
the physical state and the number could drift apart in either direction --
build the compartment and nothing loosened, remove it and nothing
re-tightened.

The figure is now computed, on every import, from a declared physical claim
about the enclosure::

    elec/enclosure_manifest.yaml      declared facts + dated, commit-anchored
                                      verification, with a content digest that
                                      makes an unverified edit detectable
      -> pollution_degree_for()       IEC 60335-2-6 cl. 29.2 Addition: PD2 is a
                                      conditional exception requiring a sealed,
                                      gasketed compartment outside the
                                      forced-air path; PD3 otherwise
      -> table_17_lookup(pd, IIIa/IIIb, ">250-400")
                                      recovered IEC 60335-1 Table 17 row iv
      -> x2 (cl. 29.2.3)              reinforced = at least double basic
      -> MIN_BARRIER_WIDTH_MM

The rule, the schema and the tables live in
``packages/temper-design-bundle/src/enclosure.rs`` and
``packages/temper-design-bundle/src/safety_value.rs``; the loader is
``temper_placer.core.enclosure_declaration``. Read
``enclosure.rs``'s module docstring before changing any of it.

**PD3 remains the enforced production classification** and this change does
not move it: as declared today the chain evaluates to PD3 -> 6.3 mm basic ->
**12.6 mm** reinforced, byte-for-byte the value this module used to state as
a literal. There is no longer an alternative figure written anywhere for it
to be in tension with -- the 8.0 mm PD2 arm exists only as the *other branch
of the same function*, reachable only by changing the declared facts,
re-verifying them, and updating the declaration's digest.

Fail-closed
-----------
Import raises :class:`~temper_placer.core.enclosure_declaration.EnclosureDeclarationError`
if the declaration is missing, unparseable, schema-mismatched, placeholder-
filled, stale (its facts were edited after the verification that backs them),
or -- when it claims the PD2 exception -- anchored to a commit that does not
resolve. There is no default classification and no fallback value: the only
thing a silent fallback could produce is a safety number chosen by something
other than the declaration. **Never shrink this figure to make a gate pass**,
and never re-introduce a literal here to route around a broken declaration.

What this cannot do
-------------------
**No gate makes a physical enclosure real.** This module and everything
behind it operate on a *claim*. They can ensure the claim is explicit,
current, internally consistent, and traceable to a dated measurement, and
they can make this number move in lockstep with it. They cannot observe a
gasket. The sealing itself is a manufacturing and QA matter -- see
``elec/enclosure_manifest.yaml``'s header and the gate's own output.
"""

from __future__ import annotations

from temper_placer.core.enclosure_declaration import reinforced_barrier_width_mm

# REINFORCED creepage across the mains<->SELV barrier, at the pollution degree
# the declared enclosure earns, material group IIIa/IIIb (generic FR-4),
# working voltage <=400 V. Derived -- see this module's docstring for the full
# chain and `elec/enclosure_manifest.yaml` for the facts it is derived from.
#
# As declared today: PD3 -> Table 17 row iv basic 6.3mm -> x2 (cl. 29.2.3) ->
# 12.6mm. Do not replace this call with its current answer; the call IS the
# mechanism that keeps the number and the physical claim from drifting apart.
MIN_BARRIER_WIDTH_MM: float = reinforced_barrier_width_mm()

__all__ = ["MIN_BARRIER_WIDTH_MM"]
