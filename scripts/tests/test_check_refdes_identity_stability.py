"""Tests for check_refdes_identity_stability.py.

Most tests here build small synthetic Python "test files" on disk (via
``tmp_path``) and synthetic netlists/manifests (same convention as
``test_check_domain_partition.py``), so each scenario is a controlled,
minimal reproduction of one specific shape -- rather than depending on the
real repo tree drifting under the test. A handful of regression tests
reproduce, verbatim in miniature, the exact false-positive shapes measured
against the real tree while building this gate (see the module docstring
of ``check_refdes_identity_stability.py`` and
``docs/evidence/2026-07-30-refdes-identity-stability-gate.md``):
synthetic-board tests whose helper functions happen to build a
``*.kicad_pcb`` filename, a same-named-but-different-module
``parse_netlist`` import, and a doc-citation filename that embeds a safety
word ("...isolator-footprints.md"). One integration test (marked
``slow``) runs the real gate against the real repo tree and only makes
loose, evidence-doc-referenced assertions, skipping if the real
netlist/manifest are unavailable -- matching every real-board test
elsewhere in this repo (e.g. ``_real_board_fixture.load_real_board_placement``
callers).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_domain_partition import (  # noqa: E402
    Isolator,
    Manifest,
    Netlist,
    NetlistComponent,
    ProtectiveImpedanceChain,
    parse_netlist,
)
from check_refdes_identity_stability import (  # noqa: E402
    GateError,
    Occurrence,
    _ref_has_nearby_claim,
    _strip_doc_citations,
    build_ref_pattern,
    discover_ref_prefixes,
    find_scan_files,
    manifest_declared_paths,
    run,
    scan_file,
    verify,
)

# ---------------------------------------------------------------------------
# Netlist / manifest builders (same S-expression convention as
# test_check_domain_partition.py)
# ---------------------------------------------------------------------------


def make_netlist_text(components: list[tuple[str, str]]) -> str:
    comp_blocks = []
    for ref, instance_path in components:
        comp_blocks.append(
            f'    (comp (ref "{ref}")\n'
            f'      (value "?")\n'
            f'      (footprint "Test:Footprint")\n'
            f'      (libsource (lib "lib") (part "TestPart") (description "d"))\n'
            f'      (sheetpath (names "/tmp/x/main.ato:Top::{instance_path}") '
            f'(tstamps "t"))\n'
            f'      (tstamps "t"))\n'
        )
    return (
        '(export (version "E")\n'
        '  (design (source "test") (date "") (tool "test"))\n'
        "  (components\n" + "".join(comp_blocks) + "  )\n"
        "  (libparts)\n"
        '  (nets\n    (net (code "1") (name "n1")\n'
        f'      (node (ref "{components[0][0]}") (pin "1") (pintype "stereo"))\n'
        "    )\n  )\n"
        ")\n"
    )


def write_netlist(tmp_path: Path, components: list[tuple[str, str]], name: str = "default.net") -> Path:
    p = tmp_path / "elec_build"
    p.mkdir(exist_ok=True)
    f = p / name
    f.write_text(make_netlist_text(components))
    return f


def make_manifest_yaml(isolator_paths: list[str]) -> str:
    isolators_yaml = "\n".join(
        f"""  - instance_path: {p}
    component: "Test isolator"
    groups:
      primary: ["1", "2"]
      secondary: ["3", "4"]"""
        for p in isolator_paths
    )
    return f"""
schema_version: 1
domains:
  HV:
    nets: ["ac_l"]
  SELV:
    nets: ["v15"]
