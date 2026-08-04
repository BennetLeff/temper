"""Tests for ``scripts/physics_soundness_register_gate.py`` (R20, plan
2026-08-02-004).

Covers all four implementation units' test scenarios:

- U1 register-loading: the real register parses, every entry has a non-empty
  proof type and a resolvable proof location, and each proof location file
  actually contains the cited proof symbol (substring check). An unknown
  proof type fails validation.
- U2 gap analysis: the stale-proof class (a register entry whose cited proof
  symbol is no longer in the file) is flagged, not silently carried.
- U3 gate contract: a deliberately added physics-gated encoder without a
  register entry fails the gate naming the encoder; removing an entry for an
  existing surface fails the gate; registering the surface clears the
  failure; the gate reports OK on the populated register with all surfaces
  covered.
- U4 register discipline: adding an entry without a proof type fails
  validation; an entry without a provenance note fails validation.
- KTD4 detection (both directions): a synthetic physics-dependent encoder is
  detected; a pure-geometry encoder is NOT flagged.

Uses temporary synthetic repos (subprocess runs) plus direct module-function
calls, following the ``test_check_physics_provenance.py`` pattern.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "physics_soundness_register_gate.py"
REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_REGISTER = REPO_ROOT / "power_pcb_dataset" / "physics_soundness_register.yaml"
SRC = REPO_ROOT / "packages" / "temper-placer" / "src"

HANDLERS_REL = "temper_placer/placer/cp_sat/handlers"
PROOF_PATH = f"packages/temper-placer/src/{HANDLERS_REL}/synthetic.py"

# The handlers-only scan spec, for detection unit tests that build a bare
# synthetic src tree (the other scan-set modules are not present there).
HANDLERS_ONLY_SPEC: list[dict] = [
    {"glob": f"{HANDLERS_REL}/*.py", "selector": "register_handler"},
]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run_gate(
    repo_root: Path | None = None,
    *,
    extra: list[str] | None = None,
    expect_fail: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the gate script; optionally against a synthetic repo root."""
    cmd = [sys.executable, str(SCRIPT)]
    if repo_root is not None:
        cmd += ["--repo-root", str(repo_root)]
    cmd += extra or []
    result = subprocess.run(cmd, capture_output=True, text=True)
    if expect_fail:
        assert result.returncode != 0, (
            f"Expected non-zero exit. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    else:
        assert result.returncode == 0, (
            f"Expected exit 0. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _import_module():
    """Import the gate script as a module for direct function calls."""
    spec = importlib.util.spec_from_file_location(
        "physics_soundness_register_gate", str(SCRIPT)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["physics_soundness_register_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


# -- synthetic modules ------------------------------------------------------

PHYSICS_IMPORT_MODULE = '''"""Synthetic physics-dependent encoder for gate tests."""
from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintType, SeparatedConstraint
from temper_placer.placer.cp_sat.handlers._registry import register_handler

from temper_placer.physics.thermal_fdm import solve_thermal


@register_handler(ConstraintType.SEPARATED)
def encode_thermal(constraint, components, model, ctx):
    """Synthetic encoder whose encoded bound depends on a physics quantity."""
    _ = solve_thermal
    return []
'''

BODY_REF_MODULE = '''"""Synthetic module: physics referenced only inside the surface body."""
from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintType, SeparatedConstraint
from temper_placer.placer.cp_sat.handlers._registry import register_handler


@register_handler(ConstraintType.SEPARATED)
def encode_body_ref(constraint, components, model, ctx):
    """No marker here; the bound depends on a physics field used in code."""
    solver = thermal_fdm  # Name reference inside the surface body
    _ = solver
    return []
'''

MARKER_ONLY_MODULE = '''"""Synthetic module: physics gating declared by marker only."""
from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintType, SeparatedConstraint
from temper_placer.placer.cp_sat.handlers._registry import register_handler


@register_handler(ConstraintType.SEPARATED)
def encode_marker_only(constraint, components, model, ctx):
    """A surface that declares physics gating explicitly.

    **Physics-gated surface (KTD4):** ``physics_gated: true``
    """
    return []
'''

PURE_GEOMETRY_MODULE = '''"""Synthetic pure-geometry encoder for gate tests."""
from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintType, SeparatedConstraint
from temper_placer.placer.cp_sat.handlers._registry import register_handler


@register_handler(ConstraintType.SEPARATED)
def encode_pure_geometry(constraint, components, model, ctx):
    """A pure-geometry encoder: no physics references, no marker."""
    return []
'''

DOMAIN_STUB = (
    '"""Stub so the domain_clearance scan spec resolves in synthetic trees."""\n'
    "def generate_domain_clearance_constraints():\n"
    "    return []\n"
)

CONSTRAINT_MODEL_STUB = (
    '"""Stub so the constraint_model scan spec resolves in synthetic trees."""\n'
    "class Constraint:\n"
    "    pass\n"
)


def _write_synthetic_src(src_root: Path, modules: dict[str, str]) -> None:
    for rel, text in modules.items():
        path = src_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _write_register(register_path: Path, surfaces: list[dict]) -> None:
    register_path.parent.mkdir(parents=True, exist_ok=True)
    register_path.write_text(
        yaml.safe_dump(
            {
                "_schema_version": 1,
                "_goal": "synthetic test register",
                "_march": {"2026-08-02": "synthetic test tree"},
                "surfaces": surfaces,
            }
        )
    )


def _build_synthetic_tree(
    tmp_path: Path,
    modules: dict[str, str],
    surfaces: list[dict],
) -> Path:
    """Build a synthetic repo root: src tree + register, plus stubs for the
    other scan-set modules so discovery has no tool errors."""
    root = tmp_path / "repo"
    src = root / "packages" / "temper-placer" / "src"
    all_modules = dict(modules)
    all_modules.setdefault(
        "temper_placer/placer/cp_sat/domain_clearance.py", DOMAIN_STUB
    )
    all_modules.setdefault(
        "temper_placer/router_v6/constraint_model.py", CONSTRAINT_MODEL_STUB
    )
    _write_synthetic_src(src, all_modules)
    _write_register(
        root / "power_pcb_dataset" / "physics_soundness_register.yaml", surfaces
    )
    return root


def _entry(**overrides: object) -> dict:
    base: dict = {
        "encoder": "temper_placer.placer.cp_sat.handlers.synthetic.encode_thermal",
        "proof_type": "conservative-bound",
        "proof_location": {
            "path": PROOF_PATH,
            "symbol": "encode_thermal",
        },
        "coverage_scope": "covers the synthetic encoder's bound",
        "last_verified": "2026-08-02",
        "provenance_note": "synthetic test entry",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# U1: register loading on the real tree
# ---------------------------------------------------------------------------


def test_real_register_loads_and_every_entry_resolves() -> None:
    mod = _import_module()
    register = mod.load_register(REAL_REGISTER)
    entries = mod.parse_entries(register)
    assert len(entries) >= 3, "expected at least the three plan-named proofs"
    for e in entries:
        assert not e.errors, f"{e.encoder}: {e.errors}"
        assert e.proof_type in mod.ALLOWED_PROOF_TYPES
        assert e.coverage_scope, e.encoder
        assert e.last_verified, e.encoder
        assert e.provenance_note, e.encoder
        # proof location resolves to a real file
        proof_file = REPO_ROOT / e.proof_path
        assert proof_file.exists(), e.proof_path
        # substring check on the cited proof symbol (U1 test scenario)
        assert e.proof_symbol in proof_file.read_text(), (
            f"symbol {e.proof_symbol!r} not in {e.proof_path}"
        )
        # the encoder key resolves to real code (register/code agreement)
        ok, _ = mod.encoder_resolves(e.encoder, SRC)
        assert ok, e.encoder


def test_real_register_has_march_and_schema() -> None:
    mod = _import_module()
    register = mod.load_register(REAL_REGISTER)
    assert "_march" in register and register["_march"]
    assert isinstance(register["surfaces"], list) and register["surfaces"]


# ---------------------------------------------------------------------------
# U1 + U4: entry schema validation
# ---------------------------------------------------------------------------


def test_unknown_proof_type_fails_validation() -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(proof_type="magic-bound")]}
    entries = mod.parse_entries(register)
    assert entries[0].errors
    assert "unknown proof_type" in entries[0].errors[0]


def test_add_without_proof_type_fails_validation() -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(proof_type="")]}
    entries = mod.parse_entries(register)
    assert any("proof_type" in err for err in entries[0].errors)


def test_edit_without_provenance_note_fails_validation() -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(provenance_note="")]}
    entries = mod.parse_entries(register)
    assert any("provenance_note" in err for err in entries[0].errors)


