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
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath


class DrcRunnerError(Exception):
    """Error running DRC."""

    pass


class DrcReportSchemaError(DrcRunnerError):
    """kicad-cli's DRC JSON carried a top-level key this parser does not
    know about.

    This exists because of a defect that survived the entire life of the
    project: :func:`_parse_drc_json` read exactly ONE of kicad-cli's
    top-level arrays (``violations``) and silently dropped the rest.  The
    dropped ``unconnected_items`` array holds **339 entries** on the
    committed board (``pcb/temper.kicad_pcb`` sha256 ``26981fea...``,
    kicad-cli 10.0.5) -- so every DRC number this project has ever recorded,
    including every ``power_pcb_dataset/drc_ceiling.json`` ceiling, was
    blind to connectivity failures on a board whose entire purpose is to be
    connected.  Nothing failed; the number was simply smaller than the
    truth, which is indistinguishable from a good result.

    A parser that reads *some* sections and drops the rest cannot be fixed
    once and stay fixed: the next kicad-cli release adds an array and the
    silence resumes.  So the key set is an explicit, committed registry
    (:data:`_VIOLATION_ARRAY_KEYS` / :data:`_METADATA_KEYS`) and an
    unrecognized key is a hard error rather than a shrug.  If kicad-cli
    grows a key, classify it deliberately -- violation-shaped arrays go in
    ``_VIOLATION_ARRAY_KEYS`` so they reach the ratchet, metadata goes in
    ``_METADATA_KEYS`` -- and record the measured count in the PR.  Do NOT
    make this pass by adding the key to ``_METADATA_KEYS`` without looking
    at what is inside it.
    """


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


_PROJECT_LOCAL_FOOTPRINT_URI_RE = re.compile(r'\(uri\s+"\$\{KIPRJMOD\}/([^"]+)"\)')
_FOOTPRINT_START_RE = re.compile(r'^\s*\(footprint\s+"', re.MULTILINE)


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


def ensure_complete_kicad_project(pcb_path: Path) -> None:
    """Require the project-local context needed for strict DRC evidence.

    The historical parsed API only requires a sibling ``.kicad_pro``.  A
    candidate evidence measurement also needs the generated rules and every
    project-local footprint library declared by ``fp-lib-table``; otherwise
    kicad-cli can silently produce a partial report.
    """
    ensure_resolvable_kicad_project(pcb_path)
    dru_path = pcb_path.with_suffix(".kicad_dru")
    if not dru_path.is_file():
        raise DrcProjectContextError(
            f"Incomplete KiCad project for {pcb_path}: missing generated DRU {dru_path}"
        )
    table_path = pcb_path.parent / "fp-lib-table"
    if not table_path.is_file():
        raise DrcProjectContextError(
            f"Incomplete KiCad project for {pcb_path}: missing sibling {table_path}"
        )
    try:
        table = table_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DrcProjectContextError(
            f"Incomplete KiCad project for {pcb_path}: cannot read {table_path}: {error}"
        ) from error
    missing: list[str] = []
    for relative in _PROJECT_LOCAL_FOOTPRINT_URI_RE.findall(table):
        library_path = _project_local_library_path(pcb_path.parent, relative)
        if not library_path.exists():
            missing.append(relative)
    if missing:
        raise DrcProjectContextError(
            f"Incomplete KiCad project for {pcb_path}: missing project-local "
            f"footprint libraries declared by fp-lib-table: {missing}"
        )


def _project_local_library_path(project_dir: Path, relative: str) -> Path:
    """Resolve a ``${KIPRJMOD}`` URI without permitting project escape."""
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or ".." in windows.parts
    ):
        raise DrcProjectContextError(
            "Unsafe project-local footprint library path in fp-lib-table: "
            f"{relative!r} escapes the KiCad project directory"
        )

    project_root = project_dir.resolve()
    candidate = (project_root / relative).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise DrcProjectContextError(
            "Unsafe project-local footprint library path in fp-lib-table: "
            f"{relative!r} escapes the KiCad project directory"
        ) from error
    return candidate


