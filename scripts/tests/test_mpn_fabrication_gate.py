"""Tests for mpn_fabrication_gate.py.

Covers:
  - the falsifier stated in docs/evidence/2026-07-27-fabricated-mpn-audit.md:
    reconstructing the known case-4 fabrication (61.3 kOhm / ERA-3AEB6132V)
    must produce an E-series violation naming the 60.4/61.2/61.9 kOhm
    E192 neighbours -- if it doesn't, the gate is broken.
  - anti-vacuity: a glob matching no files, an .ato file with zero
    parseable value+mpn pairs, and a malformed/missing-field allowlist
    must all fail closed (exit 5), never a silent pass.
  - a genuine value<->MPN decode mismatch (real MPN, wrong declared value)
    is caught even though both values individually are E-series members.
  - an unrecognised MPN prefix is counted as UNCHECKED, not silently
    treated as passing -- and does not suppress an E-series finding on
    the same part.
  - the allowlist suppresses exactly the (file, ref, mpn, check) it names,
    and nothing else.
  - integration: running the real gate against today's elec/src/*.ato
    tree exits 3 (not 0) -- this project's fabricated parts must still be
    caught by the shipped gate, not just by a synthetic fixture.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mpn_fabrication_gate import (  # noqa: E402
    AllowlistEntry,
    ParsedPart,
    analyze,
    decode_mpn,
    in_series,
    load_allowlist,
    nearest_in_series,
    parse_ato_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "scripts" / "mpn_fabrication_gate.py"
REAL_ALLOWLIST = REPO_ROOT / "mpn-fabrication-allowlist.yaml"


def _write_ato(tmp_path: Path, name: str, body: str) -> Path:
    d = tmp_path / "elec" / "src"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# Falsifier: case 4 (61.3 kOhm / ERA-3AEB6132V) must fire.
# ---------------------------------------------------------------------------


def test_falsifier_case4_reconstruction_fires():
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=1591,
        ref="r_low_top",
        mpn="ERA-3AEB6132V",
        kind="R",
        declared_value=61300.0,
        declared_tol_pct=0.1,
    )
    result = analyze([part], allowlist=[])
    assert len(result.new_violations) == 1, "falsifier did NOT fire: case-4 fixture passed the gate"
    finding = result.new_violations[0]
    assert finding.kind == "eseries"
    # The exact neighbours the audit names.
    assert "60.4kohm" in finding.detail
    assert "61.2kohm" in finding.detail
    assert "61.9kohm" in finding.detail
    # And 61.3 itself must not be quietly listed as one of the "legal"
    # neighbours (only the "is not a member of" subject may name it).
    neighbours_clause = finding.detail.split("neighbours")[1]
    assert "61.3kohm" not in neighbours_clause


def test_eseries_neighbors_match_case4_exactly():
    neighbors = nearest_in_series(61300.0, "E192")
    assert {round(n) for n in neighbors} == {61200, 61900, 60400}
    assert not in_series(61300.0, "E192")


# ---------------------------------------------------------------------------
# Anti-vacuity: glob matches nothing, zero parts parsed, bad allowlist.
# ---------------------------------------------------------------------------


def test_missing_ato_glob_fails_closed(tmp_path):
    # No elec/src at all under this tmp repo -- but the gate script uses the
    # real repo's find_repo_root(), so instead exercise the same failure
    # path the CLI takes: a glob that matches nothing under the real repo.
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--ato-glob", "elec/src/*.this-does-not-exist"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 5, f"expected fail-closed exit 5, got {result.returncode}\n{result.stdout}\n{result.stderr}"
    assert "No .ato files matched" in result.stderr


def test_zero_parts_parsed_fails_closed(tmp_path):
    # A syntactically-plausible .ato file with no `.value =` / `.mpn =`
    # pairs at all -- the parser must not silently report "0 violations".
    _write_ato(tmp_path, "empty.ato", "module Empty:\n    signal x\n")
    parts = parse_ato_file(tmp_path / "elec" / "src" / "empty.ato", tmp_path)
    assert parts == []

    # Exercise the actual CLI fail-closed path using a glob that resolves
    # (under the real repo) to a real file with no R/C pairs -- interfaces.ato
    # declares interfaces, not components.
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--ato-glob", "elec/src/interfaces.ato"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 5, f"expected fail-closed exit 5, got {result.returncode}\n{result.stdout}"
    assert "0 resistor/capacitor value+mpn pairs parsed" in result.stderr


def test_empty_file_parses_to_zero_parts(tmp_path):
    p = _write_ato(tmp_path, "blank.ato", "")
    assert parse_ato_file(p, tmp_path) == []


def test_malformed_allowlist_fails_closed(tmp_path):
    bad = tmp_path / "bad-allowlist.yaml"
    bad.write_text("allowlist:\n  - file: elec/src/modules.ato\n    ref: foo\n")  # missing mpn/checks/reason
    assert load_allowlist(bad) is None


def test_missing_allowlist_file_is_empty_not_an_error(tmp_path):
    # A genuinely *absent* allowlist (never created) is fine -- 0 exceptions,
    # not a parse failure. Only a present-but-broken file fails closed.
    assert load_allowlist(tmp_path / "does-not-exist.yaml") == []


def test_unparseable_yaml_fails_closed(tmp_path):
    bad = tmp_path / "bad2.yaml"
    bad.write_text("allowlist: [this is not: valid: yaml: at all: [[[\n")
    assert load_allowlist(bad) is None


# ---------------------------------------------------------------------------
# Decode-mismatch detection: real MPN, wrong declared value (r_div_bot /
# LogicUVLOComparator shape) -- both values individually are E96 members,
# so only the decode check should catch it.
# ---------------------------------------------------------------------------


def test_decode_mismatch_real_mpn_wrong_value():
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=2417,
        ref="r_div_bot",
        mpn="RC0603FR-0710KL",  # decodes to 10k
        kind="R",
        declared_value=100000.0,  # but declared as 100k
        declared_tol_pct=1.0,
    )
    result = analyze([part], allowlist=[])
    kinds = {f.kind for f in result.new_violations}
    assert "decode" in kinds
    decode_finding = next(f for f in result.new_violations if f.kind == "decode")
    assert "10kohm" in decode_finding.detail
    assert "100kohm" in decode_finding.detail
    # Both 10k and 100k are themselves E96 members -- eseries must NOT also
    # fire here, proving the two checks are independent.
    assert "eseries" not in kinds


def test_agreeing_mpn_and_value_produces_no_decode_finding():
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=1155,
        ref="r_fb_top",
        mpn="RC0603FR-07100KL",  # decodes to 100k
        kind="R",
        declared_value=100000.0,
        declared_tol_pct=1.0,
    )
    result = analyze([part], allowlist=[])
    assert result.new_violations == []
    assert result.decoded_count == 1


# ---------------------------------------------------------------------------
# Unknown-prefix handling: reported unchecked, never silently passed, and
# doesn't suppress an independent E-series finding on the same part.
# ---------------------------------------------------------------------------


def test_unknown_prefix_is_unchecked_not_silently_passed():
    assert decode_mpn("TOTALLY-MADE-UP-MPN-1234") is None
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=1,
        ref="r_mystery",
        mpn="TOTALLY-MADE-UP-MPN-1234",
        kind="R",
        declared_value=61300.0,  # same non-standard value as case 4
        declared_tol_pct=0.1,
    )
    result = analyze([part], allowlist=[])
    assert result.unchecked_count == 1
    assert result.decoded_count == 0
    # Unchecked MPN family must not suppress the independent E-series check.
    assert any(f.kind == "eseries" for f in result.new_violations)


# ---------------------------------------------------------------------------
# Allowlist precision: suppresses exactly what it names.
# ---------------------------------------------------------------------------


def test_allowlist_suppresses_named_entry_only():
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=1591,
        ref="r_low_top",
        mpn="ERA-3AEB6132V",
        kind="R",
        declared_value=61300.0,
        declared_tol_pct=0.1,
    )
    entries = [
        AllowlistEntry(
            file="elec/src/modules.ato",
            ref="r_low_top",
            mpn="ERA-3AEB6132V",
            checks={"eseries"},
            reason="test fixture only",
        )
    ]
    result = analyze([part], allowlist=entries)
    assert result.new_violations == []
    assert len(result.allowlisted_findings) == 1


def test_allowlist_does_not_suppress_different_ref():
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=1591,
        ref="r_low_top",
        mpn="ERA-3AEB6132V",
        kind="R",
        declared_value=61300.0,
        declared_tol_pct=0.1,
    )
    entries = [
        AllowlistEntry(
            file="elec/src/modules.ato",
            ref="some_other_ref",  # doesn't match
            mpn="ERA-3AEB6132V",
            checks={"eseries"},
            reason="wrong ref -- must not match",
        )
    ]
    result = analyze([part], allowlist=entries)
    assert len(result.new_violations) == 1


def test_allowlist_check_kind_is_scoped():
    # An entry allowlisting only "decode" must not suppress an "eseries"
    # finding on the same (file, ref, mpn).
    part = ParsedPart(
        file="elec/src/modules.ato",
        line=1591,
        ref="r_low_top",
        mpn="ERA-3AEB6132V",
        kind="R",
        declared_value=61300.0,
        declared_tol_pct=0.1,
    )
    entries = [
        AllowlistEntry(
            file="elec/src/modules.ato",
            ref="r_low_top",
            mpn="ERA-3AEB6132V",
            checks={"decode"},  # not eseries
            reason="test fixture only",
        )
    ]
    result = analyze([part], allowlist=entries)
    assert len(result.new_violations) == 1
    assert result.new_violations[0].kind == "eseries"


# ---------------------------------------------------------------------------
# Real-tree integration: the shipped gate must fail on today's tree.
# ---------------------------------------------------------------------------


def test_gate_fails_on_real_tree_today():
    """Prove the gate actually catches what's in the repo right now, not
    just synthetic fixtures. If this ever starts passing, either every
    finding below was independently fixed+allowlisted with cause, or the
    gate regressed -- check docs/evidence/2026-07-27-fabricated-mpn-audit.md."""
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 3, (
        f"expected the gate to fail (exit 3) on today's tree; got {result.returncode}\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "r_low_top" in result.stdout, "known case-4 fabrication no longer flagged"
    assert "ERA-3AEB6132V" in result.stdout
    # Parts-inspected / MPN-decoded counts must be reported, not just an
    # exit code.
    assert "Parts inspected:" in result.stdout
    assert "MPNs decoded" in result.stdout
    assert "MPNs unchecked" in result.stdout


def test_real_allowlist_parses_and_is_hand_curated_shape():
    entries = load_allowlist(REAL_ALLOWLIST)
    assert entries is not None, "committed allowlist must be valid YAML with required fields"
    assert len(entries) > 0
    for e in entries:
        assert e.reason.strip(), f"allowlist entry for {e.ref} has no reason"
        assert e.checks <= {"eseries", "decode"}
