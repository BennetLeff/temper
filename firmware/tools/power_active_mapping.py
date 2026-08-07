#!/usr/bin/env python3
"""The power-active / faulted state abstraction shared by the model checks,
the invariants module, and the audit that keeps it honest against the C
source.

This is the single definition site for KTD6 / assumption A2 of
docs/plans/2026-08-02-028-feat-state-machine-model-check-plan.md:

    power_active = {STATE_PREHEAT, STATE_HEATING}   -- entry handlers call
                                                          power_enable()
    faulted      = {STATE_FAULT, STATE_RUNAWAY_FAULT}

See ``firmware/tools/POWER_ACTIVE_MAPPING.md`` for the full interface
contract and ``firmware/tools/test_power_active_mapping.py`` (U8) for the
audit that scans ``firmware/main/state_handlers.c`` and fails if a
power-enabling call appears outside a mapped state, or a power-disabling
call is missing from a fault state's entry handler.

Every consumer of this mapping (P1/P2 in transition_model_checks.py, the
I-OVERTEMP-DISABLES / I-SENSOR-FAULT-BLOCKS-HEATING / I-FAULT-EXITS /
I-NO-REENTRY invariants in invariants.yaml) imports these constants rather
than redeclaring them, so the mapping cannot silently drift between
consumers (KTD5's "one model, one engine" discipline applied to this
abstraction too).
"""

from __future__ import annotations

from typing import FrozenSet

POWER_ACTIVE_STATES: FrozenSet[str] = frozenset({"STATE_PREHEAT", "STATE_HEATING"})
FAULTED_STATES: FrozenSet[str] = frozenset({"STATE_FAULT", "STATE_RUNAWAY_FAULT"})
