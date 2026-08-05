"""Differential test: DRC ratchet comparison kernels in Rust
(``temper_drc_rs.ratchet_check`` / ``temper_drc_rs.detect_ceiling_raise``)
vs the pinned Python oracle (Wave 4, Phase 4 — regression slice).

``temper_placer/regression/drc_ratchet.py`` moves its ceiling-comparison
compute (aggregate deltas, per-type category failure detection with the
implicit-zero ceiling, the pass/fail message composition, and
``detect_ceiling_raise``'s raise detection) into ``temper_drc_rs``. The
pre-migration module is pinned verbatim as the oracle
(``_drc_ratchet_py_oracle.py``, commit ``0a29f15e3``) and the differential
drives IDENTICAL ceiling entries + synthetic measured counts through both
``_check_board`` implementations (the DRC backends — kicad-cli subprocess,
Rust-engine board_dict building — are stubbed on both sides), comparing the
full ``DrcRatchetResult`` including message strings bit-exactly.

Design boundaries, argued in the migrated module and
``packages/temper-drc-rs/VERIFICATION.md``:

- The DRC backend execution (kicad-cli, ``temper_drc_rs.run_drc`` board_dict
  building) stays Python-side — I/O, nothing to migrate.
- The ratchet constants (``drc_ceiling.json`` values, the ``#575`` gate) stay
  where they are — this migration only ports the COMPARISON logic, which must
  not change what the ratchet reads.
- All message content is int/str/bool interpolation (no-format float
  ``str()`` is never interpolated here), so the kernel composes the messages
  bit-identically.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import pytest
import temper_drc_rs as _tdrc

import tests.regression._drc_ratchet_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
RATCHET_CHECK = _tdrc.ratchet_check
DETECT_CEILING_RAISE = _tdrc.detect_ceiling_raise

from temper_placer.regression.drc_ratchet import DrcRatchet as ShimRatchet  # noqa: E402


# ---------------------------------------------------------------------------
# Canonicalization — bit-exact comparison keys
# ---------------------------------------------------------------------------


def _canon_category(c):
    return (
        c.rule,
        c.count,
        c.allowed,
        c.is_new,
        c.kind,
        c.source,
        c.delta,
    )


def _canon_result(r):
    return (
        r.passed,
        r.board_id,
        r.message,
        r.exit_code,
        tuple((k, v) for k, v in r.violation_deltas.items()),
        tuple(_canon_category(c) for c in r.category_failures),
        r.aggregate_error_delta,
        r.aggregate_warning_delta,
        r.kicad_cli_version_running,
        r.kicad_cli_version_expected,
        r.kicad_cli_version_mismatch,
    )


# ---------------------------------------------------------------------------
# Input construction — identical ceiling entries + stub backends for both arms
# ---------------------------------------------------------------------------


@dataclass
class _StubRustBackend:
    """Stubs the ``rust`` backend: ``_run_rust_drc -> (errors, warnings)``."""

    errors: int
    warnings: int

    def _run_rust_drc(self, pcb_path: Path):
        return self.errors, self.warnings


@dataclass
class _MockRule:
    rule: str


@dataclass
class _MockResult:
    error_count: int
    warning_count: int
    errors: list
    warnings: list


@dataclass
class _StubKicadCliBackend:
    """Stubs the ``kicad-cli`` backend (run_drc + get_kicad_cli_version)."""

    errors: list[str]
    warnings: list[str]
    version: str | None = None

    def _run_drc(self, pcb_path):
        return _MockResult(
            error_count=len(self.errors),
            warning_count=len(self.warnings),
            errors=[_MockRule(r) for r in self.errors],
            warnings=[_MockRule(r) for r in self.warnings],
        )


def _build_ceiling_json(tmp_path, boards: list[dict]) -> Path:
    ceiling_path = tmp_path / "drc_ceiling.json"
    ceiling_path.write_text(json.dumps({"boards": boards}))
    return ceiling_path


def _make_pair(
    tmp_path: Path,
    backend: str,
    entry: dict,
    current: tuple[list[str], list[str]] | tuple[int, int],
    version: str | None = None,
):
    """Build oracle + shim DrcRatchet instances ready for ``_check_board``.

    ``entry`` is the ceiling board dict (with provenance block for
    tool_versions); ``current`` is the stub backend's synthetic measurement.
    Returns (oracle_ratchet, shim_ratchet, pcb_path).
    """
    ceiling_path = _build_ceiling_json(tmp_path, [entry])
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")

    oracle = _oracle.DrcRatchet(ceiling_path, backend=backend)
    shim = ShimRatchet(ceiling_path, backend=backend)
    oracle.load()
    shim.load()
    board_id = entry["board_id"]
    o_entry = oracle.entries[board_id]
    s_entry = shim.entries[board_id]

    if backend == "rust":
        errors, warnings = current
        oracle._run_rust_drc = _StubRustBackend(errors, warnings)._run_rust_drc  # type: ignore[method-assign]
        shim._run_rust_drc = _StubRustBackend(errors, warnings)._run_rust_drc  # type: ignore[method-assign]
    else:
        errors, warnings = current
        import temper_placer.validation._drc_api as drc_api

        stub = _StubKicadCliBackend(errors, warnings, version)
        monkeypatched = {}
        for ratchet in (oracle, shim):
            # Patch at the module level so both arms see the same backend.
            ratchet._stub = stub  # type: ignore[attr-defined]
        monkeypatched["drc_api"] = drc_api
        return oracle, shim, pcb, stub, drc_api

    return oracle, shim, pcb


def _random_entry(rng):
    return {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": rng.randint(0, 30),
        "warning_ceiling": rng.randint(0, 30),
        "violations_by_type": {
            f"rule{i}": rng.randint(0, 5) for i in range(rng.randint(0, 4))
        },
        "warnings_by_type": {
            f"wrule{i}": rng.randint(0, 5) for i in range(rng.randint(0, 4))
        },
        "provenance": {"tool_versions": {"kicad-cli": "v1"}},
    }


# ---------------------------------------------------------------------------
# Differential — full DrcRatchetResult bit-exactness, both backends
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend", ["rust", "kicad-cli"])
def test_differential_pass_with_slack(tmp_path, backend):
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 5,
        "violations_by_type": {"clearance": 5},  # 4 measured -> within ceiling
        "warnings_by_type": {},
        "provenance": {"tool_versions": {"kicad-cli": "v1"}},
    }
    if backend == "rust":
        o, s, pcb = _make_pair(tmp_path, backend, entry, (4, 2), version="v1")
        stub = None
    else:
        o, s, pcb, stub, drc_api = _make_pair(
            tmp_path, backend, entry, (["clearance"] * 4, []), version="v1"
        )
        drc_api.run_drc = stub._run_drc
        drc_api.get_kicad_cli_version = lambda: stub.version
    board_id = "b"
    o_res = o._check_board(board_id, pcb, o.entries[board_id])
    s_res = s._check_board(board_id, pcb, s.entries[board_id])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert s_res.passed
    assert "within ceiling" in s_res.message
    assert "6 error(s) of unratcheted slack" in s_res.message


def test_differential_pass_zero_slack(tmp_path):
    backend = "kicad-cli"
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 3,
        "warning_ceiling": 0,
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, backend, entry, (["r1"] * 3, []), version=None
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert s_res.passed
    assert "unratcheted slack" not in s_res.message


def test_differential_aggregate_error_exceeded(tmp_path):
    backend = "kicad-cli"
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 3,
        "warning_ceiling": 10,
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, backend, entry, (["r1"] * 7, []), version=None
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert not s_res.passed
    assert s_res.exit_code == 1
    assert "errors 7 exceeds ceiling 3 (+4)" in s_res.message
    assert s_res.aggregate_error_delta == 4


def test_differential_aggregate_warning_exceeded(tmp_path):
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 2,
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, ([], ["w1"] * 5), version=None
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert "warnings 5 exceeds ceiling 2 (+3)" in s_res.message


def test_differential_new_and_regressed_categories(tmp_path):
    """Both a brand-new category (implicit ceiling 0) and a regressed one,
    rendered NEW-first then regressed in the message, mirroring the oracle's
    ``new_failures + regressed_failures`` ordering."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 100,
        "warning_ceiling": 100,
        "violations_by_type": {"clearance": 10, "creepage": 2},
        "warnings_by_type": {},
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path,
        "kicad-cli",
        entry,
        (["clearance"] * 12 + ["creepage"] * 4 + ["hole_to_hole"] * 1, []),
        version=None,
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    # 3 categories over: clearance +2 (regressed), creepage +2 (regressed),
    # hole_to_hole +1 (NEW). Message: NEW first, then regressed.
    assert "hole_to_hole 1 > 0 (+1)" in s_res.message
    assert "clearance 12 > 10 (+2)" in s_res.message
    assert "creepage 4 > 2 (+2)" in s_res.message
    # NEW line precedes the regressed lines (new_failures + regressed_failures).
    new_pos = s_res.message.find("[NEW]")
    clr_pos = s_res.message.find("clearance 12")
    assert new_pos < clr_pos