def test_missing_coverage_scope_fails_validation() -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(coverage_scope="")]}
    entries = mod.parse_entries(register)
    assert any("coverage_scope" in err for err in entries[0].errors)


def test_missing_last_verified_fails_validation() -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(last_verified="")]}
    entries = mod.parse_entries(register)
    assert any("last_verified" in err for err in entries[0].errors)


def test_bad_last_verified_date_fails_validation() -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(last_verified="yesterday")]}
    entries = mod.parse_entries(register)
    assert any("YYYY-MM-DD" in err for err in entries[0].errors)


def test_proof_location_path_missing_fails_validation(tmp_path: Path) -> None:
    mod = _import_module()
    register = {"surfaces": [_entry(proof_location={"path": "does/not/exist.py", "symbol": "x"})]}
    entries = mod.parse_entries(register)
    assert not entries[0].errors
    mod.validate_proof_location(entries[0], tmp_path)
    assert any("does not exist" in err for err in entries[0].errors)


def test_proof_symbol_missing_from_file_is_flagged(tmp_path: Path) -> None:
    """U2 stale-proof class: the cited proof is no longer in the file, so the
    register entry is flagged, not silently carried."""
    mod = _import_module()
    (tmp_path / "proof.py").write_text("def unrelated():\n    pass\n")
    register = {
        "surfaces": [
            _entry(proof_location={"path": "proof.py", "symbol": "THE STALE PROOF"})
        ]
    }
    entries = mod.parse_entries(register)
    mod.validate_proof_location(entries[0], tmp_path)
    assert any("not found" in err for err in entries[0].errors)


