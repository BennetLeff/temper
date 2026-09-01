"""Tests for check_layer_plane_emission_coverage.py.

Property 1 (parser role-token fidelity) and Property 2 (zone-emitter
layer coverage) are both proven sound against SYNTHETIC scratch copies of
the real source files here -- mutating a copy of the real, currently
broken text to the fixed shape and confirming the gate's verdict flips.
This mirrors ``test_check_hv_netclass_coverage.py``'s pattern of testing
pure helper functions against constructed inputs rather than only the
live repository state.

``TestRealRepoIntegration`` documents the CURRENT (still broken, as of
this gate's writing) state of ``origin/main``: both properties violate.
See docs/evidence/2026-08-11-correspondence-gates.md for the full
before/after narrative and the path to blocking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_layer_plane_emission_coverage import (  # noqa: E402
    EXIT_VIOLATION,
    GateError,
    check_emitter_covers_declared_planes,
    check_parser_captures_layer_role,
    load_declared_plane_layers,
    load_emittable_layers,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
REAL_PARSER_SOURCE = REPO_ROOT / "packages" / "temper-design-bundle" / "src" / "parse_engine.rs"
REAL_EMITTER_SOURCE = (
    REPO_ROOT
    / "packages"
    / "temper-placer"
    / "src"
    / "temper_placer"
    / "router_v6"
    / "_zone_pour_stitch.py"
)

_BROKEN_LAYERS_ARM = """"layers" => {
                // `(0 "F.Cu" signal)` -- the NAME is the quoted token at
                // index 1; index 2 is the layer type.
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub
                        && let Some(KiNode::Atom(a)) = s.get(1) {
                            board.layers.push(atom_to_string(a));
                        }
                }
            }"""

_FIXED_LAYERS_ARM = """"layers" => {
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub
                        && let Some(KiNode::Atom(a)) = s.get(1)
                        && let Some(KiNode::Atom(role)) = s.get(2) {
                            board.layers.push(atom_to_string(a));
                            board.layer_roles.push(atom_to_string(role));
                        }
                }
            }"""


def _board_text(layers: list[tuple[str, str]]) -> str:
    entries = "\n".join(f'    ({i} "{name}" {role})' for i, (name, role) in enumerate(layers))
    return f"""
(kicad_pcb (version 20211014)
  (layers
{entries}
  )
)
"""


def _rust_source_with_arm(arm_body: str) -> str:
    """A minimal scratch module reproducing raw_board_from_tree's shape:
    the target 'layers' arm plus two DECOY 'layers' arms elsewhere (pad
    and zone layer lists) that this gate must not accidentally match."""
    return f"""
fn parse_pad(sub: &[KiNode]) -> Pad {{
    match head {{
        "layers" => {{
            for layer in sub.iter().skip(1) {{
                if let KiNode::Atom(a) = layer {{
                    layers.push(atom_to_string(a));
                }}
            }}
        }}
        _ => {{}}
    }}
}}

fn raw_board_from_tree(root: &[KiNode], errors: &mut Vec<String>) -> RawBoard {{
    for node in items {{
        match head {{
            {arm_body}
            "setup" => {{}}
            _ => {{}}
        }}
    }}
    board
}}