def test_differential_aggregate_and_categories_both_reported(tmp_path):
    """The aggregate check must not mask the per-type breakdown."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 100,
        "violations_by_type": {"clearance": 10},
        "warnings_by_type": {},
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, (["clearance"] * 11, []), version=None
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert "aggregate errors 11 exceeds ceiling 10 (+1)" in s_res.message
    assert "clearance 11 > 10 (+1)" in s_res.message
    assert s_res.aggregate_error_delta == 1
    assert s_res.violation_deltas == {"clearance": 1}


def test_differential_empty_allowed_record_suppresses_categories(tmp_path):
    """When ``violations_by_type`` is an empty record, the oracle's
    ``if entry.violations_by_type and ...`` guard suppresses per-type
    failures entirely even with measured categories present."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 100,
        "violations_by_type": {},
        "warnings_by_type": {},
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, (["clearance"] * 11, []), version=None
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert s_res.passed is False
    assert "clearance 11" not in s_res.message  # aggregate only


def test_differential_rust_backend_no_per_type_breakdown(tmp_path):
    """The rust backend supplies no per-type breakdown (``current_by_type``
    is None), so even a non-empty allowed record never fires categories."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 100,
        "violations_by_type": {"clearance": 10},
        "warnings_by_type": {},
        "provenance": {"tool_versions": {}},
    }
    o, s, pcb = _make_pair(tmp_path, "rust", entry, (5, 0), version=None)
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert s_res.passed
    assert "per-type" not in s_res.message


def test_differential_version_mismatch_note_on_pass(tmp_path):
    """kicad-cli version mismatch is reported on the pass path, with the
    note stripped of its leading whitespace (the oracle's
    ``version_note.strip()`` on pass vs. verbatim on fail)."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 5,
        "provenance": {"tool_versions": {"kicad-cli": "v2"}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, (["r1"] * 2, []), version="v1"
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: stub.version
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert s_res.kicad_cli_version_mismatch
    assert "NOTE: kicad-cli version mismatch -- running v1, ceiling measured with v2" in s_res.message


def test_differential_version_mismatch_note_on_fail(tmp_path):
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 3,
        "warning_ceiling": 5,
        "provenance": {"tool_versions": {"kicad-cli": "v2"}},
    }
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, (["r1"] * 9, []), version="v1"
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: stub.version
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    # On the fail path the note keeps its two-space indent.
    assert "  NOTE: kicad-cli version mismatch" in s_res.message