def test_malformed_yaml_is_tool_error(tmp_path: Path) -> None:
    mod = _import_module()
    reg = tmp_path / "register.yaml"
    reg.write_text("surfaces: [ { unclosed: \n")
    report = mod.run_check(repo_root=tmp_path, register_path=reg)
    assert report.tool_errors, "malformed YAML must be a tool error"
    assert report.ok is False


def test_missing_register_is_tool_error(tmp_path: Path) -> None:
    mod = _import_module()
    report = mod.run_check(
        repo_root=tmp_path, register_path=tmp_path / "nope.yaml"
    )
    assert any("register load failed" in e for e in report.tool_errors)


# ---------------------------------------------------------------------------
# KTD4 detection: both directions
# ---------------------------------------------------------------------------


def test_physics_import_detected(tmp_path: Path) -> None:
    """A synthetic encoder whose module imports a physics module is detected
    as physics-gated (KTD4 AST import/reference scan)."""
    mod = _import_module()
    src = tmp_path / "src"
    _write_synthetic_src(src, {f"{HANDLERS_REL}/synthetic.py": PHYSICS_IMPORT_MODULE})
    surfaces, errors = mod.discover_surfaces(src, HANDLERS_ONLY_SPEC)
    assert not errors
    hit = [s for s in surfaces if s.symbol == "encode_thermal"]
    assert len(hit) == 1
    assert hit[0].physics_gated
    assert any("physics module" in r for r in hit[0].reasons)


def test_surface_body_physics_reference_detected(tmp_path: Path) -> None:
    """A surface whose own code references a physics module (no module-level
    import) is detected per-surface."""
    mod = _import_module()
    src = tmp_path / "src"
    _write_synthetic_src(src, {f"{HANDLERS_REL}/synthetic.py": BODY_REF_MODULE})
    surfaces, errors = mod.discover_surfaces(src, HANDLERS_ONLY_SPEC)
    assert not errors
    hit = [s for s in surfaces if s.symbol == "encode_body_ref"]
    assert len(hit) == 1
    assert hit[0].physics_gated


def test_marker_only_surface_detected(tmp_path: Path) -> None:
    """A surface with no physics reference but an explicit ``physics_gated:
    true`` marker is detected (the per-surface declaration)."""
    mod = _import_module()
    src = tmp_path / "src"
    _write_synthetic_src(src, {f"{HANDLERS_REL}/synthetic.py": MARKER_ONLY_MODULE})
    surfaces, errors = mod.discover_surfaces(src, HANDLERS_ONLY_SPEC)
    assert not errors
    hit = [s for s in surfaces if s.symbol == "encode_marker_only"]
    assert len(hit) == 1
    assert hit[0].physics_gated
    assert any("physics_gated: true" in r for r in hit[0].reasons)


