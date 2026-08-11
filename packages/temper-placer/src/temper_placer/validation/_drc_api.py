"""
KiCad DRC runner — programmatic interface to kicad-cli DRC.

This module wraps kicad-cli to run Design Rule Checks on PCB files
and parse the results into structured data.

Extracted from drc_runner.py to break the ``regression -> validation``
import-cycle edge.  Both ``regression/`` and ``validation/drc_runner.py``
can import from here without creating a cycle because this module has
no dependencies on ``regression/`` or on the Rust/CheckRunner parts of
``drc_runner.py``.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


class DrcRunnerError(Exception):
    """Error running DRC."""

    pass


class DrcProjectContextError(DrcRunnerError):
    """``pcb_path`` has no resolvable sibling ``.kicad_pro`` project file.

    kicad-cli resolves a project by looking for ``<stem>.kicad_pro`` next to
    the board file it is asked to DRC. When that file is missing, kicad-cli
    does NOT error and does NOT fall back to some documented default -- it
    silently drops every violation category sourced from the project: the
    project's custom ``<stem>.kicad_dru`` rules (this repo's ``track_width``
    and, critically, ``creepage`` -- the IEC 60335-1 HV/LV isolation check)
    and the project's ``rule_severities`` overrides (``missing_courtyard``,
    ``annular_width``). Measured on this repo's board (2026-08-08, kicad-cli
    10.0.5): with project context, 1249 errors / 489 warnings; WITHOUT it,
    828 errors / 621 warnings -- creepage 187 -> 0, track_width 199 -> 0,
    annular_width 4 -> 0, missing_courtyard 5 -> 0, entirely absent from the
    report rather than reported as zero violations. See
    docs/evidence/2026-08-08-drc-power-token-jump-root-cause.md and
    docs/evidence/2026-08-08-drc-project-context-audit.md.

    A DRC measurement that can silently under-report a safety-critical
    category is a can't-fail gate with a fail-open bug. This project treats
    that as a defect, not a degraded-but-acceptable measurement -- so a
    missing/unresolvable project is a loud error here, never a quiet
    subset-of-the-truth result. If you are DRC'ing a scratch/temp copy of a
    board (a routed-output measurement, a mutated defect-corpus copy, ...),
    give it a resolvable project explicitly -- see
    ``copy_kicad_project_sidecar`` in this module -- rather than suppressing
    this error.
    """


def _kicad_project_path(pcb_path: Path) -> Path:
    """The ``.kicad_pro`` kicad-cli would resolve for *pcb_path* -- same
    stem, same directory, per KiCad's own project-file convention."""
    return pcb_path.with_suffix(".kicad_pro")


def ensure_resolvable_kicad_project(pcb_path: Path) -> None:
    """Raise :class:`DrcProjectContextError` if *pcb_path* has no sibling
    ``.kicad_pro`` kicad-cli can resolve.

    Every kicad-cli DRC invocation in this codebase must call this (directly
    or via :func:`run_drc`) before shelling out. See
    :class:`DrcProjectContextError` for why: without it, kicad-cli silently
    measures a strict subset of the real violations, with no warning.
    """
    project_path = _kicad_project_path(pcb_path)
    if not project_path.exists():
        raise DrcProjectContextError(
            f"No resolvable KiCad project for {pcb_path}: expected "
            f"{project_path} to exist alongside it. kicad-cli DRC without a "
            f"resolvable project silently drops the project's custom DRU "
            f"rules (track_width, creepage) and rule_severities overrides "
            f"(missing_courtyard, annular_width) -- entire categories "
            f"vanish from the report rather than reading zero. Refusing to "
            f"run a DRC measurement that can silently under-report a "
            f"safety-critical category (creepage is the IEC 60335-1 HV/LV "
            f"isolation check). If this is a scratch copy of a real board "
            f"(a routed-output measurement, a mutated defect-corpus copy, "
            f"...), call copy_kicad_project_sidecar(pcb_path, "
            f"source_board_path) to give it a resolvable project before "
            f"DRC'ing it."
        )