def test_differential_pcb_missing(tmp_path):
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 5,
        "provenance": {"tool_versions": {}},
    }
    ceiling_path = _build_ceiling_json(tmp_path, [entry])
    o = _oracle.DrcRatchet(ceiling_path, backend="kicad-cli")
    s = ShimRatchet(ceiling_path, backend="kicad-cli")
    o.load()
    s.load()
    missing = tmp_path / "nope.kicad_pcb"
    o_res = o._check_board("b", missing, o.entries["b"])
    s_res = s._check_board("b", missing, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert s_res.exit_code == 1


def test_differential_unknown_backend(tmp_path):
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 5,
        "provenance": {"tool_versions": {}},
    }
    ceiling_path = _build_ceiling_json(tmp_path, [entry])
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    o = _oracle.DrcRatchet(ceiling_path, backend="bogus")
    s = ShimRatchet(ceiling_path, backend="bogus")
    o.load()
    s.load()
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert "Unknown DRC backend: bogus" in s_res.message


@pytest.mark.parametrize("backend", ["rust", "kicad-cli"])
def test_differential_drc_backend_exception(tmp_path, backend, monkeypatch):
    """A backend exception must produce the same failure result in both arms."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 5,
        "provenance": {"tool_versions": {}},
    }
    ceiling_path = _build_ceiling_json(tmp_path, [entry])
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text("(kicad_pcb)")

    def boom(pcb_path):
        raise RuntimeError("kaboom")

    o = _oracle.DrcRatchet(ceiling_path, backend=backend)
    s = ShimRatchet(ceiling_path, backend=backend)
    o.load()
    s.load()
    if backend == "rust":
        o._run_rust_drc = boom  # type: ignore[method-assign]
        s._run_rust_drc = boom  # type: ignore[method-assign]
    else:
        import temper_placer.validation._drc_api as drc_api

        monkeypatch.setattr(drc_api, "run_drc", boom)
        monkeypatch.setattr(drc_api, "get_kicad_cli_version", lambda: None)
    o_res = o._check_board("b", pcb, o.entries["b"])
    s_res = s._check_board("b", pcb, s.entries["b"])
    assert _canon_result(s_res) == _canon_result(o_res)
    assert f"DRC ({backend}) failed: kaboom" in s_res.message


def test_differential_random_stress(tmp_path):
    """Randomized end-to-end differential across both backends."""
    rng = random.Random(0xABC123)
    for _ in range(120):
        backend = rng.choice(["rust", "kicad-cli"])
        entry = _random_entry(rng)
        n_err = rng.randint(0, 45)
        n_warn = rng.randint(0, 45)
        err_rules = [f"e{i}" for i in range(n_err)]
        warn_rules = [f"w{i}" for i in range(n_warn)]
        version = "v1" if rng.random() < 0.5 else None
        if backend == "rust":
            o, s, pcb = _make_pair(tmp_path, "rust", entry, (n_err, n_warn))
            stub, drc_api = None, None
        else:
            o, s, pcb, stub, drc_api = _make_pair(
                tmp_path, "kicad-cli", entry, (err_rules, warn_rules), version=version
            )
            drc_api.run_drc = stub._run_drc
            drc_api.get_kicad_cli_version = lambda: stub.version
        board_id = entry["board_id"]
        o_res = o._check_board(board_id, pcb, o.entries[board_id])
        s_res = s._check_board(board_id, pcb, s.entries[board_id])
        assert _canon_result(s_res) == _canon_result(o_res), (
            f"backend={backend} entry={entry} n_err={n_err} n_warn={n_warn}"
        )


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def _run_pair(o_ratchet, s_ratchet, pcb, board_id):
    o_res = o_ratchet._check_board(board_id, pcb, o_ratchet.entries[board_id])
    s_res = s_ratchet._check_board(board_id, pcb, s_ratchet.entries[board_id])
    assert _canon_result(s_res) == _canon_result(o_res)
    return s_res


def test_mr1_pass_failure_monotone_in_current_errors(tmp_path):
    """Increasing ``current_errors`` (with ceilings fixed) can only keep the
    result failing or turn a pass into a fail — never the reverse. The kernel
    must not implement an inverted aggregate comparison."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 100,
        "provenance": {"tool_versions": {}},
    }
    passes = []
    for n in range(0, 16):
        o, s, pcb = _make_pair(tmp_path, "rust", entry, (n, 0))
        res = _run_pair(o, s, pcb, "b")
        passes.append(res.passed)
    # once failing, always failing
    failed = False
    for p in passes:
        if failed:
            assert p is False
        failed = failed or (p is False)


