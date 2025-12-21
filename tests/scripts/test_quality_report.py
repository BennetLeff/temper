
import subprocess
import json
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent.parent.parent / "packages" / "temper-placer" / "tests" / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"

def test_quality_report_basic():
    """Test quality report script with JSON output."""
    cmd = [
        "python3", "scripts/placement_quality_report.py",
        "--pcb", str(MINIMAL_PCB),
        "--json"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    
    data = json.loads(result.stdout)
    assert "placement_metrics" in data
    assert "quality_score" in data
    assert data["input_file"] == str(MINIMAL_PCB)

def test_quality_report_help():
    """Test help output."""
    result = subprocess.run(["python3", "scripts/placement_quality_report.py", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Generate unified placement quality report" in result.stdout
