"""Tests for check_bom_source_reconciliation.py.

Every fixture here is synthetic (a tiny, hand-built BOM.md + elec/src tree
under ``tmp_path``) -- matching the convention in
``test_check_netlist_board_reconciliation.py`` (synthetic board/netlist
pairs passed directly to ``gate.run()``) rather than
``test_check_isolation_keepout.py``'s kiutils-object-graph style, since this
gate's inputs are plain text (a markdown table, ``.ato`` source), not a
binary board format.

Groups:
  TestBomParsing        -- split_designators()/parse_bom() unit behaviour:
                            comma lists, one hyphenated range, Package-column
                            optional, non-component tables skipped.
  TestSourceParsing     -- parse_component_defaults()/parse_instances(): the
                            component/module/interface keyword distinction,
                            class-level default MPN vs. per-instance override,
                            reused variable names.
  TestFindingClasses    -- seeded-defect anti-vacuity proof, one per the
                            three finding classes required by the plan this
                            gate implements (R14): costed-with-no-circuit,
                            wired-but-uncosted, same-designator-different-MPN.
                            Each test asserts the gate FAILS (exit 3) on a
                            tree seeded with exactly that defect.
  TestPass              -- a fully reconciled BOM/source pair -> exit 0.
  TestAntiVacuity       -- missing BOM, zero BOM rows, zero .ato files, zero
                            component instantiations, malformed/unparseable
                            allowlist -- all GATE ERROR (exit 5), never a
                            silent pass.
  TestAllowlist         -- an allowlisted finding is suppressed; a
                            differently-scoped one (different kind/file) is
                            not.
  TestFailBeforePassAfter -- explicit before/after pair: the same source
                            tree, BOM missing a line (fails) vs. BOM carrying
                            it (passes) -- proves the gate would have caught
                            the defect this plan was written to close.
  TestRealTree          -- the actual gate, actual repo, at HEAD: must run a
                            real (non-vacuous) check and must currently FAIL
                            (the BOM does not yet reconcile -- that is this
                            gate's whole reason to exist), pinning the real
                            finding counts so a future accidental regression
                            in the parser (e.g. silently parsing 0 rows) is
                            caught by "counts changed" rather than trusted
                            silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_bom_source_reconciliation import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    KIND_COSTED_NO_CIRCUIT,
    KIND_MPN_MISMATCH,
    KIND_WIRED_UNCOSTED,
    AllowlistEntry,
    allowlist_covers,
    load_allowlist,
    normalize,
    parse_bom,
    parse_component_defaults,
    parse_instances,
    reconcile,
    run,
    split_designators,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BOM = REPO_ROOT / "docs" / "hardware" / "BOM.md"
REAL_ATO_GLOB = "elec/src/*.ato"
REAL_ALLOWLIST = REPO_ROOT / "bom-reconciliation-allowlist.yaml"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

BOM_HEADER = "| Ref | Description | Part Number | Manufacturer | Qty | Package | Notes |\n"
BOM_SEP = "|-----|-------------|-------------|--------------|-----|---------|-------|\n"
BOM_HEADER_NO_PKG = "| Ref | Description | Part Number | Manufacturer | Qty | Notes |\n"
BOM_SEP_NO_PKG = "|-----|-------------|-------------|--------------|-----|-------|\n"


def write_bom(tmp_path: Path, rows: str, header: str = BOM_HEADER, sep: str = BOM_SEP) -> Path:
    p = tmp_path / "BOM.md"
    p.write_text(f"# Title\n\n## 1. Section\n\n{header}{sep}{rows}\n")
    return p


def write_ato(tmp_path: Path, name: str, body: str) -> Path:
    d = tmp_path / "elec" / "src"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body)
    return p


COMPONENTS_ATO = """\
component Resistor:
    designator_prefix = "R"

component Capacitor:
    designator_prefix = "C"

component Relay_SPDT:
    designator_prefix = "K"

component TestPoint:
    designator_prefix = "TP"
    mpn = "GENERIC_TEST_POINT"
    bom_exclude = true