def copy_kicad_project_sidecar(pcb_path: Path, source_pcb_path: Path) -> None:
    """Give a scratch copy of a board a resolvable KiCad project, so DRC on
    it is not silently blind to the source project's custom rules.

    Copies the project, generated rules, and (when present) the sibling
    ``fp-lib-table`` plus its project-local ``${KIPRJMOD}`` libraries from
    ``source_pcb_path``'s directory to the scratch directory. The project
    and rules are renamed to match the scratch copy's own stem, which is
    what kicad-cli's project-resolution-by-filename convention requires.

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
    # Validate all project-local paths before copying any table or library.
    source_table = source_pcb_path.parent / "fp-lib-table"
    local_libraries: list[tuple[Path, Path]] = []
    if source_table.is_file():
        table = source_table.read_text(encoding="utf-8")
        for relative in _PROJECT_LOCAL_FOOTPRINT_URI_RE.findall(table):
            source_library = _project_local_library_path(source_pcb_path.parent, relative)
            destination_library = _project_local_library_path(pcb_path.parent, relative)
            local_libraries.append((source_library, destination_library))

    dest_project = _kicad_project_path(pcb_path)
    shutil.copyfile(source_project, dest_project)

    source_dru = source_pcb_path.with_suffix(".kicad_dru")
    if source_dru.exists():
        shutil.copyfile(source_dru, pcb_path.with_suffix(".kicad_dru"))

    # Strict candidate evidence also requires the project-local footprint
    # table and every ${KIPRJMOD} library it names. Global KiCad libraries
    # remain resolved through the seeded KICAD_CONFIG_HOME and need no copy.
    if source_table.is_file():
        destination_table = pcb_path.parent / "fp-lib-table"
        shutil.copyfile(source_table, destination_table)
        for source_library, destination_library in local_libraries:
            if source_library.is_dir():
                shutil.copytree(source_library, destination_library, dirs_exist_ok=True)
            elif source_library.is_file():
                destination_library.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_library, destination_library)


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
        ignored_checks: Keys of the DRC checks kicad-cli did NOT run for
            this report (its top-level ``ignored_checks`` array). An empty
            category in a report that ignored that category's check is
            "not measured", NOT "clean" -- carrying this through is what
            lets a consumer tell the two apart. Measured on this repo's
            board with kicad-cli 10.0.5: four checks are ignored
            (``track_not_centered_on_via``, ``tuning_profile_track_geometries``,
            ``footprint_filters_mismatch``, ``footprint_type_mismatch``).
        included_severities: The severities kicad-cli was asked to report
            (its top-level ``included_severities`` array, normally
            ``["error", "warning"]``). A report that excluded a severity
            is likewise not an all-clear for it.
    """

    error_count: int
    warning_count: int
    errors: list[DrcError] = field(default_factory=list)
    warnings: list[DrcWarning] = field(default_factory=list)
    ignored_checks: list[str] = field(default_factory=list)
    included_severities: list[str] = field(default_factory=list)


@dataclass
class DrcMeasurement:
    """One kicad-cli invocation in parsed and lossless forms.

    ``raw_report_bytes`` is the exact byte sequence emitted by kicad-cli,
    retained before the temporary report is removed. ``raw_report`` is the
    decoded convenience view for consumers that need to inspect included and
    excluded findings without reparsing. ``result`` remains the historical
    structured API.
    """

    result: DrcResult
    raw_report_bytes: bytes
    raw_report: dict
    thread_pinned: bool

    @property
    def raw_findings(self) -> list[dict]:
        """All violation-shaped arrays in the parser's canonical order."""
        return [
            finding for key in _VIOLATION_ARRAY_KEYS for finding in self.raw_report.get(key, [])
        ]