def test_mr2_aggregate_shift_invariance(tmp_path):
    """Adding the same constant k to both ``current_errors`` and
    ``error_ceiling`` leaves ``passed``, the aggregate deltas and the
    per-category outcomes unchanged (the *message* changes, carrying the new
    numbers — only the decision and structured deltas are invariant)."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 10,
        "warning_ceiling": 100,
        "violations_by_type": {"clearance": 3},
        "provenance": {"tool_versions": {}},
    }
    base = None
    for k in (0, 5, 20):
        e = dict(entry)
        e["error_ceiling"] = 10 + k
        o, s, pcb = _make_pair(tmp_path, "rust", e, (6 + k, 0))
        res = _run_pair(o, s, pcb, "b")
        canon = (res.passed, res.exit_code, res.aggregate_error_delta, res.violation_deltas)
        if base is None:
            base = canon
        else:
            assert canon == base


def test_mr3_category_rule_order_invariance(tmp_path):
    """Per-type failure detection is independent of the rule order in the
    current measurement dict (the oracle sorts before comparing; the kernel
    must too — a kernel that compared in first-seen order would flip the
    NEW/regressed message ordering for a different rule order)."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 100,
        "warning_ceiling": 100,
        "violations_by_type": {"a": 1, "b": 1},
        "provenance": {"tool_versions": {}},
    }
    orders = [
        ["a", "b", "c"],
        ["c", "b", "a"],
        ["b", "c", "a"],
    ]
    messages = []
    for order in orders:
        o, s, pcb, stub, drc_api = _make_pair(
            tmp_path, "kicad-cli", entry, ([r for r in order for _ in range(3)], [])
        )
        drc_api.run_drc = stub._run_drc
        drc_api.get_kicad_cli_version = lambda: None
        res = _run_pair(o, s, pcb, "b")
        messages.append(res.message)
    assert messages[0] == messages[1] == messages[2]


