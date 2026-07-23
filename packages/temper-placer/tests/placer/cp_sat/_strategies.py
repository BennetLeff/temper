"""Shared Hypothesis strategies for CP-SAT geometry constraint PBT tests."""

from __future__ import annotations

from hypothesis import strategies as st


@st.composite
def component_sizes(
    draw: st.DrawFn, min_mm: float = 1.0, max_mm: float = 20.0
) -> tuple[float, float]:
    """Generate a (width_mm, height_mm) component size."""
    w = draw(st.floats(min_value=min_mm, max_value=max_mm))
    h = draw(st.floats(min_value=min_mm, max_value=max_mm))
    return (w, h)


@st.composite
def board_dimensions(
    draw: st.DrawFn,
    min_mm: float = 20.0,
    max_mm: float = 200.0,
) -> tuple[float, float]:
    """Generate a (board_w_mm, board_h_mm) pair."""
    w = draw(st.floats(min_value=min_mm, max_value=max_mm))
    h = draw(st.floats(min_value=min_mm, max_value=max_mm))
    return (w, h)


@st.composite
def tau_and_margin(
    draw: st.DrawFn,
    tau_min: float = 0.0,
    tau_max: float = 2.0,
    margin_min: float = 0.0,
    margin_max: float = 2.0,
) -> tuple[float, float]:
    """Generate (tau_mm, margin_mm) for courtyard and edge constraints."""
    tau = draw(st.floats(min_value=tau_min, max_value=tau_max))
    margin = draw(st.floats(min_value=margin_min, max_value=margin_max))
    return (tau, margin)


@st.composite
def small_placement_instance(draw: st.DrawFn, n_comps: int | None = None):
    """Generate a (model, ctx) for a small placement instance.

    Returns a tuple of (CpSatModel, EncoderContext, component_refs, tau_mm, margin_mm).
    """
    from temper_placer.placer.cp_sat.encoder import EncoderContext
    from temper_placer.placer.cp_sat.model import CpSatModel

    units_per_mm = 100

    n = draw(st.integers(min_value=2, max_value=6)) if n_comps is None else n_comps

    tau_mm = draw(st.floats(min_value=0.0, max_value=2.0))
    margin_mm = draw(st.floats(min_value=0.0, max_value=2.0))

    board_w_mm = draw(st.floats(min_value=20.0, max_value=100.0))
    board_h_mm = draw(st.floats(min_value=20.0, max_value=100.0))

    model = CpSatModel(units_per_mm=units_per_mm)
    refs: list[str] = []
    for i in range(n):
        ref = f"C{i}"
        refs.append(ref)
        w_mm = draw(st.floats(min_value=1.0, max_value=10.0))
        h_mm = draw(st.floats(min_value=1.0, max_value=10.0))
        w_u = model.mm_to_units(w_mm)
        h_u = model.mm_to_units(h_mm)
        model.add_component(ref, 0, 0, w_u, h_u)
        model.add_rotation(ref, is_polarized=True)

    board_w_u = model.mm_to_units(board_w_mm)
    board_h_u = model.mm_to_units(board_h_mm)
    margin_u = model.mm_to_units(margin_mm)

    model.set_bounds(margin_u, margin_u, board_w_u - margin_u, board_h_u - margin_u)
    model.add_no_overlap_2d(refs)

    ctx = EncoderContext(
        board_w_mm=board_w_mm,
        board_h_mm=board_h_mm,
        board_x_max_units=board_w_u,
        board_y_max_units=board_h_u,
        courtyard_clearance_mm=tau_mm,
        board_edge_margin_units=margin_u,
    )

    return model, ctx, refs, tau_mm, margin_mm
