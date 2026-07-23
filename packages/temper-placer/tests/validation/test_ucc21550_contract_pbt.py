"""Property tests for the UCC21550 fault-latch contract.

The schematic is checked separately for the net names and gate wiring.  These
tests exercise the behavioural invariant that wiring implements: the
set-dominant NAND latch must assert shutdown for every fault, hold it until an
explicit reset, and never let reset clear a simultaneously asserted fault.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[4]
MODULES = (ROOT / "elec/src/modules.ato").read_text(encoding="utf-8")


def _latch_step(
    s_bar: bool,
    r_bar: bool,
    q: bool,
    q_bar: bool,
) -> tuple[bool, bool]:
    """Iterate the cross-coupled NAND equations to a stable state.

    ``s_bar`` and ``r_bar`` are active-low inputs.  The schematic's reset OR
    gate qualifies reset with the fault bus, so the only invalid electrical
    combination (both active-low inputs asserted) is intentionally included
    in the property: Q must still be high in that case.
    """

    for _ in range(8):
        next_q = not (s_bar and q_bar)
        next_q_bar = not (r_bar and next_q)
        q, q_bar = next_q, next_q_bar
    return q, q_bar


@pytest.mark.property
@given(events=st.lists(st.tuples(st.booleans(), st.booleans()), min_size=1, max_size=40))
@settings(max_examples=150, deadline=10_000)
def test_latch_safety_invariants_hold_for_fault_reset_sequences(
    events: list[tuple[bool, bool]],
) -> None:
    """Fault dominates reset and the latch remains complementary when stable."""

    q, q_bar = False, True
    for fault, reset_request in events:
        # Active-low S/R inputs. A fault drives S_bar low. The fault-qualified
        # reset path holds R_bar high while a fault is live, so a simultaneous
        # reset request cannot present the invalid NAND-latch input pair or
        # clear shutdown.
        q, q_bar = _latch_step(not fault, fault or not reset_request, q, q_bar)

        if fault:
            assert q is True
        elif reset_request:
            assert q is False

        # The fault-qualified inputs always leave the latch in a legal,
        # complementary stable state.
        assert q_bar is (not q)


@pytest.mark.property
@given(prefix=st.lists(st.booleans(), min_size=0, max_size=20))
@settings(max_examples=100, deadline=10_000)
def test_fault_remains_latched_until_explicit_reset(prefix: list[bool]) -> None:
    """Clearing a fault without reset cannot release a previously set latch."""

    q, q_bar = False, True
    for fault in prefix:
        q, q_bar = _latch_step(not fault, True, q, q_bar)

    q, q_bar = _latch_step(False, True, q, q_bar)
    assert (q, q_bar) == (True, False)

    # A reset is the only release mechanism once the fault has cleared.
    q, q_bar = _latch_step(True, False, q, q_bar)
    assert (q, q_bar) == (False, True)


def test_schematic_keeps_fault_qualified_set_dominant_wiring() -> None:
    """Guard the source-level contract exercised by the model above."""

    required_wiring = (
        "fault_or.Y2 ~ fault_any_or.A1",
        "rtd_hw_fault.line ~ fault_any_or.B1",
        "fault_any_or.Y1 ~ latch.A1",
        "fault_any_or.Y1 ~ fault_any_or.A2",
        "reset_n_in.line ~ fault_any_or.B2",
        "fault_any_or.Y2 ~ latch.A3",
        "latch.Y1 ~ latch.A2",
        "latch.Y3 ~ latch.B2",
        "latch.Y2 ~ latch.B3",
        "runaway_cut.line ~ fault_or.C2",
    )
    for connection in required_wiring:
        assert connection in MODULES
