from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.grouped_creepage_cuts import encode_grouped_creepage_cuts
from temper_placer.placer.cp_sat.model import CpSatModel


def _dense_plan(cuts, max_group_size, min_cross_edges):
    assert max_group_size == 2
    assert min_cross_edges == 3
    return ([['A1', 'A2'], ['B1', 'B2'], ['X'], ['Y']], [(0, 1)])


def _model(monkeypatch):
    monkeypatch.setattr(
        'temper_placer.placer.cp_sat.grouped_creepage_cuts.temper_orchestration.plan_grouped_creepage_cuts_py',
        _dense_plan,
        raising=False,
    )
    model = CpSatModel(units_per_mm=10)
    for reference in ('A1', 'A2', 'B1', 'B2', 'X', 'Y'):
        model.add_component(reference, x_start_val=0, y_start_val=0, width=10, height=10)
    return model


def test_dense_block_shares_directions_but_sparse_cut_does_not(monkeypatch):
    model = _model(monkeypatch)
    stats = encode_grouped_creepage_cuts(
        model,
        [('A1', 'B1', 8.0), ('A1', 'B2', 9.0), ('A2', 'B1', 10.0), ('A2', 'B2', 12.6), ('X', 'Y', 3.0)],
        max_group_size=2,
        min_cross_edges=3,
    )
    assert stats.grouped_cut_count == 4
    assert stats.independent_cut_count == 1
    assert stats.direction_bool_count == 8
    names = [variable.name for variable in model.model_ref.Proto().variables]
    assert sum(name.startswith('creepage_group_') for name in names) == 4
    assert sum(name.startswith('creepage_pair_') for name in names) == 4


def test_each_grouped_edge_keeps_its_exact_margin(monkeypatch):
    model = _model(monkeypatch)
    cuts = [('A1', 'B1', 8.0), ('A1', 'B2', 9.0), ('A2', 'B1', 10.0), ('A2', 'B2', 12.6), ('X', 'Y', 3.0)]
    encode_grouped_creepage_cuts(model, cuts, max_group_size=2, min_cross_edges=3)
    positions = {'A1': (0, 0), 'A2': (0, 20), 'B1': (111, 0), 'B2': (125, 20), 'X': (0, 40), 'Y': (40, 40)}
    for reference, (x, y) in positions.items():
        component = model.component_map[reference]
        model.model_ref.Add(component.x_start == x)
        model.model_ref.Add(component.y_start == y)
    # A2→B2 has only 11.5 mm of x gap, below its exact 12.6 mm cut.  A max,
    # average, or group-envelope approximation would incorrectly accept it.
    assert cp_model.CpSolver().Solve(model.model_ref) == cp_model.INFEASIBLE