def test_mr4_implicit_zero_ceiling_boundary(tmp_path):
    """A rule absent from the allowed record with count 0 is not a failure;
    with count 1 it is a NEW failure (implicit ceiling 0). The boundary is at
    ``count > allowed``, not ``count >= allowed``."""
    entry = {
        "board_id": "b",
        "path": "pcb/board.kicad_pcb",
        "error_ceiling": 100,
        "warning_ceiling": 100,
        "violations_by_type": {"known": 1},
        "provenance": {"tool_versions": {}},
    }
    # absent rule at count 0: pass (nothing over any ceiling)
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, (["known"], [])
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    res_pass = _run_pair(o, s, pcb, "b")
    assert res_pass.passed

    # absent rule at count 1: NEW failure
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", entry, (["known"] + ["absent_rule"], [])
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    res_fail = _run_pair(o, s, pcb, "b")
    assert not res_fail.passed
    assert any(c.is_new and c.rule == "absent_rule" for c in res_fail.category_failures)


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------

_ENTRY = {
    "board_id": "b",
    "path": "pcb/board.kicad_pcb",
    "error_ceiling": 10,
    "warning_ceiling": 5,
    "violations_by_type": {"clearance": 3, "creepage": 2},
    "warnings_by_type": {"zone": 1},
    "provenance": {"tool_versions": {"kicad-cli": "v1"}},
}


def test_prop1_pass_implies_no_positive_deltas(tmp_path):
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", _ENTRY, (["clearance"] * 2, ["zone"]), version="v1"
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: stub.version
    res = _run_pair(o, s, pcb, "b")
    assert res.passed
    assert res.aggregate_error_delta == 0
    assert res.aggregate_warning_delta == 0
    assert res.category_failures == []
    assert res.exit_code == 0


def test_prop2_category_failure_invariants(tmp_path):
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path,
        "kicad-cli",
        _ENTRY,
        (["clearance"] * 5 + ["creepage"] * 3 + ["hole_to_hole"], []),
        version=None,
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: None
    res = _run_pair(o, s, pcb, "b")
    assert not res.passed
    for c in res.category_failures:
        assert c.count > c.allowed
        assert c.delta == c.count - c.allowed
        assert c.is_new == (c.rule not in {"clearance", "creepage"})
        assert c.source == "kicad-cli"


def test_prop3_aggregate_delta_is_magnitude_of_excess(tmp_path):
    o, s, pcb = _make_pair(tmp_path, "rust", _ENTRY, (14, 2))
    res = _run_pair(o, s, pcb, "b")
    assert res.aggregate_error_delta == 4
    assert res.aggregate_warning_delta == 0
    assert not res.passed
    assert "errors 14 exceeds ceiling 10 (+4)" in res.message


def test_prop4_passed_agrees_with_exit_code(tmp_path):
    for current in [(3, 1), (10, 5), (0, 0), (12, 5), (10, 6)]:
        o, s, pcb = _make_pair(tmp_path, "rust", _ENTRY, current)
        res = _run_pair(o, s, pcb, "b")
        assert res.passed == (res.exit_code == 0)
        assert res.board_id == "b"
        assert res.message.startswith("b: DRC")


def test_prop5_version_mismatch_flags_agree(tmp_path):
    o, s, pcb, stub, drc_api = _make_pair(
        tmp_path, "kicad-cli", _ENTRY, (["clearance"], []), version="v9"
    )
    drc_api.run_drc = stub._run_drc
    drc_api.get_kicad_cli_version = lambda: stub.version
    res = _run_pair(o, s, pcb, "b")
    assert res.kicad_cli_version_mismatch
    assert res.kicad_cli_version_running == "v9"
    assert res.kicad_cli_version_expected == "v1"


