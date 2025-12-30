import pytest
from pathlib import Path
from scripts.validate_footprints import validate_footprint_file, auto_fix_issue, FootprintIssue


@pytest.fixture
def temp_fp(tmp_path):
    """Helper to create a temporary footprint file."""
    def _create(name, content):
        fp_path = tmp_path / f"{name}.kicad_mod"
        fp_path.write_text(content)
        return fp_path
    return _create


def test_detects_negative_clearance(temp_fp):
    """Catches negative clearance values."""
    fp_path = temp_fp("TestNeg", '(module Test (pad 1 smd rect (at 0 0) (size 1 1) (clearance -0.5)))')
    issues = validate_footprint_file(fp_path)
    assert any(i.issue_type == "negative_clearance" for i in issues)
    assert any(i.severity == "error" for i in issues)


def test_detects_excessive_clearance(temp_fp):
    """Catches unusually large clearance values."""
    fp_path = temp_fp("TestLarge", '(module Test (clearance 10.0))')
    issues = validate_footprint_file(fp_path)
    assert any(i.issue_type == "excessive_clearance" for i in issues)
    assert any(i.severity == "warning" for i in issues)


def test_detects_missing_courtyard(temp_fp):
    """Catches missing courtyard definitions."""
    fp_path = temp_fp("TestNoCrtYd", '(module Test (layer F.Cu))')
    issues = validate_footprint_file(fp_path)
    assert any(i.issue_type == "missing_courtyard" for i in issues)


def test_detects_malformed_sexpr(temp_fp):
    """Catches unbalanced parentheses."""
    fp_path = temp_fp("TestMalformed", '(module Test (layer F.Cu)')
    issues = validate_footprint_file(fp_path)
    assert any(i.issue_type == "malformed_sexpr" for i in issues)


def test_auto_fix_negative_clearance(temp_fp):
    """Auto-fix replaces negative clearance with 0.2mm."""
    fp_path = temp_fp("TestFix", '(module Test (clearance -0.5))')
    issue = FootprintIssue(
        footprint="TestFix",
        severity="error",
        issue_type="negative_clearance",
        message="Negative clearance -0.5mm",
        fix_available=True
    )
    success = auto_fix_issue(fp_path, issue)
    assert success
    content = fp_path.read_text()
    assert "(clearance 0.2)" in content
    assert "(clearance -0.5)" not in content


def test_valid_footprint_passes(temp_fp):
    """A valid footprint with courtyard should have no issues."""
    content = """(footprint "TestValid"
  (layer "F.Cu")
  (fp_line (start -1 -1) (end 1 1) (layer "F.CrtYd") (width 0.05))
  (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask"))
)"""
    fp_path = temp_fp("TestValid", content)
    issues = validate_footprint_file(fp_path)
    # Filter out warnings if we only care about errors, but here we expect none
    assert len(issues) == 0