@dataclass
class DrcCountInfo:
    """A DRC violation count classified against KiCad's reporting caps.

    KiCad's DRC engine truncates per-category violation reports at
    ``ERROR_LIMIT`` (199) or ``EXTENDED_ERROR_LIMIT`` (499) —
    GUI list-widget constants inherited by kicad-cli
    (``pcbnew/drc/drc_engine.cpp``; see
    ``docs/evidence/2026-08-12-dru-rule-precedence.md`` sec 4). A count at
    exactly its category's cap is a **saturation floor** (the true count is
    ``>= count``), NOT a count. ``is_capped`` records that distinction;
    ``display`` renders it so a reader can never mistake a floor for a
    count.

    Per-category caps (the ``category`` parameter to
    :func:`drc_count_from_kicad` is load-bearing): ``clearance`` /
    ``unconnected_items`` cap at 499; ``creepage`` is empirically uncapped
    (its provider bypasses the limit — a 20 mm creepage rule reports 3,311);
    every other category caps at 199.
    """

    count: int
    is_capped: bool
    display: str

    @property
    def is_honest(self) -> bool:
        """True when this count is not saturated — it is the true count."""
        return not self.is_capped


def drc_count_from_kicad(count: int, category: str) -> DrcCountInfo:
    """Classify a raw kicad-cli DRC violation count against KiCad's
    per-category reporting caps.

    The classification kernel runs in ``temper_drc_rs.drc_count_from_kicad``
    (``drc_count.rs`` — the single source of truth for the cap table);
    this is a delegation shim following the same pattern as the
    validation-glue shims above.
    """
    import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

    raw_count, is_capped, display = _tdrc.drc_count_from_kicad(count, category)
    return DrcCountInfo(count=raw_count, is_capped=is_capped, display=display)


def classify_counts(counts: dict[str, int]) -> dict[str, DrcCountInfo]:
    """Classify a ``{rule: raw_count}`` dict (e.g. a
    ``violations_by_type``-style breakdown) against KiCad's reporting caps.

    Every value is passed through :func:`drc_count_from_kicad`, so a
    saturated category carries ``is_capped=True`` and a ``display`` string
    that reads as a floor — callers that would trust the raw number must
    first look at ``is_capped``. Categories that do not cap (``creepage``)
    are never flagged.
    """
    return {rule: drc_count_from_kicad(count, rule) for rule, count in counts.items()}


def drc_cap_for(category: str) -> int | None:
    """The reporting cap for a kicad-cli violation *type*, or None for
    categories known not to cap (e.g. ``creepage``). Mirrors
    ``scripts/measure_uncapped_drc.py::cap_for``, single-sourced in Rust.
    """
    import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

    return _tdrc.drc_cap_for(category)


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