def test_prop6_detect_raise_requires_approval_trailer():
    """The raise detector fires only without ``Ceiling-Approval:`` and only
    for a genuine increase (aggregate or per-type, including an implicit-zero
    per-type raise)."""
    ratchets = (_oracle.DrcRatchet(Path("x.json")), ShimRatchet(Path("x.json")))

    old = {
        "boards": [
            {
                "board_id": "b1",
                "error_ceiling": 100,
                "warning_ceiling": 0,
                "violations_by_type": {"clearance": 5},
            }
        ]
    }
    # per-type raise via a brand-new rule (implicit 0 -> 1)
    new = {
        "boards": [
            {
                "board_id": "b1",
                "error_ceiling": 100,
                "warning_ceiling": 0,
                "violations_by_type": {"clearance": 5, "creepage": 1},
            }
        ]
    }
    for ratchet in ratchets:
        res = ratchet.detect_ceiling_raise(old, new, commit_message="fix: nope")
        assert res is not None
        assert res.exit_code == 2
        assert "violations_by_type[creepage] 0 -> 1" in res.message
        res2 = ratchet.detect_ceiling_raise(
            old, new, commit_message="Ceiling-Approval: reviewer\nfix: nope"
        )
        assert res2 is None


def test_prop7_detect_raise_reason_order_is_stable():
    """The reason list order is deterministic: aggregates first, then
    violations_by_type (sorted), then warnings_by_type (sorted)."""
    ratchets = (_oracle.DrcRatchet(Path("x.json")), ShimRatchet(Path("x.json")))
    old = {
        "boards": [
            {
                "board_id": "b1",
                "error_ceiling": 1,
                "warning_ceiling": 1,
                "violations_by_type": {"z": 1, "a": 1},
                "warnings_by_type": {"wz": 1, "wa": 1},
            }
        ]
    }
    new = {
        "boards": [
            {
                "board_id": "b1",
                "error_ceiling": 2,
                "warning_ceiling": 2,
                "violations_by_type": {"z": 2, "a": 2},
                "warnings_by_type": {"wz": 2, "wa": 2},
            }
        ]
    }
    messages = []
    for ratchet in ratchets:
        res = ratchet.detect_ceiling_raise(old, new, commit_message="fix: nope")
        assert res is not None
        messages.append(res.message)
    assert messages[0] == messages[1]
    msg = messages[0]
    assert (
        msg.index("error_ceiling 1 -> 2")
        < msg.index("warning_ceiling 1 -> 2")
        < msg.index("violations_by_type[a] 1 -> 2")
        < msg.index("violations_by_type[z] 1 -> 2")
        < msg.index("warnings_by_type[wa] 1 -> 2")
        < msg.index("warnings_by_type[wz] 1 -> 2")
    )


def test_prop8_detect_raise_no_change_and_decrease_are_quiet():
    ratchets = (_oracle.DrcRatchet(Path("x.json")), ShimRatchet(Path("x.json")))
    old = {
        "boards": [
            {
                "board_id": "b1",
                "error_ceiling": 100,
                "warning_ceiling": 10,
                "violations_by_type": {"clearance": 5},
                "warnings_by_type": {"zone": 2},
            }
        ]
    }
    for new in (
        old,  # identical
        {  # only decreases
            "boards": [
                {
                    "board_id": "b1",
                    "error_ceiling": 50,
                    "warning_ceiling": 5,
                    "violations_by_type": {"clearance": 3},
                    "warnings_by_type": {"zone": 1},
                }
            ]
        },
        {"boards": []},  # board removed entirely
    ):
        for ratchet in ratchets:
            assert ratchet.detect_ceiling_raise(old, new, commit_message="fix: x") is None


def test_prop9_detect_raise_skips_new_boards():
    """A board absent from the old record cannot be a raise (nothing to
    raise FROM)."""
    ratchets = (_oracle.DrcRatchet(Path("x.json")), ShimRatchet(Path("x.json")))
    old = {"boards": []}
    new = {
        "boards": [
            {"board_id": "brand_new", "error_ceiling": 500, "warning_ceiling": 0}
        ]
    }
    for ratchet in ratchets:
        assert ratchet.detect_ceiling_raise(old, new, commit_message="fix: x") is None