"""


def ato_files(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "elec" / "src").glob("*.ato"))


# ---------------------------------------------------------------------------
# TestBomParsing
# ---------------------------------------------------------------------------


class TestBomParsing:
    def test_comma_list_splits_into_individual_designators(self) -> None:
        assert split_designators("C_BUS1, C_BUS1B, C_BUS2, C_BUS2B") == [
            "C_BUS1",
            "C_BUS1B",
            "C_BUS2",
            "C_BUS2B",
        ]

    def test_hyphen_range_expands(self) -> None:
        assert split_designators("R_OVP1-3") == ["R_OVP1", "R_OVP2", "R_OVP3"]

    def test_single_bare_token(self) -> None:
        assert split_designators("K_BYPASS") == ["K_BYPASS"]

    def test_parses_qty_and_designator_and_mpn(self, tmp_path: Path) -> None:
        bom = write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")
        lines = parse_bom(bom)
        assert len(lines) == 1
        assert lines[0].designator == "K_BYPASS"
        assert lines[0].mpn == "G4A-1A-E DC12"
        assert lines[0].qty_field == "1"

    def test_package_column_optional(self, tmp_path: Path) -> None:
        bom = write_bom(
            tmp_path,
            "| TP1 | Test Point | GENERIC_TEST_POINT | - | 1 | note |\n",
            header=BOM_HEADER_NO_PKG,
            sep=BOM_SEP_NO_PKG,
        )
        lines = parse_bom(bom)
        assert len(lines) == 1
        assert lines[0].designator == "TP1"

    def test_non_component_table_is_skipped(self, tmp_path: Path) -> None:
        # A table that lacks "Part Number"/"Qty" headers (e.g. a summary
        # table) must not be parsed as component rows.
        text = (
            "# Title\n\n"
            "## Summary\n\n"
            "| Category | Count |\n"
            "|----------|-------|\n"
            "| Power | 44 |\n\n"
            "## 1. Real section\n\n" + BOM_HEADER + BOM_SEP +
            "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n"
        )
        p = tmp_path / "BOM.md"
        p.write_text(text)
        lines = parse_bom(p)
        assert len(lines) == 1
        assert lines[0].designator == "K_BYPASS"

    def test_missing_bom_returns_empty(self, tmp_path: Path) -> None:
        assert parse_bom(tmp_path / "does-not-exist.md") == []


# ---------------------------------------------------------------------------
# TestSourceParsing
# ---------------------------------------------------------------------------


class TestSourceParsing:
    def test_component_keyword_is_physical_module_and_interface_are_not(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(
            tmp_path,
            "modules.ato",
            "module Foo:\n"
            "    r1 = new Resistor\n"
            "    r1.mpn = \"RC0603FR-0710KL\"\n"
            "    sig = new ElectricSignal\n"  # not a `component` type -> excluded
            "    pwr = new ElectricPower\n",
        )
        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        assert "Resistor" in types
        assert "ElectricSignal" not in types
        parts = parse_instances(files, types, defaults, tmp_path)
        assert [p.var for p in parts] == ["r1"]
        assert parts[0].mpn == "RC0603FR-0710KL"

    def test_class_level_default_mpn_applies_when_no_override(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(tmp_path, "modules.ato", "module Foo:\n    tp1 = new TestPoint\n")
        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, tmp_path)
        assert parts[0].mpn == "GENERIC_TEST_POINT"

    def test_reused_var_name_gets_separate_instances_with_own_mpn(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(
            tmp_path,
            "modules.ato",
            "module A:\n"
            "    r_ref = new Resistor\n"
            "    r_ref.mpn = \"AAA\"\n"
            "module B:\n"
            "    r_ref = new Resistor\n"
            "    r_ref.mpn = \"BBB\"\n",
        )
        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, tmp_path)
        assert [p.mpn for p in parts if p.var == "r_ref"] == ["AAA", "BBB"]

    def test_instance_with_no_mpn_at_all_is_still_parsed(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(tmp_path, "modules.ato", "module Foo:\n    r1 = new Resistor\n")
        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, tmp_path)
        assert parts[0].mpn is None

    def test_normalize_is_case_and_underscore_insensitive(self) -> None:
        assert normalize("C_TANK1") == normalize("c_tank1") == "ctank1"


# ---------------------------------------------------------------------------
# TestFindingClasses -- one seeded-defect fixture per required finding class
# ---------------------------------------------------------------------------


def _minimal_matched_tree(tmp_path: Path) -> None:
    """A BOM + source pair that reconciles cleanly on its own -- the base
    every seeded-defect test in this group starts from and adds exactly one
    defect to, so each test proves that ONE specific defect class, and only
    it, is what makes the gate fail."""
    write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
    write_ato(
        tmp_path,
        "modules.ato",
        "module Top:\n"
        "    k_bypass = new Relay_SPDT\n"
        "    k_bypass.mpn = \"G4A-1A-E DC12\"\n",
    )
    write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")


class TestFindingClasses:
    def test_costed_no_circuit_fires_when_bom_line_has_no_source_match(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(tmp_path, "modules.ato", "module Top:\n    r1 = new Resistor\n    r1.mpn = \"AAA\"\n")
        # BOM costs a part with no source counterpart at all.
        bom = write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_VIOLATION

        # Direct unit-level proof of which finding kind fired.
        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, tmp_path)
        bom_lines = parse_bom(bom)
        report = reconcile(bom_lines, parts, [])
        kinds = {f.kind for f in report.new_findings}
        assert KIND_COSTED_NO_CIRCUIT in kinds
        costed = [f for f in report.new_findings if f.kind == KIND_COSTED_NO_CIRCUIT]
        assert any(f.designator == "K_BYPASS" for f in costed)

    def test_wired_uncosted_fires_when_source_instance_has_no_bom_line(self, tmp_path: Path) -> None:
        _minimal_matched_tree(tmp_path)
        # Add a second, wholly uncosted component -- e.g. the historical
        # c_tank3 defect this gate was built to catch (a third instance with
        # no corresponding BOM row).
        write_ato(
            tmp_path,
            "extra.ato",
            "module Extra:\n    c_tank3 = new Capacitor\n    c_tank3.mpn = \"942C16P1K-F\"\n",
        )
        bom_path = tmp_path / "BOM.md"
        code = run(bom_path, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_VIOLATION

        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, tmp_path)
        bom_lines = parse_bom(bom_path)
        report = reconcile(bom_lines, parts, [])
        wired = [f for f in report.new_findings if f.kind == KIND_WIRED_UNCOSTED]
        assert any(f.designator == "c_tank3" for f in wired)

    def test_mpn_mismatch_fires_when_same_designator_disagrees_on_mpn(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        # Seeded exactly like the real K_DIS1 defect this gate's own report
        # found: BOM says one relay MPN, source instantiates a different one
        # under the same designator.
        write_ato(
            tmp_path,
            "modules.ato",
            "module Top:\n"
            "    k_dis1 = new Relay_SPDT\n"
            "    k_dis1.mpn = \"RT314012\"\n",
        )
        bom = write_bom(tmp_path, "| K_DIS1 | Discharge Relay | G5LE-1 DC12 | Omron | 1 | THT | note |\n")
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_VIOLATION

        files = ato_files(tmp_path)
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, tmp_path)
        bom_lines = parse_bom(bom)
        report = reconcile(bom_lines, parts, [])
        mismatches = [f for f in report.new_findings if f.kind == KIND_MPN_MISMATCH]
        assert len(mismatches) == 1
        assert mismatches[0].designator == "K_DIS1"
        assert "G5LE-1 DC12" in mismatches[0].detail
        assert "RT314012" in mismatches[0].detail


# ---------------------------------------------------------------------------
# TestPass
# ---------------------------------------------------------------------------


class TestPass:
    def test_fully_reconciled_tree_passes(self, tmp_path: Path) -> None:
        _minimal_matched_tree(tmp_path)
        code = run(tmp_path / "BOM.md", "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_OK


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_bom_fails_closed(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(tmp_path, "modules.ato", "module Top:\n    r1 = new Resistor\n    r1.mpn = \"AAA\"\n")
        code = run(tmp_path / "does-not-exist.md", "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_GATE_ERROR

    def test_zero_bom_rows_fails_closed(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(tmp_path, "modules.ato", "module Top:\n    r1 = new Resistor\n    r1.mpn = \"AAA\"\n")
        bom = tmp_path / "BOM.md"
        bom.write_text("# Title\n\nNo tables here at all.\n")
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_GATE_ERROR

    def test_zero_ato_files_fails_closed(self, tmp_path: Path) -> None:
        bom = write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")
        code = run(bom, "elec/src/*.this-does-not-exist", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_GATE_ERROR

    def test_zero_component_definitions_fails_closed(self, tmp_path: Path) -> None:
        # .ato files exist, but none declares any `component <Name>:` block
        # -- the physical-type detector has nothing to anchor on.
        write_ato(tmp_path, "modules.ato", "module Top:\n    sig = new ElectricSignal\n")
        bom = write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_GATE_ERROR

    def test_zero_physical_instantiations_fails_closed(self, tmp_path: Path) -> None:
        # component types exist, but nothing instantiates one.
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(tmp_path, "modules.ato", "module Top:\n    sig = new ElectricSignal\n")
        bom = write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_GATE_ERROR

    def test_malformed_allowlist_fails_closed(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("allowlist:\n  - designator: K_BYPASS\n")  # missing kind/reason
        assert load_allowlist(bad) is None

        _minimal_matched_tree(tmp_path)
        code = run(tmp_path / "BOM.md", "elec/src/*.ato", bad, tmp_path)
        assert code == EXIT_GATE_ERROR

    def test_unparseable_yaml_fails_closed(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad2.yaml"
        bad.write_text("allowlist: [this is not: valid: yaml: [[[\n")
        assert load_allowlist(bad) is None

    def test_missing_allowlist_file_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert load_allowlist(tmp_path / "does-not-exist.yaml") == []

    def test_invalid_kind_in_allowlist_fails_closed(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad3.yaml"
        bad.write_text(
            "allowlist:\n"
            "  - kind: not_a_real_kind\n"
            "    designator: K_BYPASS\n"
            "    reason: because\n"
        )
        assert load_allowlist(bad) is None

    def test_empty_reason_fails_closed(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad4.yaml"
        bad.write_text(
            "allowlist:\n"
            "  - kind: costed_no_circuit\n"
            "    designator: K_BYPASS\n"
            "    reason: \"   \"\n"
        )
        assert load_allowlist(bad) is None


# ---------------------------------------------------------------------------
# TestAllowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_allowlist_suppresses_named_finding(self, tmp_path: Path) -> None:
        # Start from a tree that already reconciles cleanly on its own, then
        # add exactly one extra BOM-only line -- so the ONLY thing standing
        # between this tree and EXIT_OK is whether the allowlist suppresses
        # that one costed_no_circuit finding.
        _minimal_matched_tree(tmp_path)
        bom = write_bom(
            tmp_path,
            "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n"
            "| HS1 | Heatsink | 392-120AB | Wakefield-Vette | 1 | - | mechanical, not in elec/src |\n",
        )
        allow = tmp_path / "allow.yaml"
        allow.write_text(
            "allowlist:\n"
            "  - kind: costed_no_circuit\n"
            "    designator: HS1\n"
            "    reason: deliberately excluded for this test\n"
        )
        code = run(bom, "elec/src/*.ato", allow, tmp_path)
        assert code == EXIT_OK

    def test_allowlist_does_not_suppress_a_different_kind(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(
            tmp_path,
            "modules.ato",
            "module Top:\n    k_dis1 = new Relay_SPDT\n    k_dis1.mpn = \"RT314012\"\n",
        )
        bom = write_bom(tmp_path, "| K_DIS1 | Discharge Relay | G5LE-1 DC12 | Omron | 1 | THT | note |\n")
        # Allowlist covers wired_uncosted for K_DIS1, not the real
        # mpn_mismatch finding -- must NOT suppress it.
        allow = tmp_path / "allow.yaml"
        allow.write_text(
            "allowlist:\n"
            "  - kind: wired_uncosted\n"
            "    designator: k_dis1\n"
            "    reason: wrong kind on purpose\n"
        )
        code = run(bom, "elec/src/*.ato", allow, tmp_path)
        assert code == EXIT_VIOLATION

    def test_allowlist_covers_matches_case_and_underscore_insensitively(self) -> None:
        entries = [
            AllowlistEntry(kind="costed_no_circuit", designator="k_bypass", file=None, reason="x")
        ]
        assert allowlist_covers(entries, "costed_no_circuit", "K_BYPASS") is not None
        assert allowlist_covers(entries, "wired_uncosted", "K_BYPASS") is None

    def test_allowlist_file_scoping_is_respected(self) -> None:
        entries = [
            AllowlistEntry(
                kind="wired_uncosted", designator="comp", file="elec/src/modules.ato", reason="x"
            )
        ]
        assert allowlist_covers(entries, "wired_uncosted", "comp", "elec/src/modules.ato") is not None
        assert allowlist_covers(entries, "wired_uncosted", "comp", "elec/src/other.ato") is None


# ---------------------------------------------------------------------------
# TestFailBeforePassAfter
# ---------------------------------------------------------------------------


class TestFailBeforePassAfter:
    """Explicit before/after demonstration (the gate is new and has no prior
    git history of its own to diff against): the same source tree, a BOM
    missing one line vs. carrying it -- proves the gate would have caught
    the defect this plan was written to close, without using ``git stash``
    (forbidden in this repo -- the stash ref is shared across worktrees)."""

    def test_before_missing_bom_line_fails(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(
            tmp_path,
            "modules.ato",
            "module Top:\n"
            "    k_bypass = new Relay_SPDT\n"
            "    k_bypass.mpn = \"G4A-1A-E DC12\"\n"
            "    c_tank3 = new Capacitor\n"
            "    c_tank3.mpn = \"942C16P1K-F\"\n",
        )
        bom = write_bom(tmp_path, "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n")
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_VIOLATION

    def test_after_bom_line_added_passes(self, tmp_path: Path) -> None:
        write_ato(tmp_path, "components.ato", COMPONENTS_ATO)
        write_ato(
            tmp_path,
            "modules.ato",
            "module Top:\n"
            "    k_bypass = new Relay_SPDT\n"
            "    k_bypass.mpn = \"G4A-1A-E DC12\"\n"
            "    c_tank3 = new Capacitor\n"
            "    c_tank3.mpn = \"942C16P1K-F\"\n",
        )
        bom = write_bom(
            tmp_path,
            "| K_BYPASS | Bypass Relay | G4A-1A-E DC12 | Omron | 1 | THT | note |\n"
            "| C_TANK3 | Tank Capacitor | 942C16P1K-F | CDE | 1 | Axial | note |\n",
        )
        code = run(bom, "elec/src/*.ato", tmp_path / "no-allowlist.yaml", tmp_path)
        assert code == EXIT_OK


# ---------------------------------------------------------------------------
# TestRealTree -- the actual gate against the actual repo at HEAD.
# ---------------------------------------------------------------------------


class TestRealTree:
    def test_real_allowlist_parses_and_is_hand_curated_shape(self) -> None:
        entries = load_allowlist(REAL_ALLOWLIST)
        assert entries is not None, "real bom-reconciliation-allowlist.yaml failed to parse"
        assert len(entries) > 0
        for e in entries:
            assert e.kind in (KIND_COSTED_NO_CIRCUIT, KIND_WIRED_UNCOSTED, KIND_MPN_MISMATCH)
            assert e.designator.strip()
            assert e.reason.strip()

    def test_real_tree_runs_a_real_non_vacuous_check(self) -> None:
        """The gate must actually parse real, non-empty BOM rows and real,
        non-empty source instantiations against HEAD -- exit must be either
        OK or VIOLATION, never GATE ERROR (which would mean the parser
        silently found nothing to check)."""
        code = run(REAL_BOM, REAL_ATO_GLOB, REAL_ALLOWLIST)
        assert code in (EXIT_OK, EXIT_VIOLATION), (
            f"gate returned {code} (GATE ERROR) against the real repo tree -- "
            "the parser found nothing to check, which is never correct for a "
            "155-component design"
        )

    def test_real_tree_currently_fails_with_known_finding_count(self) -> None:
        """Pinned at gate-introduction time (2026-08-07): the BOM does not
        yet reconcile against source (that is this gate's whole reason to
        exist -- R14, docs/hardware/BOM.md's own long history of manual
        audits finding and re-finding drift). This assertion is deliberately
        an exact count, not just ">0": if it drops, either real drift got
        fixed (update the count down) or the allowlist silently grew to
        swallow a real finding (investigate before updating the count) --
        either way, silently letting the count drift is exactly the
        alarm-fatigue failure mode this gate exists to prevent elsewhere."""
        files = sorted(REPO_ROOT.glob(REAL_ATO_GLOB))
        types, defaults = parse_component_defaults(files)
        parts = parse_instances(files, types, defaults, REPO_ROOT)
        bom_lines = parse_bom(REAL_BOM)
        allowlist = load_allowlist(REAL_ALLOWLIST)
        assert allowlist is not None
        report = reconcile(bom_lines, parts, allowlist)
        by_kind: dict[str, int] = {}
        for f in report.new_findings:
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        assert by_kind.get(KIND_MPN_MISMATCH, 0) == 8, by_kind
        assert by_kind.get(KIND_COSTED_NO_CIRCUIT, 0) == 14, by_kind
        assert by_kind.get(KIND_WIRED_UNCOSTED, 0) == 27, by_kind
        assert len(report.new_findings) == 49, by_kind