# --- kicad-cli DRC JSON: the complete top-level key registry ---------------
#
# Audited 2026-08-19 against a real report from the committed board
# (pcb/temper.kicad_pcb sha256 26981fea..., kicad-cli 10.0.5,
# --all-track-errors, single-thread pin, pcb/temper.kicad_dru regenerated,
# pcb/fp-lib-table present).  kicad-cli emits EXACTLY these ten top-level
# keys, schema https://schemas.kicad.org/drc.v1.json:
#
#   key                    kind    on this board  consumed by this parser
#   ---------------------  ------  -------------  -----------------------
#   violations             array   776 entries    yes (always was)
#   unconnected_items      array   339 entries    yes -- ADDED 2026-08-19
#   schematic_parity       array   0 entries      yes -- ADDED 2026-08-19
#   ignored_checks         array   4 entries      yes -- ADDED 2026-08-19
#                                                 (surfaced on DrcResult)
#   included_severities    array   2 entries      yes -- ADDED 2026-08-19
#                                                 (surfaced on DrcResult)
#   $schema                scalar  -              recognized, not surfaced
#   coordinate_units       scalar  "mm"           recognized, not surfaced
#   date                   scalar  -              recognized, not surfaced
#   kicad_version          scalar  "10.0.5"       recognized, not surfaced
#   source                 scalar  -              recognized, not surfaced
#
# Until 2026-08-19 the parser read `violations` and nothing else, so 339
# real connectivity errors -- 47% of the board's true error count -- were
# invisible to every ratchet, every evidence document and every DRC
# comparison this project has ever produced.  See DrcReportSchemaError.
#
# ORDER IS PART OF THE CONTRACT.  `violations` first, then
# `unconnected_items`, matching the order already used by every OTHER
# reader of this JSON in the repo (`deterministic/feedback/drc_parser.py`,
# `placer/cp_sat/gates.py::_map_violation_type` call site, and
# `temper-drc-rs/src/violation_contracts.rs`'s `DrcReport`, whose docstring
# pins "the merged `violations` + `unconnected_items` parse in order").
# `_parse_drc_json` was the one reader that never got the merge.
#
# Entries in these arrays are structurally identical -- `{type, severity,
# description, items:[{description, pos:{x,y}, uuid}]}` -- so they go
# through the same kernel and land in the same severity buckets.  On this
# board all 339 `unconnected_items` carry `severity: "error"` and
# `type: "unconnected_items"`, a type that appears in NO other array, so
# merging cannot alter any pre-existing category's count.  That is asserted
# per-category, on real reports, in
# tests/validation/test_drc_json_top_level_keys.py.
#
# `schematic_parity` is empty in every report this repo produces, and NOT
# because the board is clean: `run_drc` does not pass kicad-cli's
# `--schematic-parity` flag, so the check never runs and the array is
# emitted empty regardless.  Reading it is therefore a no-op TODAY and a
# guard against the day someone adds the flag -- and `DrcResult` carries
# `ignored_checks` so "not measured" can never again be read as "clean".
_VIOLATION_ARRAY_KEYS: tuple[str, ...] = (
    "violations",
    "unconnected_items",
    "schematic_parity",
)

_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "$schema",
        "coordinate_units",
        "date",
        "kicad_version",
        "source",
        "ignored_checks",
        "included_severities",
    }
)

_KNOWN_TOP_LEVEL_KEYS: frozenset[str] = frozenset(_VIOLATION_ARRAY_KEYS) | _METADATA_KEYS


# kicad-cli renders a shorting_items violation's net pair in whichever order
# the connectivity search reached the two nets, so the SAME short reads as
# "(nets gnd and rtd_sense_p)" in one run and "(nets rtd_sense_p and gnd)" in
# the next.  AGENTS.md records this as a trap ("normalize before diffing or
# you will 'find' changes that are not there"); this is that normalization,
# committed rather than re-derived per session.
_NET_PAIR_RE = re.compile(r"\(nets (.+) and (.+)\)\Z")


def _normalize_violation_description(description: str) -> str:
    """Order-normalize the net pair kicad-cli renders in a shorting_items
    description, so the same physical short compares equal across runs."""
    match = _NET_PAIR_RE.search(description)
    if match is None:
        return description
    first, second = sorted((match.group(1), match.group(2)))
    return f"{description[: match.start()]}(nets {first} and {second})"