def copy_kicad_project_sidecar(pcb_path: Path, source_pcb_path: Path) -> None:
    """Give a scratch copy of a board a resolvable KiCad project, so DRC on
    it is not silently blind to the source project's custom rules.

    Copies ``<source_pcb_path.stem>.kicad_pro`` (and, if present,
    ``<source_pcb_path.stem>.kicad_dru``) from ``source_pcb_path``'s
    directory to ``<pcb_path.stem>.kicad_pro`` / ``.kicad_dru`` next to
    *pcb_path* -- i.e. renamed to match the scratch copy's own stem, which
    is what kicad-cli's project-resolution-by-filename-convention requires.

    This is the supported way to DRC a routed/mutated/otherwise-derived copy
    of a real board without tripping :func:`ensure_resolvable_kicad_project`
    -- NOT a way to suppress that check. Every caller that writes a board
    copy to measure with kicad-cli DRC should call this immediately after
    writing it.

    Raises:
        FileNotFoundError: if ``source_pcb_path`` has no ``.kicad_pro`` of
            its own -- there is nothing valid to propagate.
    """
    source_project = _kicad_project_path(source_pcb_path)
    if not source_project.exists():
        raise FileNotFoundError(
            f"source board {source_pcb_path} has no {source_project} to "
            f"propagate -- cannot give the copy a resolvable project"
        )
    dest_project = _kicad_project_path(pcb_path)
    shutil.copyfile(source_project, dest_project)

    source_dru = source_pcb_path.with_suffix(".kicad_dru")
    if source_dru.exists():
        shutil.copyfile(source_dru, pcb_path.with_suffix(".kicad_dru"))


@dataclass
class DrcError:
    """
    A DRC error.

    Attributes:
        rule: Rule that was violated (e.g., 'clearance', 'courtyard_overlap').
        severity: Severity level ('error', 'warning').
        location: (x, y) position in mm.
        message: Human-readable description.
        components: List of component references involved.
        nets: List of net names involved (from items with no owning
            component, e.g. bare copper tracks/vias -- KiCad embeds the
            net name in square brackets, e.g. "Via [GND] on F.Cu - B.Cu").
        items: Raw kicad-cli item descriptions, verbatim and in report
            order (e.g. "Pad 1 [I_SENSE] of C28 on F.Cu"). ``components``
            and ``nets`` are lossy summaries of these -- both are deduped,
            so a violation between two pads of ONE footprint collapses to a
            single-entry ``components`` list and the pad numbers are gone.
            The board-defect corpus asserts that a seeded pad short
            produces a violation naming BOTH mutated pads, which is only
            decidable from the raw descriptions.
    """

    rule: str
    severity: str
    location: tuple[float, float]
    message: str
    components: list[str] = field(default_factory=list)
    nets: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


@dataclass
class DrcWarning:
    """
    A DRC warning (same structure as DrcError).

    Attributes:
        rule: Rule that was violated.
        severity: Should be 'warning'.
        location: (x, y) position in mm.
        message: Human-readable description.
        components: List of component references involved.
        nets: List of net names involved (see DrcError.nets).
    """

    rule: str
    severity: str
    location: tuple[float, float]
    message: str
    components: list[str] = field(default_factory=list)
    nets: list[str] = field(default_factory=list)


@dataclass
class DrcResult:
    """
    Result of running DRC on a PCB file.

    Attributes:
        error_count: Total number of errors.
        warning_count: Total number of warnings.
        errors: List of DrcError objects.
        warnings: List of DrcWarning objects.
    """

    error_count: int
    warning_count: int
    errors: list[DrcError] = field(default_factory=list)
    warnings: list[DrcWarning] = field(default_factory=list)


def is_kicad_cli_available() -> bool:
    """
    Check if kicad-cli is available in PATH.

    Returns:
        True if kicad-cli is found, False otherwise.
    """
    return shutil.which("kicad-cli") is not None


