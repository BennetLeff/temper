#!/usr/bin/env python3
"""Fail closed when two different Rust functions register the same
Python-visible pyo3 name into the same `#[pymodule]`.

WHY THIS EXISTS
----------------
2026-08-13: `temper-geometry` had TWO independent `#[pyfunction] pub fn
kw_boundary_match_py` definitions -- one in `via_clearance.rs`, one in
`trace_width_assignment.rs` -- both `wrap_pyfunction!`'d into the same
`temper_geometry` pymodule from `lib.rs`'s `#[pymodule] fn temper_geometry`.
pyo3's `PyModule::add_function` is a plain attribute `setattr`: it does not
raise, warn, or even print, when a name is bound twice. The LATER
`register()` call in the `#[pymodule]` body silently wins; whichever module's
implementation registered first became permanently unreachable dead code
with its own passing unit tests -- a false-confidence trap, not a caught
bug. This class is invisible to every other gate in this repo:

  - It compiles clean (`cargo build`).
  - It links clean (`cargo test`, `maturin develop`).
  - `scripts/check_stale_extensions.py` certifies the .so is *fresh*, not
    that its exported names are each backed by exactly one implementation.
  - `scripts/check_unwired_kernels.py` (a different, complementary gate)
    positively CANNOT catch this: its `registered_symbols()` scan calls
    `dict.setdefault()` when recording `python name -> defining file`, which
    means it silently keeps whichever registration it happens to see first
    and never even notices the second one exists. It answers "is this name
    called from Python at all", not "is this name backed by more than one
    implementation" -- an orthogonal question this gate exists to answer.
  - Every differential/unit test for either implementation still passes,
    because each test calls the SAME shadowed name and gets whichever
    implementation currently wins -- it cannot tell you a second one is
    sitting there unreachable.

See docs/evidence/2026-08-13-pyo3-duplicate-registration-kw-boundary-match.md
for the incident this gate closes.

WHAT COUNTS AS A DUPLICATE REGISTRATION
----------------------------------------
Per crate, starting from its `#[pymodule] fn NAME(m: &Bound<'_, PyModule>)`
entry point (there are exactly 10 across this repo's pyo3/maturin crates,
mirroring `check_stale_extensions.py --list-crates`'s own crate census),
this gate follows every `<path>::register(m)` call transitively (a
`register()` function that itself calls a further `other::register(m)` is
followed too, to any depth) and collects every `wrap_pyfunction!(NAME, m)`
and `add_class::<NAME>(...)` reachable from that one pymodule. Rust-name ->
Python-visible-name renames (`#[pyo3(name = "...")]`, `#[pyfunction(name =
"...")]`, `#[pyclass(name = "...")]`) are resolved first, exactly like
`check_unwired_kernels.py` does, so a legitimate rename is never mistaken
for a second implementation of the same symbol.

A Python-visible name registered from more than one distinct
`(file, line)` site within the SAME pymodule's reachable set is a
DUPLICATE_REGISTRATION. The same name reused across two DIFFERENT crates'
pymodules (e.g. `temper_geometry.foo_py` and `temper_thermal.foo_py`) is
NOT a violation -- those are different Python top-level modules and cannot
collide at runtime.

EXIT CODES
    0  every discovered pymodule's reachable registrations are name-unique
    3  VIOLATION: at least one duplicate registration found
    5  GATE ERROR: the scan could not run a trustworthy check (zero
       `#[pymodule]` entry points found, or zero registrations found under
       any of them -- a gate that inspects nothing must not report clean)

USAGE
    uv run python scripts/check_pyo3_duplicate_registration.py
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_stale_extensions import discover_crates as _discover_pyo3_crates  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# Mirrors check_unwired_kernels.py's own regexes (consistency: this is the
# second gate that needs to parse the same registration/rename surface).
ADD_FUNCTION = re.compile(
    r"wrap_pyfunction!\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)"
)
ADD_CLASS = re.compile(
    r"add_class::<\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)"
)
PYO3_NAME = re.compile(r'#\[pyo3\([^)]*name\s*=\s*"([^"]+)"')
PYCLASS_NAME = re.compile(r'#\[pyclass\([^)]*name\s*=\s*"([^"]+)"')
PYFUNCTION_NAME = re.compile(r'#\[pyfunction\([^)]*name\s*=\s*"([^"]+)"')

PYMODULE_FN = re.compile(r"#\[pymodule\]\s*(?:\n\s*)*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)")
REGISTER_CALL = re.compile(
    r"(?<!fn\s)(?:crate::)?((?:[A-Za-z_][A-Za-z0-9_]*::)*[A-Za-z_][A-Za-z0-9_]*)::register\(\s*m\b"
)
REGISTER_FN_DEF = re.compile(r"(?:pub\s+)?fn\s+register\s*\(")


@dataclass
class RegSite:
    python_name: str
    rust_name: str
    file: str  # repo-relative
    line: int


@dataclass
class PymoduleUnit:
    crate: str
    entry_file: str
    entry_fn: str
    sites: list[RegSite] = field(default_factory=list)


class GateError(Exception):
    pass


def _logical_lines(text: str) -> list[str]:
    """Merge multi-line `#[...]` attributes into one logical line each."""
    out: list[str] = []
    buf = ""
    for line in text.splitlines():
        s = line.strip()
        if buf:
            buf += " " + s
            if line.rstrip().endswith("]"):
                out.append(buf)
                buf = ""
        elif s.startswith("#[") and not line.rstrip().endswith("]"):
            buf = s
        else:
            out.append(line)
    if buf:
        out.append(buf)
    return out


def _declared_idents_for(text: str) -> dict[str, str]:
    """Every struct/enum/fn DECLARED in one file's text, mapped to its
    Python-visible name: the `#[pyclass(name=...)]`/`#[pyo3(name=...)]`/
    `#[pyfunction(name=...)]` rename if present, else the bare Rust
    identifier itself (an explicit identity entry, not merely "absent").

    This is deliberately a super-set of what a "renames" dict would hold:
    an item declared WITHOUT a rename must still shadow a same-named,
    DIFFERENTLY renamed item declared in another file when both are
    resolved from a call site in THIS file -- two distinct Rust types
    named `ConstraintSet` in different modules, only one of which carries
    `#[pyclass(name = "TypedConstraintSet")]`, are not the same symbol, and
    a rename computed by merging bare identifiers repo-wide (as
    `check_unwired_kernels.py` deliberately does, for a different,
    complementary reason -- see its own module doc) would wrongly treat
    them as one, producing a false DUPLICATE_REGISTRATION between two
    genuinely different classes that merely share a local Rust name.
    """
    declared: dict[str, str] = {}
    pending: str | None = None
    for line in _logical_lines(text):
        s = line.strip()
        hit = PYCLASS_NAME.search(s) or PYFUNCTION_NAME.search(s) or PYO3_NAME.search(s)
        if hit:
            pending = hit.group(1)
            continue
        m = re.match(r"(?:pub\s+)?(?:unsafe\s+)?(?:struct|enum|fn)\s+([A-Za-z_][A-Za-z0-9_]*)", s)
        if m:
            declared[m.group(1)] = pending if pending else m.group(1)
            pending = None
        elif s and not s.startswith(("#[", "//", "///")):
            pending = None
    return declared


def _extract_braced_body(text: str, open_brace_idx: int) -> str:
    """Return the `{ ... }` body starting at `open_brace_idx` (which must be
    the index of the opening `{`), matched by depth, ignoring braces inside
    string/char literals or comments only to the (small) extent this
    codebase's registration sites need -- these are plain fn bodies, not
    macro-generated braces, so a naive counter is sufficient in practice and
    is what `check_unwired_kernels.py`'s own sibling scans rely on too.
    """
    depth = 0
    i = open_brace_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_idx : i + 1]
        i += 1
    raise GateError(f"unbalanced braces scanning body starting at offset {open_brace_idx}")


def _fn_body(text: str, fn_name_end_idx: int) -> str:
    """Given the index just after a `fn NAME` match's signature start, find
    the first `{` at or after it (skipping the `(...)  [-> Ret]` signature)
    and return the matched body."""
    brace_idx = text.find("{", fn_name_end_idx)
    if brace_idx == -1:
        raise GateError("could not find fn body opening brace")
    return _extract_braced_body(text, brace_idx)


def _find_register_fn_body(text: str) -> str | None:
    m = REGISTER_FN_DEF.search(text)
    if not m:
        return None
    return _fn_body(text, m.end())


def _rs_files(crate_src: Path) -> dict[str, Path]:
    """dotted-module-path (relative to `src/`, no `.rs`/`mod.rs`) -> Path."""
    out: dict[str, Path] = {}
    for rs in crate_src.rglob("*.rs"):
        if "/target" in str(rs) or "egg-info" in str(rs):
            continue
        rel = rs.relative_to(crate_src)
        parts = list(rel.parts)
        if parts[-1] == "mod.rs":
            parts = parts[:-1]
        elif parts[-1] == "lib.rs":
            continue
        else:
            parts[-1] = parts[-1][: -len(".rs")]
        if not parts:
            continue
        out["::".join(parts)] = rs
    return out


def _resolve_module_path(path: str, index: dict[str, Path]) -> Path | None:
    if path in index:
        return index[path]
    # Fallback: match on the last segment only (handles `use`-shortened or
    # re-exported paths a strict dotted-path index would miss).
    last = path.rsplit("::", 1)[-1]
    candidates = [p for key, p in index.items() if key.rsplit("::", 1)[-1] == last]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_python_name(
    rust_name: str,
    call_site_file: Path,
    declared_by_file: dict[Path, dict[str, str]],
) -> str:
    """Python-visible name for `rust_name` as referenced from
    `call_site_file`. Same-file declaration wins outright (authoritative,
    even with no rename -- see `_declared_idents_for`'s docstring for why
    a same-named-but-unrenamed item in this file must not inherit a
    different file's rename). Otherwise falls back to an UNAMBIGUOUS
    cross-file match (the legitimate `#[pyclass(name=...)]` declared in
    one file, `m.add_class::<T>()` called from another, e.g. `lib.rs`)."""
    same_file = declared_by_file.get(call_site_file)
    if same_file and rust_name in same_file:
        return same_file[rust_name]
    matches = {
        py_name
        for f, declared in declared_by_file.items()
        if f != call_site_file
        for name, py_name in declared.items()
        if name == rust_name
    }
    if len(matches) == 1:
        return matches.pop()
    return rust_name


def _collect_sites(
    body: str,
    body_file: Path,
    body_start_line: int,
    declared_by_file: dict[Path, dict[str, str]],
    out: list[RegSite],
) -> None:
    for pattern in (ADD_FUNCTION, ADD_CLASS):
        for m in pattern.finditer(body):
            rust_name = m.group(1)
            line = body_start_line + body[: m.start()].count("\n")
            out.append(
                RegSite(
                    python_name=_resolve_python_name(rust_name, body_file, declared_by_file),
                    rust_name=rust_name,
                    file=str(body_file),
                    line=line,
                )
            )


def discover_pymodule_units(crate_dir: Path) -> list[PymoduleUnit]:
    crate_src = crate_dir / "src"
    if not crate_src.is_dir():
        return []
    index = _rs_files(crate_src)
    # Declared-identifier maps are resolved PER FILE, not merged into one
    # crate-wide dict by bare identifier -- see `_declared_idents_for`'s
    # docstring: two different files can each declare a same-named Rust
    # item (only one of them renamed), and merging would silently conflate
    # them into one Python name at the OTHER file's call sites.
    declared_by_file: dict[Path, dict[str, str]] = {}
    texts: dict[Path, str] = {}
    for rs in list(index.values()) + [crate_src / "lib.rs"]:
        if not rs.is_file():
            continue
        try:
            texts[rs] = rs.read_text(encoding="utf-8")
        except OSError:
            continue
        declared_by_file[rs] = _declared_idents_for(texts[rs])

    lib_rs = crate_src / "lib.rs"
    if lib_rs not in texts:
        return []
    lib_text = texts[lib_rs]

    units: list[PymoduleUnit] = []
    for pm in PYMODULE_FN.finditer(lib_text):
        entry_fn = pm.group(1)
        body = _fn_body(lib_text, pm.end())
        brace_offset = lib_text.find("{", pm.end())
        body_start_line = lib_text[:brace_offset].count("\n") + 1

        unit = PymoduleUnit(crate=crate_dir.name, entry_file=str(lib_rs), entry_fn=entry_fn)
        visited_files: set[Path] = {lib_rs}
        to_visit: list[tuple[str, Path, str, int]] = [(body, lib_rs, entry_fn, body_start_line)]

        while to_visit:
            cur_body, cur_file, _cur_name, cur_start_line = to_visit.pop()
            _collect_sites(cur_body, cur_file, cur_start_line, declared_by_file, unit.sites)
            for rm in REGISTER_CALL.finditer(cur_body):
                target_path = rm.group(1)
                target_file = _resolve_module_path(target_path, index)
                if target_file is None or target_file in visited_files:
                    continue
                visited_files.add(target_file)
                target_text = texts.get(target_file)
                if target_text is None:
                    try:
                        target_text = target_file.read_text(encoding="utf-8")
                    except OSError:
                        continue
                reg_body = _find_register_fn_body(target_text)
                if reg_body is None:
                    continue
                reg_brace_offset = target_text.find(reg_body)
                reg_start_line = (
                    target_text[:reg_brace_offset].count("\n") + 1 if reg_brace_offset != -1 else 1
                )
                to_visit.append((reg_body, target_file, target_path, reg_start_line))

        units.append(unit)
    return units


def discover_crates(repo_root: Path = REPO_ROOT) -> list[Path]:
    """pyo3/maturin extension crate roots.

    Delegates to `check_stale_extensions.discover_crates` -- the SAME
    `os.walk` scan `make extensions`/CI's freshness gate already uses to
    enumerate the 10 pyo3/maturin crates under `packages/` (including the
    ones nested below a package root, e.g. `temper-placer/temper-
    constraints`, which a shallow `packages/*/` glob would miss). Writing a
    second, independent crate-discovery scan here would be exactly the
    accidental-duplication shape this whole gate exists to catch elsewhere;
    reusing the canonical one keeps there being exactly one definition of
    "which crates are pyo3/maturin extensions" in this repo.

    `repo_root` is overridable so tests can point this at a synthetic
    `tmp_path` tree instead of the real repo.
    """
    return [c.root for c in _discover_pyo3_crates(repo_root)]


@dataclass
class Report:
    units: list[PymoduleUnit]
    duplicates: dict[str, list[RegSite]]  # keyed "crate::pymodule::python_name"


def run(repo_root: Path = REPO_ROOT) -> Report:
    crates = discover_crates(repo_root)
    if not crates:
        raise GateError("found zero crates with a #[pymodule] entry point -- scan is broken")

    all_units: list[PymoduleUnit] = []
    for crate_dir in crates:
        all_units.extend(discover_pymodule_units(crate_dir))

    if not all_units:
        raise GateError("found zero #[pymodule] units across discovered crates")

    total_sites = sum(len(u.sites) for u in all_units)
    if total_sites == 0:
        raise GateError("found zero pyo3 registrations across all discovered pymodules")

    duplicates: dict[str, list[RegSite]] = {}
    for unit in all_units:
        by_name: dict[str, list[RegSite]] = {}
        for site in unit.sites:
            by_name.setdefault(site.python_name, []).append(site)
        for name, sites in by_name.items():
            distinct_locations = {(s.file, s.rust_name) for s in sites}
            if len(distinct_locations) > 1:
                key = f"{unit.crate}::{unit.entry_fn}::{name}"
                duplicates[key] = sites

    return Report(units=all_units, duplicates=duplicates)


def main() -> int:
    try:
        report = run()
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    total_units = len(report.units)
    total_sites = sum(len(u.sites) for u in report.units)

    if not report.duplicates:
        print(
            f"OK: {total_units} #[pymodule] unit(s) across "
            f"{len({u.crate for u in report.units})} crate(s), "
            f"{total_sites} registration(s) total, 0 duplicate(s)."
        )
        return EXIT_OK

    print("FAIL: duplicate pyo3 function/class registration\n")
    for key, sites in sorted(report.duplicates.items()):
        print(f"DUPLICATE_REGISTRATION  {key}")
        for s in sites:
            print(f"    {s.file}:{s.line}  fn {s.rust_name}")
        print(
            "    pyo3's PyModule::add_function/add_class is a plain setattr: "
            "the LAST registration silently wins and every earlier one "
            "becomes unreachable dead code. Consolidate to one "
            "implementation (preferred) or give the second one a distinct "
            "Python-visible name (#[pyo3(name = \"...\")])."
        )
        print()
    return EXIT_VIOLATION


if __name__ == "__main__":
    sys.exit(main())