def drc_violation_key(violation: dict) -> tuple:
    """A stable, uuid-free identity for one raw kicad-cli DRC violation.

    **Use this, never the item ``uuid``, to diff violation SETS between two
    DRC runs.**  kicad-cli SYNTHESIZES item uuids for objects the board file
    does not name: ``pcb/temper.kicad_pcb`` carries exactly **10** ``(uuid
    ...)`` tokens of its own, while a single DRC report references **825**
    distinct item uuids -- and only **291** of those repeat across three
    consecutive runs of the byte-identical board.  Keying on uuid therefore
    manufactures nondeterminism out of a deterministic measurement.
    Measured on the committed board, three runs intersected:

        key                          stable   unstable
        ---------------------------  -------  --------
        violations, by uuid             310      1398
        violations, by (desc, x, y)     774         4
        unconnected_items, by uuid       49       870
        unconnected_items, by (d,x,y)   339         0

    i.e. a board whose per-category counts are identical across all three
    runs reads as almost entirely unstable under uuid keying, and as
    essentially fully stable under this key.

    The key is ``(type, normalized description, sorted((item description,
    x, y), ...))``.  Both normalizations are load-bearing on this board:

    * sorting the items absorbs the run-to-run item order inside a violation;
    * ``_normalize_violation_description`` sorts the net-name pair in the
      documented ``shorting_items`` swap ("nets A and B" vs "nets B and A")
      that AGENTS.md warns will otherwise make you "find" changes that are
      not there -- 39 of this board's 776 violations carry such a pair, and
      4 of them actually swap across three runs.

    With both applied, the committed board reads **776/776 violations and
    339/339 unconnected_items stable across three consecutive runs, zero
    unstable** -- i.e. fully deterministic.  Without the net-pair
    normalization it reads 774/4; keyed on uuid it reads 310/1398.  Same
    board, same three reports.
    """
    items = tuple(
        sorted(
            (
                item.get("description", ""),
                item.get("pos", {}).get("x"),
                item.get("pos", {}).get("y"),
            )
            for item in violation.get("items", [])
        )
    )
    return (
        violation.get("type", "unknown"),
        _normalize_violation_description(violation.get("description", "")),
        items,
    )


def _parse_drc_report(data: dict, json_path: Path) -> DrcResult:
    """Parse an already-decoded kicad-cli DRC report.

    Reads EVERY violation-shaped top-level array kicad-cli emits -- see the
    key registry above -- not just ``violations``.  Raises
    :class:`DrcReportSchemaError` on an unrecognized top-level key rather
    than dropping it silently.

    Args:
        data: Decoded JSON report.
        json_path: Path to JSON report file, used in diagnostics.

    Returns:
        DrcResult with parsed errors and warnings.

    Raises:
        DrcReportSchemaError: If the report carries a top-level key that is
            in neither ``_VIOLATION_ARRAY_KEYS`` nor ``_METADATA_KEYS`` --
            i.e. a section this parser would otherwise silently drop.
    """
    unknown = sorted(set(data) - _KNOWN_TOP_LEVEL_KEYS)
    if unknown:
        raise DrcReportSchemaError(
            f"{json_path}: kicad-cli DRC JSON carries top-level key(s) this "
            f"parser does not recognize: {unknown}. Refusing to parse a "
            f"report with sections that would be silently dropped -- that is "
            f"exactly the defect that hid 339 unconnected_items from every "
            f"DRC ratchet this project has ever recorded. Classify each key "
            f"deliberately in _drc_api's top-level key registry: "
            f"violation-shaped arrays belong in _VIOLATION_ARRAY_KEYS so they "
            f"reach the ratchet, metadata belongs in _METADATA_KEYS. Record "
            f"the measured count of any new array in the PR."
        )

    # Wave 4 entry-5: the per-violation parsing/aggregation loop (ref/net
    # extraction, component/net dedup, the first-ref-position preference,
    # the severity bucket split) runs in ``temper_drc_rs.drc_parse_violations``.
    # This shim only marshals the parsed records into the unchanged
    # ``DrcError``/``DrcWarning`` dataclasses; the counts are the record-list
    # lengths, exactly as the pre-migration body computed them.
    import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

    raw_violations: list = []
    for key in _VIOLATION_ARRAY_KEYS:
        raw_violations.extend(data.get(key, []))

    error_records, warning_records = _tdrc.drc_parse_violations(raw_violations)

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
        # Metadata arrays: not violations, but not droppable either -- an
        # ignored check reports an EMPTY category, indistinguishable from a
        # clean one unless the consumer can see it was never run.
        ignored_checks=[
            c.get("key", "") if isinstance(c, dict) else str(c)
            for c in data.get("ignored_checks", [])
        ],
        included_severities=list(data.get("included_severities", [])),
    )


