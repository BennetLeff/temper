"""R1a: behavioural A/B of the U4 pipeline-state port against the pinned oracle.

Rust Orchestration Engine plan 2026-08-09-001, U4 (pipeline state): the
``temper_placer.pipeline.state`` classes migrate to the ``temper-orchestration``
crate as pyclasses (``PipelinePhase``, ``PipelineConfig``, ``PipelineState``);
``PipelineError`` stays a Python exception (exceptions have no bit-exact
pyclass mapping in scope, and the plan's U4 row names only ``PipelineConfig`` /
``PipelinePhase`` for the Rust side). The Python module keeps its full public
API (the four names) as a delegation shim.

The pre-migration module is pinned VERBATIM as the oracle
(``tests/pipeline/_pipeline_state_py_oracle.py``, content-hash-pinned below).
Both arms are driven with IDENTICAL inputs; every assertion is bit-exact
(``repr()`` string equality for whole objects and per-field signatures —
``repr`` is the exactest discriminator for Paths, Enum members, dicts with
Enum keys and floats alike; ``float.hex()``-based ``canon`` cannot represent
Path/Enum leaves and is therefore not the right tool here).

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the port is genuinely the Rust pyclasses (``__module__``), not the shim
resolving back onto itself.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import temper_orchestration as _to

from temper_placer.pipeline import state as _state
from tests.pipeline import _pipeline_state_py_oracle as _oracle


def _rs_cls(name: str):
    """Lazy access to a Rust class so the suite collects (and fails with a
    clear assertion) BEFORE the port exists — the G1 RED state."""
    cls = getattr(_to, name, None)
    assert cls is not None, (
        f"temper_orchestration.{name} is missing: the Rust port has not been "
        "built (G1 RED). Rebuild via maturin develop after pipeline_state.rs lands."
    )
    return cls


# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_pipeline_state_py_oracle.py")
_PINNED_BODY_SHA256 = "182239b213579774ccd43083ef9e3d5468468edf9beaea2511aa5bb0a1d19afd"
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_body_matches_pinned_digest() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied body is content-addressed. If this fails, either
    the oracle was edited (revert it) or a pre-migration module's source
    really changed upstream (re-pin deliberately, in its own commit).
    """
    text = _ORACLE_PATH.read_text(encoding="utf-8")
    assert _BODY_MARKER in text, "oracle header marker missing"
    body = text.split(_BODY_MARKER, 1)[1]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _PINNED_BODY_SHA256, (
        "the pinned oracle body changed; it must stay verbatim "
        f"(expected {_PINNED_BODY_SHA256}, got {digest})"
    )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: the port must be the Rust pyclasses, not the shim."""
    assert _state is not _oracle
    assert _state.PipelineConfig is not _oracle.PipelineConfig
    assert _state.PipelineState is not _oracle.PipelineState
    assert _state.PipelinePhase is not _oracle.PipelinePhase
    # The port is genuinely Rust: the pyclasses live in the extension module.
    assert _state.PipelineConfig.__module__ == "temper_orchestration"
    assert _state.PipelineState.__module__ == "temper_orchestration"
    assert _state.PipelinePhase.__module__ == "temper_orchestration"
    # PipelineError stays a Python exception on the shim.
    assert _state.PipelineError.__module__ == "temper_placer.pipeline.state"
    # The shim still carries the `_rs` delegation seam the differential
    # convention relies on.
    assert hasattr(_state, "_rs")
    assert _state._rs is _to


# ---------------------------------------------------------------------------
# PipelinePhase — the enum
# ---------------------------------------------------------------------------

_PHASE_MEMBERS = {
    "INPUT": "input",
    "SEMANTIC": "semantic",
    "TOPOLOGICAL": "topological",
    "PREFLIGHT": "preflight",
    "GEOMETRIC": "geometric",
    "ROUTING": "routing",
    "REFINEMENT": "refinement",
    "OUTPUT": "output",
    "ZONE_GEOMETRY": "zone_geometry",
    "ZONE_ASSIGNMENT": "zone_assignment",
    "SLOT_GENERATION": "slot_generation",
    "COMPONENT_ASSIGNMENT": "component_assignment",
    "APPLY_PLACEMENTS": "apply_placements",
    "COURTYARD_CHECK": "courtyard_check",
    "APPLY_PLACEMENTS_REAPPLY": "apply_placements_reapply",
    "PLACEMENT_VALIDATION": "placement_validation",
}


def test_phase_members_values_names_match() -> None:
    rs_phase = _rs_cls("PipelinePhase")
    for name, value in _PHASE_MEMBERS.items():
        rs_member = getattr(rs_phase, name)
        py_member = getattr(_oracle.PipelinePhase, name)
        assert rs_member.value == value == py_member.value
        assert rs_member.name == name == py_member.name
        assert repr(rs_member) == repr(py_member)
        assert str(rs_member) == str(py_member)


def test_phase_equality_and_hash_match() -> None:
    rs_phase = _rs_cls("PipelinePhase")
    # same member == itself; different members != each other; a non-member is
    # never equal (Enum.__eq__ returns NotImplemented -> False).
    assert (rs_phase.INPUT == rs_phase.INPUT) is True
    assert (_oracle.PipelinePhase.INPUT == _oracle.PipelinePhase.INPUT) is True
    assert (rs_phase.INPUT == rs_phase.OUTPUT) is False
    assert (_oracle.PipelinePhase.INPUT == _oracle.PipelinePhase.OUTPUT) is False
    assert (rs_phase.INPUT == "input") is False
    assert (_oracle.PipelinePhase.INPUT == "input") is False
    # Enums are hashable and usable as dict keys (phase_timings keys).
    rs_d = {rs_phase.ROUTING: 1.5, "raw": 2.0}
    py_d = {_oracle.PipelinePhase.ROUTING: 1.5, "raw": 2.0}
    assert rs_d[rs_phase.ROUTING] == 1.5
    assert py_d[_oracle.PipelinePhase.ROUTING] == 1.5
    assert repr(rs_d) == repr(py_d)
    assert hash(rs_phase.INPUT) == hash(rs_phase.INPUT)


# ---------------------------------------------------------------------------
# Shared signature helpers (repr-based — bit-exact for Paths, Enums, dicts)
# ---------------------------------------------------------------------------

_CONFIG_FIELDS = [
    "input_pcb",
    "constraints_yaml",
    "loops_yaml",
    "output_pcb",
    "output_report",
    "output_trace",
    "skip_topological",
    "skip_routing",
    "skip_local_refinement",
    "dry_run",
    "epochs",
    "seed",
    "max_movement_mm",
    "max_iterations",
    "routability_threshold",
    "convergence_threshold",
    "fab_preset",
]

_STATE_FIELDS = [
    "config",
    "current_phase",
    "iteration",
    "success",
    "failure_reason",
    "failed_phase",
    "elapsed_time_s",
    "phase_timings",
    "board",
    "netlist",
    "loops",
    "constraints",
    "deterministic_result",
    "placement_state",
    "routing_result",
    "physics_report",
    "preflight_report",
    "decision_trace",
    "_refinement_complete",
    "_best_routed_nets",
    "_best_routability",
    "_stall_count",
]


def _config_signature(cfg) -> tuple:
    return tuple(repr(getattr(cfg, f)) for f in _CONFIG_FIELDS)


def _state_signature(state) -> tuple:
    return tuple(repr(getattr(state, f)) for f in _STATE_FIELDS)


def _assert_signatures_equal(rs, py, label: str) -> None:
    rs_sig = _config_signature(rs) if hasattr(rs, "input_pcb") else _state_signature(rs)
    py_sig = _config_signature(py) if hasattr(py, "input_pcb") else _state_signature(py)
    assert rs_sig == py_sig, f"signature diverged for {label}\n  rs={rs_sig}\n  py={py_sig}"


def _random_config_kwargs(rng: random.Random) -> dict:
    def maybe_path():
        if rng.random() < 0.6:
            return Path(f"p{rng.randint(0, 9)}.kicad_pcb")
        return None

    return {
        "input_pcb": rng.choice(
            [Path(f"in_{rng.randint(0, 9)}.kicad_pcb"), f"in_{rng.randint(0, 9)}.kicad_pcb"]
        ),
        "constraints_yaml": maybe_path(),
        "loops_yaml": maybe_path(),
        "output_pcb": maybe_path(),
        "output_report": maybe_path(),
        "output_trace": maybe_path(),
        "skip_topological": rng.random() < 0.5,
        "skip_routing": rng.random() < 0.5,
        "skip_local_refinement": rng.random() < 0.5,
        "dry_run": rng.random() < 0.5,
        "epochs": rng.randint(0, 20000),
        "seed": rng.randint(-1000, 1000),
        "max_movement_mm": rng.uniform(0.0, 50.0),
        "max_iterations": rng.randint(0, 100),
        "routability_threshold": rng.uniform(0.0, 1.0),
        "convergence_threshold": rng.choice([0.0, rng.uniform(0.0, 1.0), 1e300, 1e-300]),
        "fab_preset": rng.choice(["jlcpcb_standard", "fab1", ""]),
    }


def _random_state_kwargs(rng: random.Random, config) -> dict:
    """Randomized PipelineState kwargs over a shared config object."""
    phases = [getattr(_to.PipelinePhase, n) for n in _PHASE_MEMBERS]
    oracle_phases = [getattr(_oracle.PipelinePhase, n) for n in _PHASE_MEMBERS]
    return {
        "config": config,
        "current_phase": rng.choice(phases),
        "iteration": rng.randint(0, 100),
        "success": rng.random() < 0.5,
        "failure_reason": rng.choice([None, "boom", "netlist empty"]),
        "failed_phase": rng.choice([None] + phases),
        "elapsed_time_s": rng.choice([0.0, rng.uniform(0.0, 1e4), 1e300]),
        "phase_timings": rng.choice([
            {},
            {rng.choice(phases): 0.5, "raw": 1.0},
            {"phase": 2.5},
        ]),
        "board": rng.choice([None, "board-obj", 42]),
        "netlist": None,
        "loops": rng.choice([[], ["loop1", "loop2"], []]),
        "constraints": rng.choice([None, {"groups": 3}]),
        "deterministic_result": None,
        "placement_state": None,
        "routing_result": rng.choice([None, {"nets": ["N1"]}]),
        "physics_report": None,
        "preflight_report": None,
        "decision_trace": None,
        "_refinement_complete": rng.random() < 0.5,
        "_best_routed_nets": rng.choice([None, ["N1", "N2"]]),
        "_best_routability": rng.choice([None, rng.uniform(0.0, 1.0)]),
        "_stall_count": rng.randint(0, 10),
    }


# ---------------------------------------------------------------------------
# PipelineConfig
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_KWARGS = {
    "input_pcb": Path("default.kicad_pcb"),
}


def test_config_defaults_match() -> None:
    rs = _state.PipelineConfig(_DEFAULT_CONFIG_KWARGS["input_pcb"])
    py = _oracle.PipelineConfig(_DEFAULT_CONFIG_KWARGS["input_pcb"])
    assert _config_signature(rs) == _config_signature(py)
    assert repr(rs) == repr(py)


def test_config_repr_matches_for_documented_defaults() -> None:
    rs = _state.PipelineConfig(Path("x.kicad_pcb"))
    py = _oracle.PipelineConfig(Path("x.kicad_pcb"))
    expected = (
        "PipelineConfig(input_pcb=PosixPath('x.kicad_pcb'), constraints_yaml=None, "
        "loops_yaml=None, output_pcb=None, output_report=None, output_trace=None, "
        "skip_topological=False, skip_routing=False, skip_local_refinement=False, "
        "dry_run=False, epochs=8000, seed=42, max_movement_mm=2.0, max_iterations=5, "
        "routability_threshold=0.85, convergence_threshold=0.01, "
        "fab_preset='jlcpcb_standard')"
    )
    assert repr(py) == expected
    assert repr(rs) == expected


def test_config_randomized_kwargs_match() -> None:
    rng = random.Random(20260810)
    for i in range(40):
        kwargs = _random_config_kwargs(rng)
        rs = _state.PipelineConfig(**kwargs)
        py = _oracle.PipelineConfig(**kwargs)
        assert _config_signature(rs) == _config_signature(py), f"kwargs={kwargs!r}"
        assert repr(rs) == repr(py), f"kwargs={kwargs!r}"


def test_config_eq_matches() -> None:
    a = _state.PipelineConfig(Path("a.kicad_pcb"), epochs=100)
    b = _state.PipelineConfig(Path("a.kicad_pcb"), epochs=100)
    c = _state.PipelineConfig(Path("a.kicad_pcb"), epochs=101)
    pa = _oracle.PipelineConfig(Path("a.kicad_pcb"), epochs=100)
    pb = _oracle.PipelineConfig(Path("a.kicad_pcb"), epochs=100)
    pc = _oracle.PipelineConfig(Path("a.kicad_pcb"), epochs=101)
    assert (a == b) == (pa == pb) is True
    assert (a == c) == (pa == pc) is False
    # non-instance comparisons
    assert (a == "nope") == (pa == "nope") is False
    assert (a != b) == (pa != pb) is False


def test_config_unhashable() -> None:
    rs = _state.PipelineConfig(Path("x.kicad_pcb"))
    py = _oracle.PipelineConfig(Path("x.kicad_pcb"))
    for obj in (rs, py):
        try:
            hash(obj)
        except TypeError:
            pass
        else:
            raise AssertionError(f"dataclass {type(obj).__name__} must be unhashable")


def test_config_field_mutation_matches() -> None:
    rs = _state.PipelineConfig(Path("x.kicad_pcb"))
    py = _oracle.PipelineConfig(Path("x.kicad_pcb"))
    rs.epochs = 12345
    py.epochs = 12345
    rs.skip_routing = True
    py.skip_routing = True
    rs.output_pcb = Path("out.kicad_pcb")
    py.output_pcb = Path("out.kicad_pcb")
    assert _config_signature(rs) == _config_signature(py)
    assert repr(rs) == repr(py)


# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------


def test_state_defaults_match() -> None:
    rs_cfg = _state.PipelineConfig(Path("d.kicad_pcb"))
    py_cfg = _oracle.PipelineConfig(Path("d.kicad_pcb"))
    rs = _state.PipelineState(rs_cfg)
    py = _oracle.PipelineState(py_cfg)
    assert _state_signature(rs) == _state_signature(py)
    assert repr(rs) == repr(py)


def test_state_repr_matches_for_documented_defaults() -> None:
    rs = _state.PipelineState(_state.PipelineConfig(Path("x.kicad_pcb")))
    py = _oracle.PipelineState(_oracle.PipelineConfig(Path("x.kicad_pcb")))
    expected_prefix = (
        "PipelineState(config=PipelineConfig(input_pcb=PosixPath('x.kicad_pcb'), "
        "constraints_yaml=None, loops_yaml=None, output_pcb=None, output_report=None, "
        "output_trace=None, skip_topological=False, skip_routing=False, "
        "skip_local_refinement=False, dry_run=False, epochs=8000, seed=42, "
        "max_movement_mm=2.0, max_iterations=5, routability_threshold=0.85, "
        "convergence_threshold=0.01, fab_preset='jlcpcb_standard'), "
        "current_phase=<PipelinePhase.INPUT: 'input'>, iteration=0, success=False, "
        "failure_reason=None, failed_phase=None, elapsed_time_s=0.0, phase_timings={}, "
        "board=None, netlist=None, loops=[], constraints=None, deterministic_result=None, "
        "placement_state=None, routing_result=None, physics_report=None, "
        "preflight_report=None, decision_trace=None, _refinement_complete=False, "
        "_best_routed_nets=None, _best_routability=None, _stall_count=0)"
    )
    assert repr(py) == expected_prefix
    assert repr(rs) == expected_prefix


def test_state_randomized_kwargs_match() -> None:
    rng = random.Random(20260810)
    for i in range(40):
        cfg_kwargs = _random_config_kwargs(rng)
        rs_cfg = _state.PipelineConfig(**cfg_kwargs)
        py_cfg = _oracle.PipelineConfig(**cfg_kwargs)
        state_kwargs = _random_state_kwargs(rng, rs_cfg)
        oracle_state_kwargs = dict(state_kwargs)
        oracle_state_kwargs["config"] = py_cfg
        rs = _state.PipelineState(**state_kwargs)
        py = _oracle.PipelineState(**oracle_state_kwargs)
        assert _state_signature(rs) == _state_signature(py), f"kwargs={state_kwargs!r}"
        assert repr(rs) == repr(py), f"kwargs={state_kwargs!r}"


def test_state_eq_matches() -> None:
    def build(module, rng_key):
        rng = random.Random(rng_key)
        cfg = module.PipelineConfig(Path("eq.kicad_pcb"), epochs=7)
        return module.PipelineState(cfg, iteration=3, success=True)

    a = build(_state, 1)
    b = build(_state, 1)
    c = build(_state, 2)
    pa = build(_oracle, 1)
    pb = build(_oracle, 1)
    pc = build(_oracle, 2)
    assert (a == b) == (pa == pb) is True
    assert (a == c) == (pa == pc)
    assert (a == c) is True and (pa == pc) is True
    assert (a == "nope") == (pa == "nope") is False
    # equality is deep: differing nested config breaks it
    c.config.epochs = 8
    pc.config.epochs = 8
    assert (a == c) == (pa == pc)  # both arms now disagree
    assert (a == c) is False and (pa == pc) is False


def test_state_unhashable() -> None:
    rs = _state.PipelineState(_state.PipelineConfig(Path("x.kicad_pcb")))
    py = _oracle.PipelineState(_oracle.PipelineConfig(Path("x.kicad_pcb")))
    for obj in (rs, py):
        try:
            hash(obj)
        except TypeError:
            pass
        else:
            raise AssertionError(f"dataclass {type(obj).__name__} must be unhashable")


def test_state_field_mutation_matches() -> None:
    rs = _state.PipelineState(_state.PipelineConfig(Path("x.kicad_pcb")))
    py = _oracle.PipelineState(_oracle.PipelineConfig(Path("x.kicad_pcb")))
    rs.current_phase = _to.PipelinePhase.ROUTING
    py.current_phase = _oracle.PipelinePhase.ROUTING
    rs._stall_count = 4
    py._stall_count = 4
    rs.phase_timings = {_to.PipelinePhase.INPUT: 1.0}
    py.phase_timings = {_oracle.PipelinePhase.INPUT: 1.0}
    rs.board = {"b": 1}
    py.board = {"b": 1}
    assert _state_signature(rs) == _state_signature(py)
    assert repr(rs) == repr(py)


def test_state_default_factories_are_independent() -> None:
    """Each instance gets a FRESH loops list and phase_timings dict (the
    dataclass default_factory semantics — mutating one instance must not
    leak into another)."""
    rs_a = _state.PipelineState(_state.PipelineConfig(Path("x.kicad_pcb")))
    rs_b = _state.PipelineState(_state.PipelineConfig(Path("x.kicad_pcb")))
    py_a = _oracle.PipelineState(_oracle.PipelineConfig(Path("x.kicad_pcb")))
    py_b = _oracle.PipelineState(_oracle.PipelineConfig(Path("x.kicad_pcb")))
    rs_a.loops.append("X")
    rs_a.phase_timings["X"] = 1.0
    py_a.loops.append("X")
    py_a.phase_timings["X"] = 1.0
    assert rs_b.loops == py_b.loops == []
    assert rs_b.phase_timings == py_b.phase_timings == {}


def test_pipeline_error_keeps_phase() -> None:
    err = _state.PipelineError("phase failed", phase=_to.PipelinePhase.PREFLIGHT)
    assert str(err) == "phase failed"
    assert err.phase is _to.PipelinePhase.PREFLIGHT
    assert isinstance(err, Exception)
