"""Property-based + metamorphic tests for the Rust config loader.

Wave 4, Phase 3, candidate 5 (plan ``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``,
R1c/R1d). These properties exercise the migrated ``temper_placer.io.config_loader``
module (delegation shim over ``temper_design_bundle_python``); parity against
the pinned oracle is asserted separately by
``test_config_loader_rust_differential.py``.

Properties:

- P1. Preprocess parity: for any generated raw config dict, the Rust and
  oracle ``_preprocess_config`` agree bit-identically (typed objects
  canonicalized; floats via ``float.hex()``).
- P2. Defaults: an empty/minimal raw dict yields the oracle's default board
  geometry and empty typed collections.
- P3. Loss-weight name mapping: the oracle's ``_NAME_MAP`` aliases
  (``zone_membership`` -> ``zone``) and ``_LOSS_NAMES`` gate are reproduced.
- P4. Net-priority coercion: every ``net_priority`` entry becomes
  ``str(key): int(value)`` identically on both arms.
- P5. Differential-pair ``or`` semantics: ``positive_net or net_pos`` falls
  back only when the primary is *falsy* (missing, None, or empty) — the
  truthiness-or trap. Same chain governs the spacing/impedance fallbacks
  (``separation_mm or spacing_mm or 0.2``, ``target_impedance_ohm or
  impedance_ohm``) — M7 full scope.
- P6. Fixed-positions float coercion: list and dict position forms both
  coerce to float tuples.

Metamorphic relations:

- MR1. Dict-insertion order: ``net_assignments`` / ``critical_paths`` /
  ``net_topology`` iteration order is observable in the output lists.
- MR2. Section independence: adding a section that is absent from the oracle's
  mapping (``unknown_section``) never changes the processed result.
- MR3. Loss-weights vs losses precedence: an explicit ``losses`` key wins over
  ``loss_weights`` when both are present.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.io._config_loader_py_oracle as _oracle
from tests.io.test_config_loader_rust_differential import canon_call

PRECONFIG = _tdb.preprocess_config

MAX_EXAMPLES = 60


@st.composite
def raw_config(draw):
    """A random but schema-shaped raw config dict (invalid combos may be
    produced — both arms must agree on accept AND reject)."""
    cfg: dict = {}
    if draw(st.booleans()):
        cfg["board"] = {
            "width_mm": draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False,
                                       allow_infinity=False)),
            "height_mm": draw(st.floats(min_value=1.0, max_value=500.0, allow_nan=False,
                                        allow_infinity=False)),
        }
    if draw(st.booleans()):
        cfg["zones"] = [
            {"name": "Z1", "bounds": [0.0, 0.0, 50.0, 50.0]},
        ]
    if draw(st.booleans()):
        cfg["net_assignments"] = {
            f"NCLASS_{i}": [f"NET_{j}" for j in range(draw(st.integers(0, 3)))]
            for i in range(draw(st.integers(0, 3)))
        }
    if draw(st.booleans()):
        cfg["net_class_rules"] = {
            f"CLS_{i}": {"trace_width_mm": draw(st.floats(min_value=0.1, max_value=5.0,
                                                          allow_nan=False, allow_infinity=False))}
            for i in range(draw(st.integers(0, 3)))
        }
    if draw(st.booleans()):
        cfg["loss_weights"] = {
            name: draw(st.floats(min_value=0.0, max_value=1000.0, allow_nan=False,
                                 allow_infinity=False))
            for name in ["overlap", "boundary", "zone_membership", "unknown_x"]
        }
    if draw(st.booleans()):
        cfg["net_priority"] = {f"NET_{i}": draw(st.integers(1, 10)) for i in range(3)}
    if draw(st.booleans()):
        cfg["critical_paths"] = {
            f"path_{i}": {"from": f"A{i}", "to": f"B{i}"} for i in range(2)
        }
    return cfg


@given(raw_config())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_preprocess_parity(cfg):
    assert canon_call(PRECONFIG, cfg) == canon_call(_oracle._preprocess_config, cfg)


@given(st.sampled_from([{}, {"board": {}}, {"zones": []}, {"net_classes": {}}]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_defaults_on_minimal_inputs(cfg):
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    assert rs["board_width_mm"] == py["board_width_mm"] == 100.0
    assert rs["board_height_mm"] == py["board_height_mm"] == 150.0
    assert rs["board_margin_mm"] == py["board_margin_mm"] == 3.0
    assert list(rs.keys()) == list(py.keys())


@given(st.dictionaries(st.sampled_from(
    ["zone_membership", "zone", "overlap", "boundary", "wirelength", "spread",
     "edge_avoidance", "group_cluster", "thermal", "clearance", "loop_area",
     "star_point", "not_a_loss"]),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_loss_weights_name_mapping(weights):
    cfg = {"loss_weights": weights}
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    assert dict(rs["losses"].model_dump()) == dict(py["losses"].model_dump())


@given(st.dictionaries(
    st.one_of(st.integers(min_value=0, max_value=10), st.floats(min_value=0.0, max_value=10.0,
                                                                allow_nan=False, allow_infinity=False),
              st.none(), st.tuples(st.text(min_size=1, max_size=3))),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3b_loss_weights_non_str_keys_skipped(weights):
    """Oracle: `_NAME_MAP.get(wkey, wkey)` tolerates any hashable key — a
    non-str key can never be a loss name, so it is skipped silently. A raw
    str extract in the Rust arm raised TypeError instead (the P2 parity
    bug); the Rust must skip non-str keys identically."""
    cfg = {"loss_weights": weights}
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    assert dict(rs["losses"].model_dump()) == dict(py["losses"].model_dump())


@given(st.dictionaries(st.text(alphabet="NET_0123", min_size=1, max_size=8),
                        st.integers(min_value=1, max_value=100)))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_net_priority_coercion(net_priority):
    cfg = {"net_priority": net_priority}
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    rs_np = {k: (type(v).__name__, v) for k, v in rs["net_priority"].items()}
    py_np = {k: (type(v).__name__, v) for k, v in py["net_priority"].items()}
    assert rs_np == py_np
    for v in rs["net_priority"].values():
        assert type(v).__name__ == "int"


@given(st.sampled_from([
    # Discriminating cases: a falsy PRIMARY with a live SECONDARY (and both
    # polarity nets present) — truthiness-or keeps the pair, key-existence
    # would drop it.
    {"positive_net": "", "negative_net": "DN", "net_pos": "FP", "net_neg": "FN"},
    {"positive_net": None, "negative_net": "DN", "net_pos": "FP", "net_neg": "FN"},
    {"positive_net": "DP", "negative_net": "", "net_pos": "FP", "net_neg": "FN"},
    # Same-outcome control cases (both semantics agree).
    {"positive_net": "DP", "negative_net": "DN", "net_pos": "FP", "net_neg": "FN"},
    {"net_pos": "FP", "net_neg": "FN"},
    {},
    # M7 full scope — the spacing/impedance fallback chains are truthiness-ors
    # too: a present-but-falsy primary (0) falls through to the secondary /
    # default. Key-existence fed 0 into pydantic's gt=0 spacing field (raise)
    # or 0.0 into impedance where the oracle yields None.
    {"positive_net": "DP", "negative_net": "DN", "separation_mm": 0},
    {"positive_net": "DP", "negative_net": "DN", "spacing_mm": 0},
    {"positive_net": "DP", "negative_net": "DN", "target_impedance_ohm": 0},
    {"positive_net": "DP", "negative_net": "DN", "impedance_ohm": 0},
    # falsy primary alongside a live fallback key
    {"positive_net": "DP", "negative_net": "DN", "separation_mm": 0, "spacing_mm": 0.7},
    {"positive_net": "DP", "negative_net": "DN", "spacing_mm": 0, "separation_mm": 0.9},
    {"positive_net": "DP", "negative_net": "DN", "target_impedance_ohm": 0, "impedance_ohm": 50.0},
]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_differential_pair_or_semantics(entry):
    """`dc.get("positive_net") or dc.get("net_pos")` — the truthiness-or:
    an empty-string/None primary falls back to the secondary; a present
    primary wins. (The cases with a falsy primary AND both polarity nets
    present are the discriminator — earlier drafts lacked a negative net, so
    both arms skipped identically and the property was vacuous.) The same
    truthiness-or governs the spacing/impedance fallbacks (M7 full scope):
    `separation_mm or spacing_mm or 0.2` and `target_impedance_ohm or
    impedance_ohm`."""
    cfg = {"differential_pairs": [entry]}
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    rs_pos = [(p.net_pos, p.net_neg) for p in rs["differential_pairs"]]
    py_pos = [(p.net_pos, p.net_neg) for p in py["differential_pairs"]]
    assert rs_pos == py_pos
    rs_sp = [(p.spacing_mm, p.impedance_ohm) for p in rs["differential_pairs"]]
    py_sp = [(p.spacing_mm, p.impedance_ohm) for p in py["differential_pairs"]]
    assert rs_sp == py_sp
    # non-vacuity anchors: at least one of the discriminating cases yields a pair
    if entry.get("positive_net") in ("", None) and entry.get("negative_net"):
        assert rs_pos, "falsy primary with live secondary must yield a pair"
    # M7 anchors: falsy spacing/impedance primary with a live fallback must
    # pick the fallback; falsy-only must land on 0.2 / None.
    if entry.get("separation_mm") == 0 and entry.get("spacing_mm") == 0.7:
        assert rs["differential_pairs"][0].spacing_mm == 0.7
    if entry.get("spacing_mm") == 0 and entry.get("separation_mm") == 0.9:
        assert rs["differential_pairs"][0].spacing_mm == 0.9
    if entry.get("target_impedance_ohm") == 0 and entry.get("impedance_ohm") == 50.0:
        assert rs["differential_pairs"][0].impedance_ohm == 50.0
    if entry.get("separation_mm") == 0 and "spacing_mm" not in entry:
        assert rs["differential_pairs"][0].spacing_mm == 0.2
        assert rs["differential_pairs"][0].impedance_ohm is None


@given(st.tuples(
    st.lists(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False,
                       allow_infinity=False), min_size=2, max_size=2),
    st.lists(st.floats(min_value=-100.0, max_value=100.0, allow_nan=False,
                       allow_infinity=False), min_size=2, max_size=2),
))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_fixed_positions_float_coercion(pos_pair):
    list_pos, dict_pos = pos_pair
    cfg = {
        "fixed_components": {"R1": {"x": list_pos[0], "y": list_pos[1]}},
        "fixed_positions": {"R2": list_pos, "R3": {"x": dict_pos[0], "y": dict_pos[1]}},
    }
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    rs_fp = {k: (tuple(type(v).__name__ for v in val), val) for k, val in rs["fixed_positions"].items()}
    py_fp = {k: (tuple(type(v).__name__ for v in val), val) for k, val in py["fixed_positions"].items()}
    assert rs_fp == py_fp


@given(st.lists(st.text(alphabet="abcXYZ", min_size=1, max_size=3), min_size=0, max_size=6, unique=True))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_dict_insertion_order_observable(net_names):
    cfg = {"net_assignments": {f"Cls{i}": [n] for i, n in enumerate(net_names)}}
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    rs_keys = list(rs["net_classes"].keys())
    py_keys = list(py["net_classes"].keys())
    assert rs_keys == py_keys == net_names


@given(raw_config())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_unknown_section_ignored(cfg):
    base = dict(cfg)
    augmented = dict(cfg)
    augmented["unknown_section"] = {"anything": 1}
    rs_base = PRECONFIG(base)
    rs_aug = PRECONFIG(augmented)
    assert list(rs_base.keys()) == list(rs_aug.keys())
    assert {k: repr(v) for k, v in rs_base.items()} == {
        k: repr(v) for k, v in rs_aug.items()
    }


def test_mr3_losses_wins_over_loss_weights():
    cfg = {
        "losses": {"overlap": {"weight": 5.0}},
        "loss_weights": {"overlap": 1.0},
    }
    rs = PRECONFIG(cfg)
    py = _oracle._preprocess_config(cfg)
    assert rs["losses"].overlap.weight == py["losses"].overlap.weight == 5.0


# ---------------------------------------------------------------------------
# R20 suite hardening — discriminator moved from the differential. #850's
# differential-disabled re-run found M10 (the LossConfig.enabled default
# flip) survives the suites-only run; its discriminating assertion (a
# dict-form `losses` entry without an explicit `enabled` gets the True
# default) lived only in `test_config_loader_rust_differential.py`. The
# default is a deterministic invariant of preprocess_config, so it is pinned
# here. The differential keeps its own assertion.
# ---------------------------------------------------------------------------


def test_p7_losses_dict_form_default_enabled():
    """A dict-form `losses` entry WITHOUT an explicit `enabled` gets the
    LossConfig default True (the ``data.get("enabled", True)`` default — the
    `loss_weights` path cannot see it because it goes through the float
    branch). A port that flipped the default to False fails the pin
    (surviving mutant M10)."""
    rs = PRECONFIG({"losses": {"overlap": {"weight": 2.0}}})
    assert rs["losses"].overlap.enabled is True
    assert rs["losses"].overlap.weight == 2.0
    # Non-vacuity: an explicit `enabled: false` is honored (the default is
    # not constant).
    off = PRECONFIG({"losses": {"overlap": {"weight": 2.0, "enabled": False}}})
    assert off["losses"].overlap.enabled is False