def _parse_drc_json(json_path: Path) -> DrcResult:
    """Parse a kicad-cli DRC JSON file while preserving legacy callers."""
    raw_report_bytes = json_path.read_bytes()
    return _parse_drc_report(json.loads(raw_report_bytes), json_path)


def _reject_footprint_resolution_failure(pcb_path: Path, raw_report: dict) -> None:
    """Reject the all-footprints-unresolved kicad-cli report signature."""
    try:
        board_text = pcb_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DrcProjectContextError(
            f"Cannot census footprints in measured subject {pcb_path}: {error}"
        ) from error
    footprint_count = len(_FOOTPRINT_START_RE.findall(board_text))
    by_type = {"lib_footprint_issues": 0, "lib_footprint_mismatch": 0}
    for key in _VIOLATION_ARRAY_KEYS:
        for finding in raw_report.get(key, []):
            category = finding.get("type")
            if category in by_type:
                by_type[category] += 1
    if (
        footprint_count > 0
        and by_type["lib_footprint_issues"] == footprint_count
        and by_type["lib_footprint_mismatch"] == 0
    ):
        raise DrcProjectContextError(
            "KiCad footprint resolution failure for "
            f"{pcb_path}: lib_footprint_issues={footprint_count} equals the "
            "subject footprint census while lib_footprint_mismatch=0. "
            "Refusing to treat unresolved libraries as a DRC measurement."
        )


def run_drc_measurement(pcb_path: Path, *, strict: bool = True) -> DrcMeasurement:
    """Run one DRC measurement and retain raw and parsed report forms.

    Strict measurements are the candidate-evidence path: they require the
    complete project-local context, a pinned KiCad worker pool, and request
    all track errors, all severities, and zone refill.  ``strict=False`` is
    retained for the historical :func:`run_drc` wrapper and deliberately
    keeps its project guard and invocation behavior.

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        A :class:`DrcMeasurement` backed by one kicad-cli invocation.

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
    if strict:
        ensure_complete_kicad_project(pcb_path)
    else:
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
            if strict and env is None:
                raise DrcRunnerError(
                    "Strict DRC measurement requires the single-thread KiCad "
                    "configuration; ambient/unpinned fallback is not evidence."
                )
            command = [
                "kicad-cli",
                "pcb",
                "drc",
                "--all-track-errors",
            ]
            if strict:
                command.extend(("--severity-all", "--refill-zones"))
            command.extend(
                (
                    "--format",
                    "json",
                    "--output",
                    str(json_path),
                    str(pcb_path),
                )
            )
            result = subprocess.run(
                command,
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

        try:
            raw_report_bytes = json_path.read_bytes()
        except FileNotFoundError as error:
            raise DrcRunnerError(
                f"DRC did not produce output file. stdout: {result.stdout}, stderr: {result.stderr}"
            ) from error

        try:
            raw_report = json.loads(raw_report_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DrcReportSchemaError(
                f"Cannot retain raw kicad-cli DRC report {json_path}: {error}"
            ) from error
        # Derive parsed records from the exact byte buffer retained below;
        # the legacy path-based parser remains available for existing users.
        parsed = _parse_drc_report(raw_report, json_path)
        if strict:
            _reject_footprint_resolution_failure(pcb_path, raw_report)
        return DrcMeasurement(
            result=parsed,
            raw_report_bytes=raw_report_bytes,
            raw_report=raw_report,
            thread_pinned=env is not None,
        )

    except subprocess.TimeoutExpired as e:
        raise DrcRunnerError("DRC timed out after 60 seconds") from e
    except subprocess.SubprocessError as e:
        raise DrcRunnerError(f"Failed to run kicad-cli: {e}") from e
    finally:
        # Clean up JSON file
        with contextlib.suppress(FileNotFoundError, OSError):
            json_path.unlink()


def run_drc(pcb_path: Path) -> DrcResult:
    """Run KiCad DRC with the historical parsed-result compatibility shape."""
    return run_drc_measurement(pcb_path, strict=False).result