def get_kicad_cli_version() -> str | None:
    """
    Return the running ``kicad-cli`` version string (e.g. ``"10.0.4"``),
    or ``None`` if the binary is unavailable or its version can't be read.

    This exists so a DRC ratchet result can compare "what actually measured
    this run" against a ceiling's recorded provenance -- kicad-cli's DRC
    engine changes behavior across versions (see
    docs/evidence/2026-07-27-drc-truth-gate-discrepancy.md), so silently
    measuring with a different binary than the one the ceiling was
    calibrated against is a real, previously-unflagged source of
    irreproducibility, not just a hypothetical one.
    """
    if not is_kicad_cli_available():
        return None
    try:
        result = subprocess.run(
            ["kicad-cli", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    version = result.stdout.strip()
    return version or None


# --- Determinism: pin KiCad's worker thread pool to a single thread ---------
#
# kicad-cli runs the DRC providers over a shared BS::thread_pool.  Several of
# them accumulate per-item state from whichever worker reaches an item first
# -- notably the connectivity search that builds copper clusters and the
# copper-clearance provider's checked-pair cache -- so the ORDER in which
# results land varies with thread scheduling, and on a byte-identical board
# the reported violation COUNT moves with it.  Measured on this repo's
# pcb/temper.kicad_pcb (macOS 15.5 arm64, kicad-cli 10.0.4, 120 samples --
# see docs/evidence/2026-08-04-drc-measurement-determinism.md):
#
#     default pool       clearance 377-378   shorting_items 199-200
#     MaximumThreads=1   clearance 378       shorting_items 199
#
# Wall time is unaffected (~4.8 s per run either way) -- the DRC is not
# thread-bound on this board.
#
# ``MaximumThreads`` is a KiCad "advanced config" key, readable only from a
# ``kicad_advanced`` file inside KiCad's per-user settings tree.  Rather than
# mutate the developer's real KiCad configuration -- ambient state that would
# make the measurement depend on who ran it -- we build a throwaway settings
# tree per invocation, seeded with a copy of the real one so library tables
# still resolve exactly as they otherwise would, and point KICAD_CONFIG_HOME
# at it for the lifetime of the subprocess.
#
# This does NOT make ``creepage`` deterministic, and it leaves a small
# residual set-level churn in ``clearance`` at a constant count.  Both have a
# different, upstream cause: KiCad dedupes reported pairs through containers
# keyed on raw BOARD_ITEM pointer values, so the dedup outcome follows the
# process's own allocation addresses and is redrawn every run.  No kicad-cli
# invocation reaches that; see the evidence doc and KiCad issue #20048.
#
# Set ``TEMPER_DRC_THREAD_PIN=0`` to disable the pin and reproduce the
# unpinned behaviour (this is what ``scripts/check_drc_determinism.py
# --inject-variance=unpin`` does).
_KICAD_ADVANCED_FILENAME = "kicad_advanced"
_MAX_THREADS_KEY = "MaximumThreads"


def _kicad_user_config_root() -> Path | None:
    """Root of KiCad's per-user settings tree (the directory holding the
    ``<major>.<minor>`` version folders), mirroring KiCad's own
    ``PATHS::calculateUserSettingsPath()``.  Returns None when the platform
    convention can't be resolved."""
    env_home = os.environ.get("KICAD_CONFIG_HOME")
    if env_home:
        return Path(env_home)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "kicad"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "kicad" if appdata else None
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "kicad"


def _kicad_settings_dirname() -> str | None:
    """The ``<major>.<minor>`` settings folder name for the running
    kicad-cli (e.g. ``"10.0"`` for 10.0.4), or None if unreadable."""
    version = get_kicad_cli_version()
    if not version:
        return None
    parts = version.strip().split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return f"{parts[0]}.{parts[1]}"


def _write_pinned_advanced_config(dest_dir: Path, existing: str) -> None:
    """Write ``kicad_advanced`` into ``dest_dir``, preserving any keys the
    real config already set and forcing ``MaximumThreads=1``."""
    kept = [
        line
        for line in existing.splitlines()
        if line.split("=", 1)[0].strip().casefold() != _MAX_THREADS_KEY.casefold()
    ]
    kept.append(f"{_MAX_THREADS_KEY}=1")
    (dest_dir / _KICAD_ADVANCED_FILENAME).write_text("\n".join(kept) + "\n", encoding="utf-8")


@contextlib.contextmanager
def _single_threaded_kicad_env() -> Iterator[dict[str, str] | None]:
    """Yield an environment mapping that pins kicad-cli's worker pool to one
    thread, or None to run with the ambient environment unchanged.

    Yielding None (rather than raising) is deliberate: an unreadable
    kicad-cli version or an unwritable temp dir should degrade to a
    *measurable but unpinned* DRC run, not to no measurement at all.  The
    determinism harness reports which mode it got.
    """
    if os.environ.get("TEMPER_DRC_THREAD_PIN") == "0":
        yield None
        return

    settings_dirname = _kicad_settings_dirname()
    if settings_dirname is None:
        yield None
        return

    try:
        with tempfile.TemporaryDirectory(prefix="temper-kicad-cfg-") as tmp_root:
            dest = Path(tmp_root) / settings_dirname
            dest.mkdir(parents=True)

            existing_advanced = ""
            src_root = _kicad_user_config_root()
            src = (src_root / settings_dirname) if src_root else None
            if src is not None and src.is_dir():
                # Top-level regular files only: that is where the library
                # tables and kicad_common.json live, so resolution is
                # unchanged, and it bounds the copy to a few tens of KB.
                for entry in sorted(src.iterdir()):
                    if not entry.is_file():
                        continue
                    if entry.name == _KICAD_ADVANCED_FILENAME:
                        with contextlib.suppress(OSError, UnicodeDecodeError):
                            existing_advanced = entry.read_text(encoding="utf-8")
                        continue
                    with contextlib.suppress(OSError):
                        shutil.copy2(entry, dest / entry.name)

            _write_pinned_advanced_config(dest, existing_advanced)

            env = dict(os.environ)
            env["KICAD_CONFIG_HOME"] = tmp_root
            yield env
    except OSError:
        yield None


def _get_drc_json_path(pcb_path: Path) -> Path:
    """
    Get the path where DRC JSON output will be written.

    This is a helper function that can be mocked in tests.
    """
    return pcb_path.parent / f"{pcb_path.stem}_drc_report.json"


# VERIFIED 2026-07-17: kicad-cli's DRC JSON violation items never carry a
# "reference" key -- the old code's `item.get("reference")` matched
# nothing on any observed violation type, not just courtyard ones, so
# `components` came back empty and `location` (which read a top-level
# "pos" that also never exists -- only per-item "pos" does) came back
# (0.0, 0.0) universally. The component ref is embedded in each item's
# free-text "description" string instead, in one of two shapes:
#   "Footprint D3"                              -> D3
#   "Reference field of C1"                     -> C1
#   "Segment of C16 on F.Silkscreen"             -> C16
#   "PTH pad 1 [+15V] of R1"                     -> R1
#   "Pad 13 [power_in.ntc-no] of K1 on F.Cu"     -> K1
# Some items are legitimately not owned by any single component (e.g.
# "Via [bias] on F.Cu - B.Cu", "Polygon on Edge.Cuts") -- these
# correctly yield no ref rather than a wrong guess. See
# docs/solutions/logic-errors/
# drc-api-wrapper-components-and-location-always-empty.md.
#
# Wave 4 entry-5 migration (port-inventory): the regex extraction and the
# per-violation aggregation below moved to the `temper_drc_rs`
# `validation_glue` kernels (`drc_extract_ref`, `drc_extract_net`,
# `drc_parse_violations`). The pre-migration bodies are pinned verbatim as
# the oracle in
# `tests/validation/test_validation_glue_rust_differential.py`. `run_drc`
# and the `DrcResult` shape are unchanged -- the shim marshals the
# kernel's parsed records into the untouched dataclasses.


def _extract_ref_from_item_description(description: str) -> str | None:
    """Extract a component reference designator from a DRC item's
    free-text description, or None if the item isn't owned by a single
    component (e.g. a via or a board-edge polygon).

    Wave 4 entry-5: the extraction runs in ``temper_drc_rs.drc_extract_ref``
    (``validation_glue.rs``); this is a delegation shim so the public name
    is unchanged.
    """
    import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

    return _tdrc.drc_extract_ref(description)


def _extract_net_from_item_description(description: str) -> str | None:
    """Extract a net name from a DRC item's free-text description, or
    None if it doesn't carry one. KiCad embeds net names in square
    brackets for net-owned items -- "Via [GND] on F.Cu - B.Cu",
    "Pad 2 [hb.gate_hs.driver-p2] of C22 on F.Cu" -- but not for
    board-level features like "Polygon on Edge.Cuts".

    Wave 4 entry-5: the extraction runs in ``temper_drc_rs.drc_extract_net``
    (``validation_glue.rs``); this is a delegation shim so the public name
    is unchanged.
    """
    import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

    return _tdrc.drc_extract_net(description)


def _parse_drc_json(json_path: Path) -> DrcResult:
    """
    Parse kicad-cli DRC JSON output.

    Args:
        json_path: Path to JSON report file.

    Returns:
        DrcResult with parsed errors and warnings.
    """
    with open(json_path) as f:
        data = json.load(f)

    # Wave 4 entry-5: the per-violation parsing/aggregation loop (ref/net
    # extraction, component/net dedup, the first-ref-position preference,
    # the severity bucket split) runs in ``temper_drc_rs.drc_parse_violations``.
    # This shim only marshals the parsed records into the unchanged
    # ``DrcError``/``DrcWarning`` dataclasses; the counts are the record-list
    # lengths, exactly as the pre-migration body computed them.
    import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

    error_records, warning_records = _tdrc.drc_parse_violations(data.get("violations", []))

    errors: list[DrcError] = []
    for r in error_records:
        errors.append(
            DrcError(
                rule=r["rule"],
                severity=r["severity"],
                location=r["location"],
                message=r["message"],
                components=r["components"],
                nets=r["nets"],
                items=r["items"],
            )
        )

    warnings: list[DrcWarning] = []
    for r in warning_records:
        warnings.append(
            DrcWarning(
                rule=r["rule"],
                severity=r["severity"],
                location=r["location"],
                message=r["message"],
                components=r["components"],
                nets=r["nets"],
            )
        )

    return DrcResult(
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
    )


def run_drc(pcb_path: Path) -> DrcResult:
    """
    Run KiCad DRC on a PCB file.

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        DrcResult with all errors and warnings.

    Raises:
        FileNotFoundError: If PCB file doesn't exist.
        DrcProjectContextError: If ``pcb_path`` has no resolvable sibling
            ``.kicad_pro`` -- see that class's docstring for why this is a
            hard failure rather than a degraded measurement.
        DrcRunnerError: If kicad-cli is not available or DRC fails.
    """
    pcb_path = Path(pcb_path)

    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    if not is_kicad_cli_available():
        raise DrcRunnerError(
            "kicad-cli is not available. Install KiCad 8+ and ensure kicad-cli is in PATH."
        )

    # Fail loud, not silent-and-wrong: see DrcProjectContextError. This must
    # run before the subprocess call below -- kicad-cli itself gives no
    # warning when it can't resolve a project, it just quietly measures
    # fewer categories.
    ensure_resolvable_kicad_project(pcb_path)

    # Get output path for JSON report
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json_path = Path(tmp.name)

    try:
        # Run kicad-cli DRC.
        #
        # --all-track-errors is load-bearing, for determinism as much as for
        # completeness. Without it KiCad reports only a SUBSET of the errors on
        # each track, and which subset it picks varies between runs on a
        # byte-identical board. Measured over 11 runs before adding it:
        #
        #     clearance       334 - 343      shorting_items  148 - 174
        #     tracks_crossing   2 -   3
        #
        # With it, shorting_items and tracks_crossing are stable across every
        # run and clearance varies by at most 1. The counts also rise --
        # clearance 337 -> 499, shorting_items ~160 -> 199 -- because the
        # earlier figures were a sample, not a measurement. 499 is the same
        # clearance count docs/STRATEGY.md independently records for this
        # board.
        #
        # A DRC number that moves on an unchanged board cannot be ratcheted:
        # any tight ceiling fails intermittently and gets written off as flake,
        # which is exactly how a removed placement capability stayed hidden
        # behind a "nondeterministic on CI runners" comment for months.
        #
        # The worker pool is pinned to one thread for the same reason (see
        # _single_threaded_kicad_env): with the default pool the *count*
        # itself moves run to run.
        with _single_threaded_kicad_env() as env:
            result = subprocess.run(
                [
                    "kicad-cli",
                    "pcb",
                    "drc",
                    "--all-track-errors",
                    "--format",
                    "json",
                    "--output",
                    str(json_path),
                    str(pcb_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )

        # kicad-cli returns 0 even with DRC errors (errors are in the report).
        # Any other status is an unavailable measurement, even if a stale or
        # partial JSON file happens to exist at the requested output path.
        if result.returncode != 0:
            raise DrcRunnerError(
                "kicad-cli DRC failed "
                f"(exit {result.returncode}). stdout: {result.stdout}, "
                f"stderr: {result.stderr}"
            )

        if not json_path.exists():
            raise DrcRunnerError(
                f"DRC did not produce output file. stdout: {result.stdout}, stderr: {result.stderr}"
            )

        return _parse_drc_json(json_path)

    except subprocess.TimeoutExpired as e:
        raise DrcRunnerError("DRC timed out after 60 seconds") from e
    except subprocess.SubprocessError as e:
        raise DrcRunnerError(f"Failed to run kicad-cli: {e}") from e
    finally:
        # Clean up JSON file
        if json_path.exists():
            with contextlib.suppress(OSError):
                json_path.unlink()