isolators:
{isolators_yaml}
"""


def write_manifest(tmp_path: Path, isolator_paths: list[str], name: str = "manifest.yaml") -> Path:
    p = tmp_path / name
    p.write_text(make_manifest_yaml(isolator_paths))
    return p


def touch_src(tmp_path: Path) -> Path:
    src = tmp_path / "elec_src"
    src.mkdir(exist_ok=True)
    (src / "main.ato").write_text("# empty\n")
    return src


# ---------------------------------------------------------------------------
# discover_ref_prefixes / build_ref_pattern
# ---------------------------------------------------------------------------


class TestDiscoverPrefixes:
    def test_derives_prefixes_from_netlist_not_a_hardcoded_list(self, tmp_path: Path):
        netlist_path = write_netlist(tmp_path, [("U1", "a.b"), ("C2", "c.d"), ("K3", "e.f")])
        netlist = parse_netlist(netlist_path)
        prefixes = discover_ref_prefixes(netlist)
        assert prefixes == frozenset({"U", "C", "K"})

    def test_zero_matching_refs_is_a_gate_error(self, tmp_path: Path):
        # A ref with no trailing digits can't yield a prefix.
        netlist_path = write_netlist(tmp_path, [("WEIRD", "a.b")])
        netlist = parse_netlist(netlist_path)
        with pytest.raises(GateError):
            discover_ref_prefixes(netlist)


class TestRefPattern:
    def test_matches_exact_prefix_plus_digits_only(self):
        pattern = build_ref_pattern(frozenset({"U", "C", "RV"}))
        assert pattern.fullmatch("U3")
        assert pattern.fullmatch("C104")
        assert pattern.fullmatch("RV1")
        assert not pattern.fullmatch("U3A")  # not a bare <prefix><digits>
        assert not pattern.fullmatch("3U")
        assert not pattern.fullmatch("Q1")  # prefix not in the discovered set
        assert not pattern.fullmatch("some U3 sentence")


# ---------------------------------------------------------------------------
# find_scan_files
# ---------------------------------------------------------------------------


class TestFindScanFiles:
    def test_finds_py_files_under_any_tests_dir(self, tmp_path: Path):
        (tmp_path / "pkg" / "tests").mkdir(parents=True)
        (tmp_path / "pkg" / "tests" / "test_a.py").write_text("x = 1\n")
        (tmp_path / "pkg" / "src").mkdir(parents=True)
        (tmp_path / "pkg" / "src" / "not_scanned.py").write_text("x = 1\n")
        found = find_scan_files(tmp_path)
        assert found == [tmp_path / "pkg" / "tests" / "test_a.py"]

    def test_excludes_pycache(self, tmp_path: Path):
        (tmp_path / "pkg" / "tests" / "__pycache__").mkdir(parents=True)
        (tmp_path / "pkg" / "tests" / "__pycache__" / "test_a.cpython.pyc").write_bytes(b"")
        (tmp_path / "pkg" / "tests" / "__pycache__" / "stray.py").write_text("x=1\n")
        found = find_scan_files(tmp_path)
        assert found == []


# ---------------------------------------------------------------------------
# _strip_doc_citations / _ref_has_nearby_claim
# ---------------------------------------------------------------------------


class TestClaimProximity:
    def test_claim_on_same_line_is_found(self):
        ctx = "U7 genuinely straddles domains (it carries gnd and DC_BUS_RTN)"
        assert _ref_has_nearby_claim(ctx, "U7")

    def test_unrelated_ref_in_same_function_is_not_a_claim(self):
        """Regression: a function-wide claim search flagged TP3 as an
        isolator claim purely because U7 (a DIFFERENT ref in the same
        docstring) was described elsewhere as straddling domains -- with
        enough separation between the two mentions that they must not be
        treated as the same claim (mirrors the real docstring's spacing:
        "TP3<->U7" is named early, "U7 genuinely straddles domains" appears
        many lines later, and TP3 is never itself called an isolator)."""
        ctx = (
            "The pair investigated was specifically TP3<->U7.\n"
            "\n\n\n\n\n\n\n\n\n\n"
            "U7 genuinely straddles domains, confirmed directly.\n"
            "\n\n\n\n\n\n\n\n\n\n"
            "assert {c.a, c.b} == {'TP3', 'U7'}\n"
        )
        assert _ref_has_nearby_claim(ctx, "U7")
        assert not _ref_has_nearby_claim(ctx, "TP3")

    def test_doc_citation_filename_is_not_a_claim(self):
        """Regression: 'docs/evidence/2026-07-28-tank-cap-and-isolator-
        footprints.md', word-wrapped across the docstring's own line
        break, sits one line above an unrelated mention of C27 and must
        not be read as an isolator claim about C27."""
        ctx = (
            "(C25/C26, see docs/evidence/\n"
            "2026-07-28-tank-cap-and-isolator-footprints.md) plus\n"
            "one component never resynced at all (C27/tank.c_tank3).\n"
        )
        cleaned = _strip_doc_citations(ctx)
        assert "isolator" not in cleaned
        assert not _ref_has_nearby_claim(cleaned, "C27")

    def test_doc_citation_stripping_preserves_line_count(self):
        ctx = "line0\ndocs/evidence/\n2026-07-01-some-isolator-thing.md\nline3\n"
        cleaned = _strip_doc_citations(ctx)
        assert cleaned.count("\n") == ctx.count("\n")


# ---------------------------------------------------------------------------
# scan_file: shape/dataflow classification
# ---------------------------------------------------------------------------


SAFETY_DOC = '"""Mains<->SELV isolation barrier test (IEC 60335, REINFORCED creepage)."""\n'


def write_test_module(tmp_path: Path, name: str, body: str) -> Path:
    tests_dir = tmp_path / "pkg" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    p = tests_dir / name
    p.write_text(body)
    return p


class TestLoadBearingDetection:
    def test_direct_compare_is_load_bearing(self, tmp_path: Path):
        body = SAFETY_DOC + (
            "def test_isolator_ref():\n"
            "    v = get_violation()\n"
            "    assert v.ref_a == 'U1'\n"
        )
        f = write_test_module(tmp_path, "test_a.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"U"})))
        assert ok
        assert raw == 1
        occ = occs[0]
        assert occ.ref == "U1"
        assert occ.safety_relevant
        assert occ.assert_reachable
        assert occ.load_bearing

    def test_dict_key_used_via_comprehension_is_load_bearing(self, tmp_path: Path):
        """Reproduces test_emi_filter.py's real pattern: refs is a dict
        literal, never compared directly, but its keys are read through a
        `for r in refs` comprehension into a Compare/Subscript."""
        body = SAFETY_DOC + (
            "def _load():\n"
            "    refs = {'F1': 'fuse'}\n"
            "    comps = {'known': object()}\n"
            "    missing = [r for r in refs if r not in comps]\n"
            "    return missing\n"
            "\n"
            "def test_mains_filter():\n"
            "    assert _load() == []\n"
        )
        f = write_test_module(tmp_path, "test_b.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"F"})))
        assert ok
        assert raw == 1
        occ = occs[0]
        assert occ.func_qualname.endswith("::_load")
        assert occ.safety_relevant  # via caller (test_mains_filter has no safety doc itself,
        # but the MODULE docstring is safety-relevant and applies to every function)
        assert occ.assert_reachable  # _load has no assert itself, but its caller does
        assert occ.load_bearing

    def test_decorative_dict_value_is_not_load_bearing(self, tmp_path: Path):
        """Reproduces test_ground_plane.py's real pattern: a ref sits in a
        dict value that is passed to a checker function whose RETURN
        VALUE (not the dict) is what gets asserted on -- the checker never
        reads the ref field. Must be discovered (Tier 1) but NOT promoted
        to load-bearing (Tier 2): changing the ref could not change this
        test's pass/fail.
        """
        body = SAFETY_DOC + (
            "def check_star_ground_point(domains):\n"
            "    return type('R', (), {'passed': True})()\n"
            "\n"
            "def test_isolation_barrier():\n"
            "    ground_domains = {'connections': [{'ref': 'C6'}]}\n"
            "    result = check_star_ground_point(ground_domains)\n"
            "    assert result.passed\n"
        )
        f = write_test_module(tmp_path, "test_c.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"C"})))
        assert ok
        assert raw == 1
        occ = occs[0]
        assert occ.safety_relevant
        assert occ.assert_reachable
        assert not occ.load_bearing

    def test_parametrize_value_used_via_subscript_is_load_bearing(self, tmp_path: Path):
        body = SAFETY_DOC + (
            "import pytest\n"
            "@pytest.mark.parametrize('ref,expected', [('T1', 9.1), ('K1', 8.0)])\n"
            "def test_isolator_pad_gap(ref, expected):\n"
            "    by_ref = {'T1': 9.1, 'K1': 8.0}\n"
            "    assert by_ref[ref] == expected\n"
        )
        f = write_test_module(tmp_path, "test_d.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"T", "K"})))
        assert ok
        # T1/K1 appear twice each: once in the parametrize decorator, once
        # in the by_ref dict literal in the function body.
        assert raw == 4
        load_bearing_refs = {o.ref for o in occs if o.load_bearing}
        assert load_bearing_refs == {"T1", "K1"}

    def test_non_safety_context_is_excluded(self, tmp_path: Path):
        body = (
            '"""Ordinary unrelated fixture test, no safety vocabulary here."""\n'
            "def test_widget():\n"
            "    assert get_ref() == 'U1'\n"
        )
        f = write_test_module(tmp_path, "test_e.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"U"})))
        assert ok
        assert raw == 1
        assert not occs[0].safety_relevant

    def test_no_assert_anywhere_is_excluded(self, tmp_path: Path):
        body = SAFETY_DOC + (
            "def helper_no_assert():\n"
            "    return 'U1'\n"
        )
        f = write_test_module(tmp_path, "test_f.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"U"})))
        assert ok
        assert raw == 1
        assert not occs[0].assert_reachable


class TestRealBoardBoundDetection:
    def test_load_real_board_placement_marks_real_board_bound(self, tmp_path: Path):
        body = SAFETY_DOC + (
            "def test_isolator():\n"
            "    from tests.requirements.safety._real_board_fixture import load_real_board_placement\n"
            "    placement, domains, stats = load_real_board_placement()\n"
            "    assert placement['components'][0]['ref'] == 'U3'\n"
        )
        f = write_test_module(tmp_path, "test_g.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"U"})))
        assert ok
        assert occs[0].real_board_bound

    def test_synthetic_kicad_pcb_filename_is_not_real_board_bound(self, tmp_path: Path):
        """Regression: scripts/tests/test_check_isolation_keepout.py's
        fully-synthetic ``write_board(tmp_path, board, name="board.kicad_pcb")``
        helper false-triggered a bare 'kicad_pcb' substring marker."""
        body = SAFETY_DOC + (
            "def write_board(tmp_path, name='board.kicad_pcb'):\n"
            "    return tmp_path / name\n"
            "\n"
            "def test_barrier_intrusion(tmp_path):\n"
            "    board_path = write_board(tmp_path)\n"
            "    extra_ref = 'C99'\n"
            "    assert extra_ref == 'C99'\n"
        )
        f = write_test_module(tmp_path, "test_h.py", body)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"C"})))
        assert ok
        assert not occs[0].real_board_bound

    def test_ambiguous_parse_netlist_requires_matching_import(self, tmp_path: Path):
        """Regression: a locally-defined parse_netlist() (e.g.
        check_footprint_drift's own, tested against a synthetic tmp_path
        netlist) must not be mistaken for check_domain_partition's real
        one just because the call text matches."""
        wrong_import = SAFETY_DOC + (
            "from check_footprint_drift import parse_netlist\n"
            "def test_x(tmp_path):\n"
            "    netlist = parse_netlist(tmp_path / 'default.net')\n"
            "    assert netlist.components['C6'].ref == 'C6'\n"
        )
        f = write_test_module(tmp_path, "test_i.py", wrong_import)
        occs, raw, ok = scan_file(f, tmp_path, build_ref_pattern(frozenset({"C"})))
        assert ok
        assert not occs[0].real_board_bound

        right_import = SAFETY_DOC + (
            "from check_domain_partition import parse_netlist\n"
            "def test_y(tmp_path):\n"
            "    netlist = parse_netlist(tmp_path / 'default.net')\n"
            "    assert netlist.components['C6'].ref == 'C6'\n"
        )
        f2 = write_test_module(tmp_path, "test_j.py", right_import)
        occs2, raw2, ok2 = scan_file(f2, tmp_path, build_ref_pattern(frozenset({"C"})))
        assert ok2
        assert occs2[0].real_board_bound


# ---------------------------------------------------------------------------
# verify()
# ---------------------------------------------------------------------------


def _occ(ref: str, has_claim: bool) -> Occurrence:
    return Occurrence(
        file=Path("x.py"),
        lineno=1,
        ref=ref,
        func_qualname="x.py::test_x",
        safety_relevant=True,
        assert_reachable=True,
        load_bearing=True,
        real_board_bound=True,
        has_claim=has_claim,
    )


class TestVerify:
    def _netlist(self) -> Netlist:
        return Netlist(
            components={
                "U3": NetlistComponent(ref="U3", instance_path="power_in.zcd_opto"),
                "U7": NetlistComponent(ref="U7", instance_path="power_mgmt.buck_3v3.buck"),
            },
            nets={},
            net_nodes={},
            pin_net={},
            ref_pins={},
        )

    def _manifest_declared(self) -> frozenset[str]:
        return frozenset({"power_in.zcd_opto"})

    def test_match_when_current_path_is_declared(self):
        v = verify([_occ("U3", has_claim=True)], self._netlist(), self._manifest_declared())
        assert len(v) == 1
        assert v[0].verdict == "MATCH"
        assert v[0].current_instance_path == "power_in.zcd_opto"

    def test_mismatch_when_current_path_is_not_declared(self):
        """The exact scenario this gate was built for: U7 now resolves to
        a buck converter, not a declared isolator."""
        v = verify([_occ("U7", has_claim=True)], self._netlist(), self._manifest_declared())
        assert len(v) == 1
        assert v[0].verdict == "MISMATCH"
        assert v[0].current_instance_path == "power_mgmt.buck_3v3.buck"

    def test_mismatch_when_ref_no_longer_exists(self):
        v = verify([_occ("U99", has_claim=True)], self._netlist(), self._manifest_declared())
        assert v[0].verdict == "MISMATCH"
        assert v[0].current_instance_path is None

    def test_unverified_when_no_claim_text(self):
        v = verify([_occ("U7", has_claim=False)], self._netlist(), self._manifest_declared())
        assert v[0].verdict == "UNVERIFIED"

    def test_shape_only_when_not_real_board_bound(self):
        occ = _occ("U7", has_claim=True)
        occ.real_board_bound = False
        v = verify([occ], self._netlist(), self._manifest_declared())
        assert v[0].verdict == "SHAPE_ONLY"

    def test_non_load_bearing_occurrence_is_dropped(self):
        occ = _occ("U7", has_claim=True)
        occ.load_bearing = False
        assert verify([occ], self._netlist(), self._manifest_declared()) == []


# ---------------------------------------------------------------------------
# manifest_declared_paths
# ---------------------------------------------------------------------------


class TestManifestDeclaredPaths:
    def test_includes_isolators_and_chain_members(self):
        manifest = Manifest(
            domains={"HV": ["ac_l"], "SELV": ["v15"]},
            isolators=[
                Isolator(instance_path="a.b", component="x", groups={"p": ["1"], "s": ["2"]})
            ],
            chains=[
                ProtectiveImpedanceChain(
                    name="chain1",
                    component="r",
                    chain=["c.d1", "c.d2"],
                    boundary_a="ac_l",
                    boundary_b="v15",
                    min_length=2,
                )
            ],
        )
        paths = manifest_declared_paths(manifest)
        assert paths == frozenset({"a.b", "c.d1", "c.d2"})


# ---------------------------------------------------------------------------
# run(): end-to-end synthetic scenario, and fail-closed conditions
# ---------------------------------------------------------------------------


class TestRunEndToEnd:
    def _setup(self, tmp_path: Path, components, isolator_paths):
        netlist_path = write_netlist(tmp_path, components)
        manifest_path = write_manifest(tmp_path, isolator_paths)
        src_dir = touch_src(tmp_path)
        return netlist_path, manifest_path, src_dir

    def test_detects_a_genuine_mismatch(self, tmp_path: Path, monkeypatch):
        """End-to-end: a test module hardcodes 'U7' as the claimed isolator,
        but the synthetic netlist now resolves U7 to something the
        manifest does not declare as an isolator."""
        netlist_path, manifest_path, src_dir = self._setup(
            tmp_path,
            components=[("U3", "power_in.zcd_opto"), ("U7", "power_mgmt.buck_3v3.buck")],
            isolator_paths=["power_in.zcd_opto"],
        )
        # Skip freshness by writing a matching build stamp.
        _stamp_fresh(netlist_path, src_dir)

        body = SAFETY_DOC + (
            "def test_isolator_pair():\n"
            "    \"\"\"U7 is the gate-driver isolator, straddling the mains<->SELV barrier.\"\"\"\n"
            "    from tests.requirements.safety._real_board_fixture import load_real_board_placement\n"
            "    placement, domains, stats = load_real_board_placement()\n"
            "    v = get_violation(placement)\n"
            "    assert v.ref_a == 'U7'\n"
        )
        write_test_module(tmp_path, "test_isolators.py", body)

        report = run(tmp_path, netlist_path, manifest_path, src_dir)
        assert report.raw_literal_count >= 1
        mismatches = [v for v in report.verdicts if v.verdict == "MISMATCH"]
        assert any(v.occurrence.ref == "U7" for v in mismatches)

    def test_missing_netlist_is_gate_error(self, tmp_path: Path):
        manifest_path = write_manifest(tmp_path, ["a.b"])
        src_dir = touch_src(tmp_path)
        with pytest.raises(GateError):
            run(tmp_path, tmp_path / "elec_build" / "default.net", manifest_path, src_dir)

    def test_zero_scan_files_is_gate_error(self, tmp_path: Path):
        netlist_path, manifest_path, src_dir = self._setup(
            tmp_path, [("U1", "a.b")], ["a.b"]
        )
        _stamp_fresh(netlist_path, src_dir)
        with pytest.raises(GateError, match="zero .py files"):
            run(tmp_path, netlist_path, manifest_path, src_dir)

    def test_zero_ref_literals_anywhere_is_gate_error(self, tmp_path: Path):
        netlist_path, manifest_path, src_dir = self._setup(
            tmp_path, [("U1", "a.b")], ["a.b"]
        )
        _stamp_fresh(netlist_path, src_dir)
        write_test_module(
            tmp_path, "test_nothing.py", "def test_x():\n    assert 1 == 1\n"
        )
        with pytest.raises(GateError, match="zero ref-designator"):
            run(tmp_path, netlist_path, manifest_path, src_dir)


def _stamp_fresh(netlist_path: Path, src_dir: Path) -> None:
    """Write a build stamp so check_netlist_freshness (content-hash mode)
    treats this synthetic netlist as fresh -- same helper
    (``write_stamp``) ``scripts/write_build_stamp.py`` itself calls, so
    this test file does not depend on shelling out to `make netlist`."""
    from _lib.freshness import write_stamp

    source_files = sorted(src_dir.rglob("*.ato"))
    write_stamp(netlist_path, source_files, src_dir)


# ---------------------------------------------------------------------------
# Real-tree integration (loose assertions only; skips if unavailable)
# ---------------------------------------------------------------------------


class TestRealTreeIntegration:
    @pytest.mark.slow
    def test_real_tree_finds_the_known_instance(self):
        """Runs the actual gate against the real repo tree. Requires
        `make netlist` to have been run first; skips (not fails) if the
        compiled netlist/manifest are unavailable or stale -- same
        convention as every real-board test in
        packages/temper-placer/tests/requirements/safety/.

        Loosely asserts the denominator is non-trivial and that the known
        instance this gate was built to surface
        (test_the_seven_known_intra_footprint_blockers_are_now_visible's
        hardcoded 'U3'/'U7') is discoverable with a verdict, not silently
        dropped -- without asserting an exact MATCH/MISMATCH verdict,
        since that verdict legitimately flips depending on which branch
        is checked out (see docs/evidence/2026-07-30-refdes-identity-
        stability-gate.md for the cross-check against a sibling branch
        that DOES show MISMATCH).
        """
        from _lib.repo import find_repo_root

        repo_root = find_repo_root(Path(__file__).resolve().parent)
        netlist_path = repo_root / "elec" / "build" / "default.net"
        manifest_path = repo_root / "elec" / "domain_manifest.yaml"
        src_dir = repo_root / "elec" / "src"
        if not netlist_path.exists():
            pytest.skip(f"{netlist_path} not found -- run `make netlist` first")

        try:
            report = run(repo_root, netlist_path, manifest_path, src_dir)
        except GateError as exc:
            pytest.skip(f"gate could not run against the real tree: {exc}")

        assert report.raw_literal_count > 1000
        assert report.real_board_bound_count > 0

        targeted = [
            v
            for v in report.verdicts
            if v.occurrence.ref in ("U3", "U7")
            and "test_the_seven_known_intra_footprint_blockers_are_now_visible"
            in v.occurrence.func_qualname
        ]
        assert targeted, (
            "expected the known instance (test_the_seven_known_intra_footprint_"
            "blockers_are_now_visible's hardcoded U3/U7) to be discoverable "
            "with SOME verdict -- got none, meaning the gate's scope regressed"
        )
        assert all(v.verdict in ("MATCH", "MISMATCH") for v in targeted)