fn parse_zone(items: &[KiNode]) -> Option<RawZone> {{
    match head {{
        "layers" => {{
            for layer in s.iter().skip(1) {{
                if let KiNode::Atom(a) = layer {{
                    layers.push(atom_to_string(a));
                }}
            }}
        }}
        _ => {{}}
    }}
}}
"""


def _emitter_source(return_layers: list[str]) -> str:
    layers_literal = ", ".join(f'"{layer_}"' for layer_ in return_layers)
    return f'''
def _zone_layers_for_net(net_name: str) -> list[str]:
    """Docstring."""
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES

    nc_name = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    nc = TEMPER_NET_CLASSES.get(nc_name)
    if nc is not None and nc.routing_strategy in ("plane_required", "plane_preferred"):
        return [{layers_literal}]
    return []


def _zone_params_for_net(net_name: str) -> tuple[float, float]:
    return 0.3, 0.3
'''


# ---------------------------------------------------------------------------
# 1. Mutations
# ---------------------------------------------------------------------------


class TestParserRoleTokenFidelity:
    def test_broken_arm_flagged(self, tmp_path):
        src = tmp_path / "parse_engine.rs"
        src.write_text(_rust_source_with_arm(_BROKEN_LAYERS_ARM))
        ok, detail = check_parser_captures_layer_role(src)
        assert ok is False
        assert "discarded" in detail

    def test_fixed_arm_passes(self, tmp_path):
        src = tmp_path / "parse_engine.rs"
        src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        ok, detail = check_parser_captures_layer_role(src)
        assert ok is True

    def test_decoy_layers_arms_do_not_affect_the_verdict(self, tmp_path):
        """The pad-layers and zone-layers decoy arms in the fixture both
        lack index-2 role tokens (correctly, for their own shape) -- the
        gate must scope to raw_board_from_tree specifically, not just
        find the first/any '"layers" =>' arm in the file."""
        src = tmp_path / "parse_engine.rs"
        src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        ok, _ = check_parser_captures_layer_role(src)
        assert ok is True  # would be False if the decoy pad-layers arm won

    def test_missing_function_fails_closed(self, tmp_path):
        src = tmp_path / "parse_engine.rs"
        src.write_text("fn something_else() {}\n")
        with pytest.raises(GateError):
            check_parser_captures_layer_role(src)


class TestZoneEmitterCoverage:
    def test_hardcoded_f_b_cu_misses_declared_inner_planes(self, tmp_path):
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu", "B.Cu"]))
        emittable = load_emittable_layers(emitter)
        missing = check_emitter_covers_declared_planes(["In1.Cu", "In2.Cu"], emittable)
        assert missing == ["In1.Cu", "In2.Cu"]

    def test_fixed_emitter_covers_declared_planes(self, tmp_path):
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]))
        emittable = load_emittable_layers(emitter)
        missing = check_emitter_covers_declared_planes(["In1.Cu", "In2.Cu"], emittable)
        assert missing == []

    def test_missing_function_fails_closed(self, tmp_path):
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text("def something_else():\n    pass\n")
        with pytest.raises(GateError):
            load_emittable_layers(emitter)


class TestDeclaredPlaneLayers:
    def test_extracts_only_power_role_layers(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(
            _board_text(
                [("F.Cu", "signal"), ("In1.Cu", "power"), ("In2.Cu", "power"), ("B.Cu", "signal")]
            )
        )
        assert load_declared_plane_layers(board) == ["In1.Cu", "In2.Cu"]

    def test_no_power_layers_is_a_tool_error_via_run(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([("F.Cu", "signal"), ("B.Cu", "signal")]))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu", "B.Cu"]))
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        state, report = run(board, parser_src, emitter)
        assert state == "tool_error"


# ---------------------------------------------------------------------------
# 2. End-to-end run() against synthetic fixtures
# ---------------------------------------------------------------------------


class TestRunEndToEnd:
    def test_both_broken(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([("F.Cu", "signal"), ("In1.Cu", "power"), ("B.Cu", "signal")]))
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_BROKEN_LAYERS_ARM))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu", "B.Cu"]))
        state, report = run(board, parser_src, emitter)
        assert state == "violation"
        assert report.parser_captures_role is False
        assert report.unemittable_planes == ["In1.Cu"]

    def test_both_fixed(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([("F.Cu", "signal"), ("In1.Cu", "power"), ("B.Cu", "signal")]))
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu", "B.Cu", "In1.Cu"]))
        state, report = run(board, parser_src, emitter)
        assert state == "clean"

    def test_fixing_only_one_property_leaves_a_violation(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([("F.Cu", "signal"), ("In1.Cu", "power"), ("B.Cu", "signal")]))
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu", "B.Cu"]))  # still missing In1.Cu
        state, report = run(board, parser_src, emitter)
        assert state == "violation"
        assert report.parser_captures_role is True
        assert report.unemittable_planes == ["In1.Cu"]


# ---------------------------------------------------------------------------
# 3. Anti-vacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_board(self, tmp_path):
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu"]))
        state, report = run(tmp_path / "nope.kicad_pcb", parser_src, emitter)
        assert state == "tool_error"

    def test_missing_parser_source(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([("In1.Cu", "power")]))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu"]))
        state, report = run(board, tmp_path / "nope.rs", emitter)
        assert state == "tool_error"

    def test_missing_emitter_source(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text(_board_text([("In1.Cu", "power")]))
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        state, report = run(board, parser_src, tmp_path / "nope.py")
        assert state == "tool_error"

    def test_board_with_no_layers_block(self, tmp_path):
        board = tmp_path / "board.kicad_pcb"
        board.write_text("(kicad_pcb (version 1))")
        parser_src = tmp_path / "parse_engine.rs"
        parser_src.write_text(_rust_source_with_arm(_FIXED_LAYERS_ARM))
        emitter = tmp_path / "_zone_pour_stitch.py"
        emitter.write_text(_emitter_source(["F.Cu"]))
        state, report = run(board, parser_src, emitter)
        assert state == "tool_error"


# ---------------------------------------------------------------------------
# 4. Real-repo integration -- PROPERTY 1 fixed, PROPERTY 2 still live
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_property1_fixed_property2_still_live(self):
        """UPDATED 2026-08-21, per the instruction this test carried: "If
        either is fixed, update this test to match and reconsider whether the
        CI step should stop being advisory for that property."

        PROPERTY 1 IS NOW FIXED. `raw_board_from_tree`'s `layers` arm reads
        index 2 -- the role token -- so `parser_captures_role` is True, where
        this test previously asserted False. Renamed from
        `test_real_repo_currently_violates_both_properties`, which now
        describes the opposite of the measured state.

        PROPERTY 2 IS STILL LIVE: In1.Cu and In2.Cu are declared with role
        'power' in the board yet appear nowhere in `_zone_layers_for_net`'s
        body, so no path reachable from `route_pcb` can pour copper on either.
        The gate as a whole therefore still exits non-zero and its CI step
        stays `continue-on-error: true`.

        ON THE ADVISORY QUESTION: the gate script reports both properties
        through one exit code, so it cannot go blocking while Property 2 is
        open. But this test IS blocking (`continue-on-error: false` on the
        `Declared <-> emitted layer gate tests` step), so asserting
        `parser_captures_role is True` here is what actually enforces the fix
        -- a regression fails CI on this file even though the gate itself
        stays advisory. That is the "stop being advisory for that property"
        the original note asked for, achieved without splitting the script.
        """
        state, report = run(REAL_BOARD, REAL_PARSER_SOURCE, REAL_EMITTER_SOURCE)
        assert state == "violation"
        assert report.declared_plane_layers == ["In1.Cu", "In2.Cu"]
        assert report.parser_captures_role is True
        assert report.unemittable_planes == ["In1.Cu", "In2.Cu"]

    def test_real_repo_gate_exits_violation_not_error(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/check_layer_plane_emission_coverage.py")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == EXIT_VIOLATION, result.stdout + result.stderr
