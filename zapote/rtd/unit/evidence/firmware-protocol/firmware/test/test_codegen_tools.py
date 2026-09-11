"""
Unit tests for firmware codegen tools.

Tests verify that gen_config.py, gen_fault_list.py, and gen_transition_table.py
run without error, produce deterministic output, and generate correct header content.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GEN_CONFIG = REPO_ROOT / "firmware" / "tools" / "gen_config.py"
GEN_FAULT_LIST = REPO_ROOT / "firmware" / "tools" / "gen_fault_list.py"
GEN_TRANSITION_TABLE = REPO_ROOT / "firmware" / "tools" / "gen_transition_table.py"


def _run_tool(script: Path) -> subprocess.CompletedProcess:
    """Run a codegen script and return the completed process."""
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# gen_config.py
# ---------------------------------------------------------------------------

class TestGenConfig:
    """Tests for firmware/tools/gen_config.py."""

    OUTPUT = REPO_ROOT / "firmware" / "config.h"

    def test_runs_without_error(self):
        """gen_config.py exits 0 and produces output file."""
        result = _run_tool(GEN_CONFIG)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert self.OUTPUT.exists()

    def test_output_not_empty(self):
        """Generated config.h is not empty."""
        content = self.OUTPUT.read_text()
        assert len(content) > 100

    def test_header_guard_present(self):
        """config.h contains #ifndef CONFIG_H guard."""
        content = self.OUTPUT.read_text()
        assert "#ifndef CONFIG_H" in content
        assert "#define CONFIG_H" in content
        assert "#endif /* CONFIG_H */" in content

    def test_contains_expected_patterns(self):
        """config.h contains key structural elements."""
        content = self.OUTPUT.read_text()
        assert "typedef struct" in content
        assert "config_t" in content
        assert "void config_init(void);" in content
        assert "DO NOT EDIT" in content

    def test_deterministic(self):
        """Running gen_config.py twice produces identical output."""
        content1 = self.OUTPUT.read_text()
        result = _run_tool(GEN_CONFIG)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content2 = self.OUTPUT.read_text()
        assert content1 == content2, "output changed on second run"


# ---------------------------------------------------------------------------
# gen_fault_list.py
# ---------------------------------------------------------------------------

class TestGenFaultList:
    """Tests for firmware/tools/gen_fault_list.py."""

    OUTPUT = REPO_ROOT / "firmware" / "main" / "fault_list_generated.h"

    def test_runs_without_error(self):
        """gen_fault_list.py exits 0 and produces output file."""
        result = _run_tool(GEN_FAULT_LIST)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert self.OUTPUT.exists()

    def test_output_not_empty(self):
        """Generated fault_list_generated.h is not empty."""
        content = self.OUTPUT.read_text()
        assert len(content) > 50

    def test_contains_fault_list_macro(self):
        """fault_list_generated.h contains FAULT_LIST(X) macro."""
        content = self.OUTPUT.read_text()
        assert "#define FAULT_LIST(X)" in content
        assert "FAULT_NONE" in content

    def test_contains_expected_fault_codes(self):
        """Generated file includes known fault codes from both manifest and supplemental sources."""
        content = self.OUTPUT.read_text()
        # From manifest.json (labelified)
        assert "FAULT_OVER_TEMP" in content
        assert "FAULT_OVER_CURRENT" in content
        assert "FAULT_THERMAL_RUNAWAY" in content
        # From supplemental
        assert "FAULT_NONE" in content
        assert "FAULT_WATCHDOG_RESET" in content

    def test_fault_count_in_comment(self):
        """The trailing comment mentions total entry count."""
        content = self.OUTPUT.read_text()
        assert "14 total entries" in content

    def test_deterministic(self):
        """Running gen_fault_list.py twice produces identical output."""
        content1 = self.OUTPUT.read_text()
        result = _run_tool(GEN_FAULT_LIST)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content2 = self.OUTPUT.read_text()
        assert content1 == content2, "output changed on second run"


# ---------------------------------------------------------------------------
# gen_transition_table.py
# ---------------------------------------------------------------------------

