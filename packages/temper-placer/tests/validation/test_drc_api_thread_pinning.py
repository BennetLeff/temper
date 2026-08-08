"""Tests for the single-thread pin that makes ``run_drc`` reproducible.

kicad-cli spreads the DRC providers across a shared worker pool, and several
of them accumulate per-item state from whichever worker reaches an item
first. On pcb/temper.kicad_pcb that moves the reported violation COUNT run to
run on a byte-identical board (measured, macOS 15 arm64 / kicad-cli 10.0.4,
120 samples: ``clearance`` 377-378 and ``shorting_items`` 199-200 unpinned,
both single-valued pinned). ``run_drc`` therefore points KICAD_CONFIG_HOME at
a throwaway settings tree carrying ``MaximumThreads=1``.

The load-bearing assertion here is the last one: that the pinned environment
actually reaches the subprocess. Everything else can be correct while the env
is silently dropped, and the failure mode is invisible -- the numbers just go
back to wobbling, which historically gets written off as CI flake.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from temper_placer.validation import _drc_api


@pytest.fixture
def fake_version(monkeypatch):
    def _set(version: str | None):
        monkeypatch.setattr(_drc_api, "get_kicad_cli_version", lambda: version)

    return _set


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("10.0.4", "10.0"),
        ("10.0.5", "10.0"),
        ("9.0.1", "9.0"),
        ("10.0", "10.0"),
        ("nightly", None),
        ("", None),
        (None, None),
    ],
)
def test_settings_dirname_tracks_the_running_binary(fake_version, version, expected):
    """The advanced-config file only takes effect inside the settings folder
    named for the running KiCad's major.minor -- so it must be derived from the
    binary, never hardcoded."""
    fake_version(version)
    assert _drc_api._kicad_settings_dirname() == expected


def test_advanced_config_preserves_other_keys_and_forces_the_pin(tmp_path):
    _drc_api._write_pinned_advanced_config(
        tmp_path, "DRCEpsilon=10\nMaximumThreads=8\nExtraFillMargin=1\n"
    )
    lines = (tmp_path / "kicad_advanced").read_text().splitlines()
    assert "DRCEpsilon=10" in lines
    assert "ExtraFillMargin=1" in lines
    assert "MaximumThreads=8" not in lines
    assert lines[-1] == "MaximumThreads=1"


def test_advanced_config_overrides_a_differently_cased_existing_key(tmp_path):
    _drc_api._write_pinned_advanced_config(tmp_path, "maximumthreads = 16\n")
    lines = (tmp_path / "kicad_advanced").read_text().splitlines()
    assert lines == ["MaximumThreads=1"]


def test_pinned_env_supplies_a_config_home_containing_the_pin(fake_version, tmp_path, monkeypatch):
    fake_version("10.0.4")
    real_config = tmp_path / "kicad"
    (real_config / "10.0").mkdir(parents=True)
    (real_config / "10.0" / "fp-lib-table").write_text("(fp_lib_table)")
    (real_config / "10.0" / "colors").mkdir()
    monkeypatch.setattr(_drc_api, "_kicad_user_config_root", lambda: real_config)

    with _drc_api._single_threaded_kicad_env() as env:
        assert env is not None
        settings = Path(env["KICAD_CONFIG_HOME"]) / "10.0"
        assert (settings / "kicad_advanced").read_text().strip() == "MaximumThreads=1"
        # Library tables are carried across, so pinning threads does not also
        # change how footprints resolve -- that would move lib_footprint_* counts.
        assert (settings / "fp-lib-table").read_text() == "(fp_lib_table)"
        sandbox = Path(env["KICAD_CONFIG_HOME"])

    assert not sandbox.exists(), "the throwaway settings tree must not outlive the run"


def test_the_real_kicad_config_is_never_written_to(fake_version, tmp_path, monkeypatch):
    """Writing the pin into the developer's own KiCad settings would make the
    measurement depend on who ran it, and would persist after the run."""
    fake_version("10.0.4")
    real_config = tmp_path / "kicad"
    (real_config / "10.0").mkdir(parents=True)
    monkeypatch.setattr(_drc_api, "_kicad_user_config_root", lambda: real_config)

    with _drc_api._single_threaded_kicad_env() as env:
        assert Path(env["KICAD_CONFIG_HOME"]) != real_config
    assert list((real_config / "10.0").iterdir()) == []


def test_unreadable_version_degrades_to_an_unpinned_measurement(fake_version):
    """A measurement that still happens (and is reported as unpinned) beats no
    measurement at all."""
    fake_version(None)
    with _drc_api._single_threaded_kicad_env() as env:
        assert env is None


def test_escape_hatch_disables_the_pin(fake_version, monkeypatch):
    fake_version("10.0.4")
    monkeypatch.setenv("TEMPER_DRC_THREAD_PIN", "0")
    with _drc_api._single_threaded_kicad_env() as env:
        assert env is None


def test_run_drc_passes_the_pinned_env_to_kicad_cli(tmp_path, monkeypatch):
    """Anti-vacuity: every other test above can pass while run_drc quietly
    forgets to hand the environment to the subprocess."""
    pcb = tmp_path / "board.kicad_pcb"
    pcb.write_text("(kicad_pcb)")
    # run_drc now hard-requires a resolvable sibling .kicad_pro (see
    # ensure_resolvable_kicad_project) -- this test exercises env plumbing,
    # not project resolution, so give it a minimal one.
    pcb.with_suffix(".kicad_pro").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_drc_api, "is_kicad_cli_available", lambda: True)
    monkeypatch.setattr(_drc_api, "get_kicad_cli_version", lambda: "10.0.4")
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        env = kwargs.get("env")
        seen["env"] = env
        # Read it HERE: the throwaway settings tree is deleted as soon as
        # run_drc returns, so the assertion has to happen while kicad-cli
        # would still be able to see the file.
        if env and "KICAD_CONFIG_HOME" in env:
            advanced = Path(env["KICAD_CONFIG_HOME"]) / "10.0" / "kicad_advanced"
            seen["advanced"] = advanced.read_text() if advanced.exists() else None
        output = Path(cmd[cmd.index("--output") + 1])
        output.write_text('{"violations": []}')
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(_drc_api.subprocess, "run", fake_run)

    result = _drc_api.run_drc(pcb)

    assert result.error_count == 0
    assert "--all-track-errors" in seen["cmd"]
    assert seen["env"] is not None, "run_drc dropped the pinned environment"
    assert seen["advanced"] is not None, "KICAD_CONFIG_HOME had no kicad_advanced in it"
    assert seen["advanced"].strip().endswith("MaximumThreads=1")
