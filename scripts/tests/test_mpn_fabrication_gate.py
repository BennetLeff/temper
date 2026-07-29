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
  - per manufacturer family taught to the decoder: a true-positive decode
    (wherever possible against a part that is NOT in this repo, so the test
    proves the decoder reads the manufacturer's scheme rather than the repo's
    strings), a structurally malformed string that must fall back to
    UNCHECKED, and a value that must be reported as disagreeing.
  - the two families deliberately left unimplemented (Murata DE, Vishay VY2)
    stay UNCHECKED, with the reasoning pinned in the test docstrings.
  - integration: running the real gate against today's elec/src/*.ato tree
    exits 3, naming c_tank1/c_tank2 (WIMA FKP1U021507E00JSSD encodes 15 nF
    against a declared 150 nF) -- a defect the decoder could not see before
    the WIMA family was added, left unfixed and unallowlisted on purpose.
    The five fabrications the 2026-07-27 audit found -- including the case-4
    anchor reconstructed above (r_low_top / ERA-3AEB6132V) -- were
    independently fixed in source with cited distributor verification (see
    docs/evidence/2026-07-27-era-resistor-resolution.md and
    docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md), not allowlisted
    away.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mpn_fabrication_gate import (  # noqa: E402
    AllowlistEntry,
    ParsedPart,
    analyze,
    classify_unchecked,
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
# Newly taught families (feat/mpn-decoder-families).
#
# Every encoding under test comes from the manufacturer's published
# part-numbering / ordering-information table, cited in the corresponding
# decoder docstring in mpn_fabrication_gate.py. The tests are written around
# what must be REJECTED, because a decoder that accepts every part already in
# the tree has proven nothing: for each family there is a true-positive decode,
# a structurally malformed string that must fall back to UNCHECKED, and a
# value that must be reported as disagreeing.
#
# Where a true-positive is a part that exists in this repo, it is paired
# wherever possible with a second true-positive that does NOT -- e.g.
# FKP1Y022207E00MSSD, a distributor-stocked WIMA part (DigiKey 19131711,
# 0.022 uF / 6000 VDC) that appears nowhere in elec/src -- so the decoder is
# demonstrably reading the manufacturer's scheme rather than the repo's
# strings.
# ---------------------------------------------------------------------------


def _mismatch_part(mpn: str, kind: str, declared: float, tol: float | None = None) -> ParsedPart:
    return ParsedPart(
        file="elec/src/modules.ato",
        line=1,
        ref="fixture",
        mpn=mpn,
        kind=kind,
        declared_value=declared,
        declared_tol_pct=tol,
    )


def _decode_findings(part: ParsedPart) -> list:
    return [f for f in analyze([part], allowlist=[]).new_violations if f.kind == "decode"]


# --- Vishay AC / AC-AT / AC-NI cemented wirewound (doc 28730 p.2) ----------


def test_vishay_ac_decodes_true_positive():
    d = decode_mpn("AC05000003901JAC00")
    assert d is not None and d.kind == "R"
    assert d.value == pytest.approx(3900.0)
    assert d.tol_pct == 5.0  # tolerance code J
    # Datasheet's own worked example, which is not in this repo: AC03 15 ohm.
    d2 = decode_mpn("AC03000001509JAC00")
    assert d2 is not None and d2.value == pytest.approx(15.0)  # multiplier 9 = x10^-1


def test_vishay_ac_rejects_malformed():
    # Multiplier digit 5 is not one of the published multipliers (7,8,9,0,1,2).
    assert decode_mpn("AC05000003905JAC00") is None
    # ...and the part is reported under its family, not silently dropped.
    group, reason = classify_unchecked("AC05000003905JAC00")
    assert group == "Vishay AC wirewound"
    assert "not a published" in reason
    # Truncated VALUE field: 17 characters instead of 18.
    assert decode_mpn("AC0500000390JAC00") is None


def test_vishay_ac_reports_value_disagreement():
    # Real MPN shape encoding 3.9 kOhm, declared as 39 kOhm.
    findings = _decode_findings(_mismatch_part("AC05000003901JAC00", "R", 39000.0, 5.0))
    assert len(findings) == 1
    assert "3.9kohm" in findings[0].detail and "39kohm" in findings[0].detail


def test_vishay_ac_non_standard_value_fails_eseries():
    # 3.85 kOhm is in no E24 series; the datasheet says "Resistance value to be
    # selected from E24 series", which is why this family feeds its decoded
    # tolerance into the E-series check.
    part = _mismatch_part("AC05000003851JAC00", "R", 3850.0, None)
    kinds = {f.kind for f in analyze([part], allowlist=[]).new_violations}
    assert "eseries" in kinds


# --- TDK / EPCOS B32xxx, B81xxx film (Marking and ordering code system) ----


def test_tdk_film_decodes_true_positive():
    d = decode_mpn("B32671L6474K000")
    assert d is not None and d.kind == "C"
    assert d.value == pytest.approx(470e-9)
    # TDK's own worked example from the ordering-code document, not in this
    # repo: B32652A3154K = 15 x 10^4 pF = 150 nF.
    d2 = decode_mpn("B32652A3154K000")
    assert d2 is not None and d2.value == pytest.approx(150e-9)
    # The X2 mains capacitor.
    d3 = decode_mpn("B32922C3224M289")
    assert d3 is not None and d3.value == pytest.approx(220e-9)


def test_tdk_film_rejects_malformed():
    # Two capacitance digits where the scheme fixes three (digits 9...11).
    assert decode_mpn("B32671L647K0000") is None
    # Tolerance code Q is not one of the published letters (A/H/J/K/M).
    assert decode_mpn("B32671L6474Q000") is None
    # Wrong product block: B33 is not "32 = metallized film / 81 = EMI".
    assert decode_mpn("B33671L6474K000") is None


def test_tdk_film_reports_value_disagreement():
    # 474 encodes 470 nF; declare it as the 47 nF it is not.
    findings = _decode_findings(_mismatch_part("B32671L6474K000", "C", 47e-9, 10.0))
    assert len(findings) == 1
    assert "470nF" in findings[0].detail and "47nF" in findings[0].detail


# --- Murata BLM / BLA chip ferrite beads (Part Numbering Guide) ------------


def test_murata_blm_decodes_true_positive():
    d = decode_mpn("BLM18AG121SN1D")
    assert d is not None and d.kind == "R"
    assert d.value == pytest.approx(120.0)  # impedance at 100 MHz
    # Murata's own worked example, not in this repo: BLM18AG102SN1D = 1000 ohm.
    d2 = decode_mpn("BLM18AG102SN1D")
    assert d2 is not None and d2.value == pytest.approx(1000.0)


def test_murata_blm_rejects_malformed():
    # Two-figure impedance code where the guide fixes three.
    assert decode_mpn("BLM18AG12SN1D") is None
    # 99 is not a published dimension code (03/15/18/2A/21/31/41).
    assert decode_mpn("BLM99AG121SN1D") is None
    # 7 is not a published circuit count (1 or 4).
    assert decode_mpn("BLM18AG121SN7D") is None


def test_murata_blm_reports_value_disagreement():
    findings = _decode_findings(_mismatch_part("BLM18AG121SN1D", "R", 600.0, None))
    assert len(findings) == 1
    assert "120ohm" in findings[0].detail and "600ohm" in findings[0].detail


def test_murata_blm_does_not_impose_a_resistor_eseries_rule():
    # A bead's impedance tolerance (typically +/-25 %) is not an IEC 60063
    # tolerance; the decoder must not push one into series_for_tolerance().
    d = decode_mpn("BLM18AG121SN1D")
    assert d is not None and d.tol_pct is None


# --- Nippon Chemi-Con 18-field aluminium electrolytic (CAT.No.E1001U) -----


def test_chemicon_decodes_true_positive():
    d = decode_mpn("EKMQ251VSN182MA50S")
    assert d is not None and d.kind == "C"
    assert d.value == pytest.approx(1800e-6)
    # Chemi-Con's own worked examples, neither of which is in this repo:
    # snap-in KMS 400 V 330 uF, and radial KMQ 450 V 100 uF.
    d2 = decode_mpn("EKMS401VSN331MR30S")
    assert d2 is not None and d2.value == pytest.approx(330e-6)
    d3 = decode_mpn("EKMQ451ELL101MM40S")
    assert d3 is not None and d3.value == pytest.approx(100e-6)


def test_chemicon_rejects_malformed():
    # X is not a published capacitance-tolerance code (M or V).
    assert decode_mpn("EKMQ251VSN182XA50S") is None
    # 17 characters: the scheme is a fixed 18-field code.
    assert decode_mpn("EKMQ251VSN182MA50") is None
    # Z is not a published category code for this decoder (A/H/E/B).
    assert decode_mpn("ZKMQ251VSN182MA50S") is None


def test_chemicon_reports_value_disagreement():
    # "182" encodes 1800 uF; declaring 3300 uF must be flagged.
    findings = _decode_findings(_mismatch_part("EKMQ251VSN182MA50S", "C", 3300e-6, None))
    assert len(findings) == 1
    assert "1800uF" in findings[0].detail and "3300uF" in findings[0].detail


def test_chemicon_electrolytic_does_not_get_a_resistor_eseries_rule():
    """1800 uF at code-M (+/-20 %) is a real catalogued Chemi-Con value whose
    1.8 mantissa is not in E6. If the decoder fed its tolerance letter into
    series_for_tolerance() the way a resistor family does, this genuine part
    would be reported as a non-standard value -- a false positive produced by
    applying a resistor concept to an electrolytic."""
    d = decode_mpn("EKMQ251VSN182MA50S")
    assert d is not None and d.tol_pct is None
    part = _mismatch_part("EKMQ251VSN182MA50S", "C", 1800e-6, None)
    assert analyze([part], allowlist=[]).new_violations == []


def test_chemicon_decoder_is_not_an_existence_check():
    """EKZE251ELL332MM40S is fabrication #1 from the 2026-07-27 audit: it
    existed at no distributor. It nonetheless decodes cleanly to the 3300 uF
    it was declared as, because its *encoding* was internally consistent.

    This test pins that limitation rather than hiding it: check 2 proves
    MPN/value consistency, never that the part is real. It is also the reason
    the Murata DE family is deliberately left unimplemented -- see
    test_murata_de_family_is_deliberately_unchecked."""
    d = decode_mpn("EKZE251ELL332MM40S")
    assert d is not None
    assert d.value == pytest.approx(3300e-6)
    part = _mismatch_part("EKZE251ELL332MM40S", "C", 3300e-6, None)
    assert analyze([part], allowlist=[]).new_violations == []


# --- WIMA FKP 1 pulse capacitors (FKP 1 datasheet, general-data tables) ----


def test_wima_fkp1_decodes_true_positive_against_a_part_not_in_this_repo():
    """FKP1Y022207E00MSSD is a real, distributor-stocked WIMA part that
    appears nowhere in elec/src: DigiKey 19131711 lists it as 0.022 uF /
    6000 VDC, body 17x29x41, matching WIMA's own 6000 VDC / 0.022 uF row
    (W 17, H 29, L 41.5, PCM 37.5). Decoding it correctly is evidence that
    this family's rule came from the manufacturer's tables and not from the
    string in this repo."""
    d = decode_mpn("FKP1Y022207E00MSSD")
    assert d is not None and d.kind == "C"
    assert d.value == pytest.approx(22e-9)
    assert "6000 VDC" in d.family
    # And WIMA's own listed 0.15 uF / 1600 VDC part -- the one the design
    # would need if 150 nF is the intended tank value.
    d2 = decode_mpn("FKP1T031507G00JSSD")
    assert d2 is not None and d2.value == pytest.approx(150e-9)
    assert "1600 VDC" in d2.family


def test_wima_fkp1_rejects_malformed():
    # Z is not one of the eight published rated-voltage letters.
    assert decode_mpn("FKP1Z021507E00JSSD") is None
    # Q is not a published tolerance code (M/K/J).
    assert decode_mpn("FKP1U021507E00QSSD") is None
    # 5 is not a published decade group (0...4).
    assert decode_mpn("FKP1U051507E00JSSD") is None


def test_wima_fkp1_flags_the_tank_capacitor_as_declared_in_this_repo():
    """The finding this branch exists to surface. FKP1U021507E00JSSD is
    decade group 2 + significant figures 150 = 150 x 10^2 pF = 0.015 uF, at
    rated-voltage letter U = 2000 VDC. elec/src/modules.ato declares c_tank1 /
    c_tank2 as 150 nF at 1600 V."""
    d = decode_mpn("FKP1U021507E00JSSD")
    assert d is not None
    assert d.value == pytest.approx(15e-9)
    assert "2000 VDC" in d.family
    findings = _decode_findings(_mismatch_part("FKP1U021507E00JSSD", "C", 150e-9, None))
    assert len(findings) == 1
    assert "15nF" in findings[0].detail and "150nF" in findings[0].detail


# --- Yageo RT thin film (RT series data sheet, ordering information) -------


def test_yageo_rt_decodes_true_positive():
    d = decode_mpn("RT0603BRD0716K9L")
    assert d is not None and d.kind == "R"
    assert d.value == pytest.approx(16900.0)
    assert d.tol_pct == 0.1  # tolerance code B
    d2 = decode_mpn("RT0603BRD07487KL")
    assert d2 is not None and d2.value == pytest.approx(487000.0)
    # Yageo's own ordering example, not in this repo: 56 ohm, +/-0.5 %, TC50.
    d3 = decode_mpn("RT0603DRE0756RL")
    assert d3 is not None and d3.value == pytest.approx(56.0)
    assert d3.tol_pct == 0.5


def test_yageo_rt_rejects_malformed():
    # X is not a published RT tolerance code (L/P/W/B/C/D/F). Note that L/P/W
    # are absent from the generic TOL_LETTER_PCT table, which is why this
    # family carries its own.
    assert decode_mpn("RT0603XRD0716K9L") is None
    # Missing the trailing default code L.
    assert decode_mpn("RT0603BRD0716K9") is None
    # Z is not a published TCR code (A...E).
    assert decode_mpn("RT0603BRZ0716K9L") is None


def test_yageo_rt_reports_value_disagreement():
    findings = _decode_findings(_mismatch_part("RT0603BRD0716K9L", "R", 169000.0, 0.1))
    assert len(findings) == 1
    assert "16.9kohm" in findings[0].detail and "169kohm" in findings[0].detail


def test_yageo_rt_non_standard_value_fails_eseries():
    # 16.85 kOhm is in no standard series; the RT family is a precision
    # resistor family, so its decoded 0.1 % tolerance correctly demands E192.
    part = _mismatch_part("RT0603BRD0716K85L", "R", 16850.0, None)
    kinds = {f.kind for f in analyze([part], allowlist=[]).new_violations}
    assert "eseries" in kinds


# --- Vishay VY1 ceramic disc safety capacitors (doc 28537 p.3) -------------


def test_vishay_vy1_decodes_true_positive():
    d = decode_mpn("VY1222M47Y5UQ6TV0")
    assert d is not None and d.kind == "C"
    assert d.value == pytest.approx(2200e-12)
    # Vishay's own ordering-code example, not in this repo: 100 pF Y5S.
    d2 = decode_mpn("VY1101K31Y5SQ6TV0")
    assert d2 is not None and d2.value == pytest.approx(100e-12)


def test_vishay_vy1_rejects_malformed():
    # Y9Z is not a published temperature coefficient (U2J/Y5S/Y5U/Y5V).
    assert decode_mpn("VY1222M47Y9ZQ6TV0") is None
    # J is not a published VY1 tolerance code (K = +/-10 %, M = +/-20 %).
    assert decode_mpn("VY1222J47Y5UQ6TV0") is None
    # 5 is not a published lead-spacing code (0 = 10.0 mm, X = 12.5 mm).
    assert decode_mpn("VY1222M47Y5UQ6TV5") is None


def test_vishay_vy1_reports_value_disagreement():
    # The Y-cap sits line-to-PE: a 1000x capacitance error here is the exact
    # shape of audit fabrication #2 (DE2E3KH221MA3B, "221" = 220 pF declared
    # as 220 nF).
    findings = _decode_findings(_mismatch_part("VY1222M47Y5UQ6TV0", "C", 2.2e-6, 20.0))
    assert len(findings) == 1
    assert "2.2nF" in findings[0].detail and "2.2uF" in findings[0].detail


# --- Vishay WSLP Power Metal Strip shunts (doc 30122 p.1) -----------------


def test_vishay_wslp_decodes_true_positive():
    d = decode_mpn("WSLP25122L000FEA")
    assert d is not None and d.kind == "R"
    assert d.value == pytest.approx(0.002)
    # Vishay's own two worked examples, neither of which is in this repo:
    # "4L000 = 0.004 Ohm" and "R0100 = 0.01 Ohm" / WSLP1206R0100FEA.
    d2 = decode_mpn("WSLP12064L000FEA")
    assert d2 is not None and d2.value == pytest.approx(0.004)
    d3 = decode_mpn("WSLP1206R0100FEA")
    assert d3 is not None and d3.value == pytest.approx(0.01)


def test_vishay_wslp_rejects_malformed():
    # Structurally well-formed, but the 5-character value field carries
    # neither the L (milliohm) nor the R (decimal) marker the datasheet
    # requires, so there is no published way to place the decimal point.
    assert decode_mpn("WSLP251220000FEA") is None
    assert classify_unchecked("WSLP251220000FEA")[0] == "Vishay WSLP shunt"
    # H is not a published tolerance code (D/F/G).
    assert decode_mpn("WSLP25122L000HEA") is None
    # 2520 is not a published global model size.
    assert decode_mpn("WSLP25202L000FEA") is None


def test_vishay_wslp_reports_value_disagreement():
    # A shunt that is 5 mOhm in the MPN but declared as 2 mOhm silently
    # rescales every overcurrent trip point derived from it.
    findings = _decode_findings(_mismatch_part("WSLP25125L000FEA", "R", 0.002, 1.0))
    assert len(findings) == 1
    assert "0.005ohm" in findings[0].detail and "0.002ohm" in findings[0].detail


def test_vishay_wslp_does_not_impose_a_resistor_eseries_rule():
    """WSLP2512's own catalogue values are 0.0005 / 0.001 / 0.002 / 0.005 /
    0.007 / 0.01 Ohm -- a milliohm shunt ladder, not an IEC 60063 series. The
    decoder must not push its tolerance letter into the E-series selector."""
    d = decode_mpn("WSLP25122L000FEA")
    assert d is not None and d.tol_pct is None


# --- Deliberately unimplemented families ----------------------------------


def test_murata_de_family_is_deliberately_unchecked():
    """DE1E3KX222MA4BA01 -- the Y-capacitor fabrication removed from the
    design on 2026-07-28 (docs/evidence/2026-07-28-suspect-mpn-verification.md)
    -- must remain UNCHECKED, and this is a deliberate choice, not an
    oversight.

    Murata's published scheme for this family (Cat.No.C85E-2, "Part
    Numbering", p.2) is complete and unambiguous, and running the fabrication
    through it yields a fully well-formed part: DE / 1 = IEC 60384-14 Class
    X1,Y1 / E3 / KX / 222 = 2200 pF / M = +/-20 % / A4 = vertical crimp long,
    10 mm lead spacing / B = bulk / A01 = individual specification code, which
    that document explicitly permits as a trailing three-digit alphanumeric.
    Its declared value, 2.2 nF, agrees with the 2200 pF it encodes.

    So an offline decoder built from the published scheme *cannot* reject this
    string -- the fabrication was established by catalogue absence (no Murata
    document pairs the A4B lead style with the A01 suffix; A4B pairs with N01F
    and A01 pairs with A5B), which is not an encoding property. Implementing
    the family would therefore move the one MPN known to be invented out of
    the honest UNCHECKED column and into "decoded, agrees" -- manufacturing
    confidence, which is strictly worse than leaving it unchecked.

    If this test ever fails because DE now decodes, the burden is on that
    change to show it rejects this exact string."""
    assert decode_mpn("DE1E3KX222MA4BA01") is None
    group, reason = classify_unchecked("DE1E3KX222MA4BA01")
    assert group == "DE"
    assert "unrecognised manufacturer-prefix family" in reason
    # Reported, never silently passed.
    part = _mismatch_part("DE1E3KX222MA4BA01", "C", 2.2e-9, 20.0)
    result = analyze([part], allowlist=[])
    assert result.unchecked_count == 1
    assert result.decoded_count == 0


def test_audit_fabrication_de2e3kh221ma3b_stays_unchecked():
    """Audit fabrication #2. It is unchecked for the same reason as above --
    the DE family is not implemented -- so its 1000x value error (Murata's
    "221" = 220 pF against a declared 220 nF) is NOT caught by check 2 here.
    That is the honest cost of the DE decision and is recorded rather than
    glossed: the part is long since removed from the design, and the
    E-series check is unaffected either way."""
    assert decode_mpn("DE2E3KH221MA3B") is None


def test_existing_families_still_decode_after_the_registry_refactor():
    """decode_mpn()/classify_unchecked() were rewritten to walk one shared
    FAMILIES registry; the pre-existing six families must be untouched."""
    assert decode_mpn("RC0603FR-0710KL").value == pytest.approx(10000.0)
    assert decode_mpn("RSF100JB-73-39R").value == pytest.approx(39.0)
    assert decode_mpn("CRCW0805100KFKEA").value == pytest.approx(100000.0)
    assert decode_mpn("CRGP2512F22K").value == pytest.approx(22000.0)
    assert decode_mpn("ERA-3AEB6192V").value == pytest.approx(61900.0)
    assert decode_mpn("C0603C104K5RACTU").value == pytest.approx(100e-9)


# ---------------------------------------------------------------------------
# Real-tree integration: the shipped gate walking elec/src/*.ato.
# ---------------------------------------------------------------------------


def _stdout_int_after(stdout: str, label: str) -> int:
    """Pull the leading integer off the gate's ``"<label>: <n> ..."`` line."""
    line = next(l for l in stdout.splitlines() if l.startswith(label))
    return int(line.split(":", 1)[1].split()[0])


def test_gate_flags_the_resonant_tank_capacitor_on_real_tree_today():
    """The shipped CLI must FAIL (exit 3) on today's tree, naming c_tank1 /
    c_tank2 (elec/src/modules.ato, ResonantTank) as a decode mismatch.

    History of this assertion, because it has now moved twice and each move
    has to be justifiable on its own evidence:

      1. Originally it pinned the gate failing on the case-4 fabrication
         (r_low_top / ERA-3AEB6132V, docs/evidence/2026-07-27-fabricated-mpn-
         audit.md).
      2. When that fabrication and the four others were fixed in source with
         cited distributor verification -- none of them allowlisted -- it was
         moved to pinning a clean exit 0, since asserting failure would then
         have been asserting a falsehood about the repo.
      3. It now pins failure again, because extending the decoder to the
         previously-UNCHECKED families surfaced a *new*, previously invisible
         defect. This is not a reversion to (1); it is the gate doing the job
         it was built for on a part it could not read before.

    The finding: `c_tank1.mpn = "FKP1U021507E00JSSD"` with
    `c_tank1.value = 150nF`. Decoded against WIMA's own FKP 1 ordering tables
    (https://www.wima.de/wp-content/uploads/media/e_WIMA_FKP_1.pdf, pages
    63-68), the string says decade group 2 + significant figures 150, i.e.
    150 x 10^2 pF = 0.015 uF -- ten times smaller than declared -- at rated
    voltage letter U = 2000 VDC, while the source declares 1600 V. WIMA's own
    row for 0.15 uF at 1600 VDC is FKP1T031507G.

    Deliberately NOT resolved here: fixing it means editing elec/src, which
    is a design change with a resonant-frequency consequence
    (f0 ~ 1/sqrt(LC): a 10x tank-capacitance error moves f0 by ~3.16x) and
    belongs to whoever owns the ResonantTank module -- and allowlisting it
    would be exactly the "pad the allowlist until CI is green" move that the
    allowlist file's own hand-curated-only header exists to prevent.

    So: if this test starts failing because the gate now exits 0, that means
    someone changed the design or the MPN -- check that the fix was verified
    against a distributor, then move this assertion back to a clean pass with
    that evidence cited. If it fails because a *different* part is reported,
    that is a new finding and must be investigated, not silenced.
    """
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 3, (
        f"expected the shipped gate to report violations (exit 3) on today's tree; "
        f"got {result.returncode}\n{result.stdout}\n{result.stderr}"
    )
    assert "NEW VIOLATIONS" in result.stdout
    assert "c_tank1" in result.stdout
    assert "c_tank2" in result.stdout
    assert "FKP1U021507E00JSSD" in result.stdout
    # The specific numbers, so a decoder regression that merely reports *a*
    # violation on this part cannot pass this test.
    assert "encodes 15nF" in result.stdout
    assert "declared value is 150nF" in result.stdout

    # ...and nothing else. A newly-broken decoder that flags half the BOM
    # must not slip through under cover of this expected finding.
    assert "=== NEW VIOLATIONS (2) ===" in result.stdout

    # Anti-vacuity: prove this walked the real tree and did real work, not
    # a hollow "0 files matched" run.
    assert _stdout_int_after(result.stdout, "Parts inspected") > 0
    assert _stdout_int_after(result.stdout, "MPNs decoded") > 0

    real_allowlist_entries = load_allowlist(REAL_ALLOWLIST)
    assert real_allowlist_entries, "expected the hand-curated allowlist to be non-empty"
    assert _stdout_int_after(result.stdout, "Allowlist entries loaded") == len(
        real_allowlist_entries
    )


def test_real_tree_has_no_unchecked_mpns_left():
    """Every MPN in elec/src/*.ato is now decodable against a cited
    manufacturer part-numbering document -- the point of the family
    extension. This is deliberately a *characterisation* of today's tree, not
    a rule: if a future part introduces a family the decoder has never been
    taught, this test failing is the intended prompt to go read that
    manufacturer's ordering-information table and teach it, NOT to relax the
    assertion. Unchecked has always been a legal (non-failing) state for the
    gate itself; this test just makes the regression visible."""
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    inspected = _stdout_int_after(result.stdout, "Parts inspected")
    decoded = _stdout_int_after(result.stdout, "MPNs decoded")
    unchecked = _stdout_int_after(result.stdout, "MPNs unchecked")
    assert unchecked == 0, f"{unchecked} MPN(s) still unchecked:\n{result.stdout}"
    assert decoded == inspected


def test_real_allowlist_parses_and_is_hand_curated_shape():
    entries = load_allowlist(REAL_ALLOWLIST)
    assert entries is not None, "committed allowlist must be valid YAML with required fields"
    assert len(entries) > 0
    for e in entries:
        assert e.reason.strip(), f"allowlist entry for {e.ref} has no reason"
        assert e.checks <= {"eseries", "decode"}