class TestGenTransitionTable:
    """Tests for firmware/tools/gen_transition_table.py."""

    OUTPUT = REPO_ROOT / "firmware" / "main" / "transition_table.h"

    # Expected values derived from transition_table.yaml and state_machine.h:
    #   9 states (STATE_INIT..STATE_RUNAWAY_FAULT)
    #  23 events (EVENT_SELFTEST_PASS..EVENT_FAULT_RESET_PERSISTS)
    #  32 declared transitions in the YAML
    STATE_COUNT = 9
    EVENT_COUNT = 23
    TRANSITION_COUNT = 32

    def test_runs_without_error(self):
        """gen_transition_table.py exits 0 and produces output file."""
        result = _run_tool(GEN_TRANSITION_TABLE)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert self.OUTPUT.exists()

    def test_output_not_empty(self):
        """Generated transition_table.h is not empty."""
        content = self.OUTPUT.read_text()
        assert len(content) > 500

    def test_header_guard_present(self):
        """transition_table.h contains #ifndef guard."""
        content = self.OUTPUT.read_text()
        assert "#ifndef TRANSITION_TABLE_H" in content
        assert "#define TRANSITION_TABLE_H" in content
        assert "#endif /* TRANSITION_TABLE_H */" in content

    def test_contains_transition_table_array(self):
        """Output defines transition_table and transition_fault arrays."""
        content = self.OUTPUT.read_text()
        assert "transition_table[STATE_COUNT][EVENT_COUNT]" in content
        assert "transition_fault[STATE_COUNT][EVENT_COUNT]" in content
        assert "TRANSITION_INVALID" in content

    def test_transition_count_matches_manifest(self):
        """The number of valid (non-INVALID) transition cells equals the YAML row count."""
        content = self.OUTPUT.read_text()
        # Each valid transition is of the form  [EVENT_X] = STATE_Y,
        # while invalid cells are  [EVENT_X] = TRANSITION_INVALID,
        # The regex ensures we match only transition-cell forms (not _Static_assert
        # lines like "== STATE_COUNT * ..." which would false-match on count("= STATE_")).
        valid_count = len(re.findall(r'= STATE_\w+,', content))
        assert valid_count == self.TRANSITION_COUNT, (
            f"Expected {self.TRANSITION_COUNT} valid transitions, found {valid_count}"
        )

    def test_state_coverage(self):
        """Every state appears as a designated initializer in the array."""
        content = self.OUTPUT.read_text()
        states = [
            "STATE_INIT", "STATE_IDLE", "STATE_PAN_DET", "STATE_PREHEAT",
            "STATE_HEATING", "STATE_NO_PAN", "STATE_COOLDOWN",
            "STATE_FAULT", "STATE_RUNAWAY_FAULT",
        ]
        for state in states:
            assert f"[{state}]" in content, f"Missing state {state}"

    def test_event_coverage(self):
        """Every event appears at least once."""
        content = self.OUTPUT.read_text()
        events = [
            "EVENT_SELFTEST_PASS", "EVENT_SELFTEST_FAIL",
            "EVENT_START_BUTTON", "EVENT_PAN_DETECTED",
            "EVENT_PAN_TIMEOUT", "EVENT_NEAR_TARGET",
            "EVENT_PREHEAT_TIMEOUT", "EVENT_OVER_TEMP",
            "EVENT_OVER_CURRENT", "EVENT_FAN_FAILURE",
            "EVENT_PROBE_OPEN", "EVENT_PROBE_SHORT",
            "EVENT_THERMAL_RUNAWAY", "EVENT_PAN_REMOVED",
            "EVENT_STOP_BUTTON", "EVENT_TIMER_EXPIRED",
            "EVENT_PAN_REPLACED_SAME", "EVENT_PAN_REPLACED_DIFFERENT",
            "EVENT_NO_PAN_TIMEOUT", "EVENT_COOLED_DOWN",
            "EVENT_COOLDOWN_OVERHEAT", "EVENT_FAULT_RESET_CLEARED",
            "EVENT_FAULT_RESET_PERSISTS",
        ]
        for event in events:
            assert f"[{event}]" in content, f"Missing event {event}"

    def test_static_asserts_present(self):
        """Output includes compile-time size guards."""
        content = self.OUTPUT.read_text()
        assert "_Static_assert" in content
        assert "STATE_COUNT * EVENT_COUNT" in content

    def test_deterministic(self):
        """Running gen_transition_table.py twice produces identical output."""
        content1 = self.OUTPUT.read_text()
        result = _run_tool(GEN_TRANSITION_TABLE)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content2 = self.OUTPUT.read_text()
        assert content1 == content2, "output changed on second run"