def test_pure_geometry_encoder_not_flagged(tmp_path: Path) -> None:
    """The other KTD4 direction: a pure-geometry encoder (no physics
    reference, no marker) is discovered but NOT physics-gated."""
    mod = _import_module()
    src = tmp_path / "src"
    _write_synthetic_src(src, {f"{HANDLERS_REL}/synthetic.py": PURE_GEOMETRY_MODULE})
    surfaces, errors = mod.discover_surfaces(src, HANDLERS_ONLY_SPEC)
    assert not errors
    hit = [s for s in surfaces if s.symbol == "encode_pure_geometry"]
    assert len(hit) == 1
    assert not hit[0].physics_gated


def test_scan_missing_module_is_tool_error(tmp_path: Path) -> None:
    mod = _import_module()
    src = tmp_path / "empty-src"
    src.mkdir(parents=True)
    surfaces, errors = mod.discover_surfaces(src)
    assert not surfaces
    assert errors, "a scan-set module missing from the tree must be a tool error"


# ---------------------------------------------------------------------------
# U3: gate contract
# ---------------------------------------------------------------------------


def test_gate_ok_on_populated_real_register() -> None:
    result = _run_gate()
    assert "OK" in result.stdout


def test_unregistered_physics_gated_encoder_fails_naming_it(tmp_path: Path) -> None:
    root = _build_synthetic_tree(
        tmp_path,
        modules={f"{HANDLERS_REL}/synthetic.py": PHYSICS_IMPORT_MODULE},
        surfaces=[],
    )
    result = _run_gate(root, expect_fail=True)
    assert result.returncode == 3
    assert "encode_thermal" in result.stderr
    assert "physics-gated surface has no register entry" in result.stderr


def test_removing_entry_for_existing_surface_fails(tmp_path: Path) -> None:
    """Deleting a register entry for a surface that still exists fails the
    gate, naming the surface (U3 'removing an entry fails')."""
    mod = _import_module()
    register = mod.load_register(REAL_REGISTER)
    register["surfaces"] = [
        s for s in register["surfaces"] if "encode_separated" not in s["encoder"]
    ]
    reg = tmp_path / "register.yaml"
    reg.write_text(yaml.safe_dump(register))
    report = mod.run_check(repo_root=REPO_ROOT, register_path=reg)
    assert report.coverage_errors
    assert any("encode_separated" in e for e in report.coverage_errors)


def test_registering_the_surface_clears_the_failure(tmp_path: Path) -> None:
    root = _build_synthetic_tree(
        tmp_path,
        modules={f"{HANDLERS_REL}/synthetic.py": PHYSICS_IMPORT_MODULE},
        surfaces=[_entry()],
    )
    result = _run_gate(root)
    assert "OK" in result.stdout
    assert "encode_thermal" in result.stdout


def test_orphan_register_entry_fails(tmp_path: Path) -> None:
    """A register entry whose encoder does not resolve to code fails the
    gate (register and code must agree)."""
    root = _build_synthetic_tree(
        tmp_path,
        modules={f"{HANDLERS_REL}/synthetic.py": PURE_GEOMETRY_MODULE},
        surfaces=[_entry(encoder="temper_placer.placer.cp_sat.handlers.encode_ghost")],
    )
    result = _run_gate(root, expect_fail=True)
    assert result.returncode == 3
    assert "does not resolve to code" in result.stderr


def test_stale_proof_entry_fails_gate(tmp_path: Path) -> None:
    root = _build_synthetic_tree(
        tmp_path,
        modules={f"{HANDLERS_REL}/synthetic.py": PURE_GEOMETRY_MODULE},
        surfaces=[
            _entry(
                proof_location={"path": PROOF_PATH, "symbol": "NO SUCH SYMBOL HERE"}
            )
        ],
    )
    result = _run_gate(root, expect_fail=True)
    assert result.returncode == 3
    assert "not found" in result.stderr


def test_invalid_entry_blocks_gate(tmp_path: Path) -> None:
    root = _build_synthetic_tree(
        tmp_path,
        modules={f"{HANDLERS_REL}/synthetic.py": PURE_GEOMETRY_MODULE},
        surfaces=[_entry(proof_type="not-a-real-type")],
    )
    result = _run_gate(root, expect_fail=True)
    assert result.returncode == 3
    assert "unknown proof_type" in result.stderr


def test_missing_register_subprocess_is_tool_error(tmp_path: Path) -> None:
    result = _run_gate(
        extra=["--register", str(tmp_path / "absent.yaml")], expect_fail=True
    )
    assert result.returncode == 5


def test_verbose_lists_discovered_surfaces() -> None:
    result = _run_gate(extra=["--verbose"])
    assert "discovered" in result.stdout
    assert "encode_separated" in result.stdout
