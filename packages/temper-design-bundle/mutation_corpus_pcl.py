#!/usr/bin/env python3
"""Anti-vacuity mutation corpus for the Wave-4 Phase-2 PCL migration.

A differential that passes proves nothing until you have shown it can fail.
This script applies each mutation below to the Rust source in place, rebuilds
the extension, re-runs the PCL gate suite, records whether the mutation was
KILLED (some test failed) or SURVIVED, and restores the source.

Every mutation is a plausible port error, not a strawman: each one is the
mistake a competent engineer would actually make writing this file -- an
`is_ascii_digit` where CPython means `isdigit`, a `trim()` where CPython means
`strip()`, a sorted intersection where CPython iterates a set, `<` where the
reference has `>`, a `to_lowercase()` where the reference uppercases.

Survivors are not swept up: each is either killed by a new discriminating test
or proven equivalent with evidence, and the outcome is recorded in
VERIFICATION.md.

Usage:
    python3 packages/temper-design-bundle/mutation_corpus_pcl.py
    python3 packages/temper-design-bundle/mutation_corpus_pcl.py --only M03
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
SRC = WT / "packages/temper-design-bundle/src"
TAGS = SRC / "pcl_tags.rs"
PARSE = SRC / "pcl_parse.rs"
DEV = WT / "dev.sh"
PLACER = WT / "packages/temper-placer"

# The gate suite the mutations must be caught by.
GATE = [
    "tests/pcl/test_parse_utils_rust_differential.py",
    "tests/pcl/test_tag_dispatch_rust_differential.py",
    "tests/pcl/test_pcl_rust_pbt.py",
    "tests/pcl/test_pcl_bench_fixture_parity.py",
    "tests/pcl",
]

# (id, file, old, new, what real mistake this models)
MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    # --- pcl_parse.rs: the CPython string-primitive traps -------------------
    (
        "M01",
        PARSE,
        "fn py_isdigit(py: Python<'_>, c: char) -> PyResult<bool> {\n    if c.is_ascii() {",
        "fn py_isdigit(py: Python<'_>, c: char) -> PyResult<bool> {\n    if true {",
        "treat str.isdigit() as ASCII-only (rejects fullwidth/Arabic-Indic digits)",
    ),
    (
        "M02",
        PARSE,
        "'\\x1c'..='\\x1f' | ' ')",
        "' ')",
        "use Rust's char::is_whitespace set, dropping the C0 separators",
    ),
    (
        "M03",
        PARSE,
        '"mil" => Ok(number * 0.0254),',
        '"mil" => Ok(number * 0.0255),',
        "R24: wrong mil->mm conversion factor",
    ),
    (
        "M04",
        PARSE,
        '"in" => Ok(number * 25.4),',
        '"in" => Ok(number * 2.54),',
        "R24: wrong inch->mm conversion factor (off by 10x)",
    ),
    (
        "M05",
        PARSE,
        "    if number < 0.0 {",
        "    if number <= 0.0 {",
        "off-by-one on the negativity guard (rejects 0mm)",
    ),
    (
        "M06",
        PARSE,
        'if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() {',
        'if value.is_instance_of::<PyFloat>() {',
        "forget that bool/int satisfy isinstance(x,(int,float))",
    ),
    (
        "M07",
        PARSE,
        '            Ok(1) => Some("HARD"),',
        '            Ok(1) => Some("STRONG"),',
        "swap two tier mappings",
    ),
    (
        "M08",
        PARSE,
        '"horizontal" | "h" | "x" => Some("X"),',
        '"horizontal" | "h" => Some("X"),',
        "drop the plain 'x' axis value, keeping only the aliases",
    ),
    (
        "M09",
        PARSE,
        '            format!("Distance cannot be negative: {value}"),',
        '            format!("Distance must not be negative: {value}"),',
        "reword an error message (message text is part of the contract)",
    ),
    (
        "M10",
        PARSE,
        "        \"mm\" | \"\" => Ok(number),",
        "        \"mm\" => Ok(number),",
        "stop treating the empty unit as millimetres",
    ),
    # --- pcl_tags.rs: the lattice ------------------------------------------
    (
        "M11",
        TAGS,
        "    &[1],    // DECOUPLING -> POWER",
        "    &[2],    // DECOUPLING -> POWER",
        "reparent DECOUPLING under SIGNAL instead of POWER",
    ),
    (
        "M12",
        TAGS,
        "        closure[i] |= 1 << i;",
        "        closure[i] |= 0;",
        "drop reflexivity from the Floyd-Warshall seeding",
    ),
    (
        "M13",
        TAGS,
        "                if closure[i] & (1 << k) != 0 && closure[k] & (1 << j) != 0 {",
        "                if closure[i] & (1 << k) != 0 || closure[k] & (1 << j) != 0 {",
        "&& -> || in the Floyd-Warshall relaxation",
    ),
    (
        "M14",
        TAGS,
        "fn tag_le_idx(a: usize, b: usize) -> bool {\n    closure()[a] & (1 << b) != 0\n}",
        "fn tag_le_idx(a: usize, b: usize) -> bool {\n    closure()[b] & (1 << a) != 0\n}",
        "invert the <= relation (ancestor/descendant swap)",
    ),
    # --- pcl_tags.rs: resolve ----------------------------------------------
    (
        "M15",
        TAGS,
        "            if crate::pcl_parse::py_upper(py, t)? == tag_upper {",
        "            if t == &tag_upper {",
        "case-sensitive tag membership (drops the .upper() normalisation)",
    ),
    (
        "M16",
        TAGS,
        "        return Ok(resolve_inner(py, node.left.bind(py), comp)?\n            && resolve_inner(py, node.right.bind(py), comp)?);\n    }\n    if let Ok(node) = expr.cast::<TagOr>() {",
        "        return Ok(resolve_inner(py, node.left.bind(py), comp)?\n            || resolve_inner(py, node.right.bind(py), comp)?);\n    }\n    if let Ok(node) = expr.cast::<TagOr>() {",
        "TagAnd evaluates as OR",
    ),
    (
        "M17",
        TAGS,
        "        return Ok(!resolve_inner(py, node.expr.bind(py), comp)?);",
        "        return Ok(resolve_inner(py, node.expr.bind(py), comp)?);",
        "TagNot forgets to negate",
    ),
    (
        "M18",
        TAGS,
        "        return comp.getattr(\"ref\")?.eq(node.r#ref.bind(py));",
        "        return Ok(false);",
        "ComponentRef never matches",
    ),
    # --- pcl_tags.rs: _check_overconstrained -------------------------------
    (
        "M19",
        TAGS,
        "                if s.dist > a.dist {",
        "                if s.dist >= a.dist {",
        "off-by-one: flag equal bounds as contradictory",
    ),
    (
        "M20",
        TAGS,
        "        let key = if a <= b {\n            (a.clone(), b.clone())\n        } else {\n            (b.clone(), a.clone())\n        };",
        "        let key = (a.clone(), b.clone());",
        "drop the sorted() normalisation of the (a,b) pair key",
    ),
    (
        "M21",
        TAGS,
        "    let intersection = adj_set.call_method1(\"__and__\", (&sep_set,))?;\n\n    for key_obj in intersection.try_iter()? {",
        "    let intersection = adj_set.call_method1(\"__and__\", (&sep_set,))?;\n    let intersection = intersection.call_method0(\"__iter__\")?;\n    let mut _sorted: Vec<_> = Vec::new();\n    for k in intersection.try_iter()? {\n        _sorted.push(k?);\n    }\n    _sorted.sort_by_key(|k| k.str().map(|s| s.to_string()).unwrap_or_default());\n    for key_obj in _sorted.into_iter().map(Ok::<_, PyErr>) {",
        "SORT the set intersection (the 'undetectable behaviour change' the brief warns about)",
    ),
    (
        "M22",
        TAGS,
        "        if tc.hasattr(\"max_distance_mm\")? {",
        "        if tc.hasattr(\"min_distance_mm\")? {",
        "swap the if/elif order so a both-bounds constraint lands in separation",
    ),
    (
        "M23",
        TAGS,
        "        for a in adj_entries {\n            for s in sep_entries {",
        "        for s in sep_entries {\n            for a in adj_entries {",
        "swap the itertools.product loop nesting (changes which pair is reported first)",
    ),
    (
        "M24",
        TAGS,
        "{:.1}mm but \\\n                             [{}:{}] requires \\u{2265}{:.1}mm",
        "{:.2}mm but \\\n                             [{}:{}] requires \\u{2265}{:.2}mm",
        "change the float format precision in the error message",
    ),
    # --- pcl_tags.rs: pyclass contract fidelity ----------------------------
    (
        "M25",
        TAGS,
        'Ok(format!("TagRef(tag={})", self.tag.bind(py).repr()?))',
        'Ok(format!("TagRef({})", self.tag.bind(py).repr()?))',
        "drop the field name from __repr__ (dataclass reprs include it)",
    ),
    (
        "M26",
        TAGS,
        "    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {\n        tuple_hash(py, vec![self.tag.clone_ref(py)])\n    }",
        "    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {\n        let _ = py;\n        Ok(0)\n    }",
        "constant __hash__ (still consistent with eq, so this may survive)",
    ),
    (
        "M27",
        TAGS,
        "let msg = format!(\"cannot {verb} field '{name}'\");",
        "let msg = format!(\"cannot set field '{name}'\");",
        "wrong FrozenInstanceError message wording",
    ),
    (
        "M28",
        TAGS,
        "    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {\n        let Ok(other) = other.cast::<TagRef>() else {\n            return Ok(false);\n        };",
        "    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {\n        let Ok(other) = other.cast::<TagRef>() else {\n            return Ok(true);\n        };",
        "TagRef.__eq__ returns True for foreign types (dataclass eq returns NotImplemented->False)",
    ),
    (
        "M29",
        PARSE,
        "    let raw: String = value.extract()?;\n    let value = py_strip(py, &raw)?;",
        "    let value: String = value.extract()?;",
        "forget the leading str.strip() before scanning",
    ),
    (
        "M30",
        PARSE,
        '"cm" => Ok(number * 10.0),',
        '"cm" => Ok(number / 0.1),',
        "algebraically-equal but differently-rounded cm conversion (x*10 vs x/0.1)",
    ),
]


def _restore(backup: Path, target: Path) -> None:
    """Restore ``target`` from ``backup`` with a FRESH mtime.

    Not ``shutil.copy2``. copy2 preserves the source mtime, so cargo -- whose
    staleness check is mtime-based -- would see the restored file as older
    than the object it built from the *mutated* source and skip the rebuild,
    leaving a mutated .so behind a clean tree. That happened on the first run
    of this corpus and made a post-run test session report a hash of 0 from
    an already-reverted M26. Writing the bytes gives a new mtime and forces
    the rebuild.
    """
    target.write_bytes(backup.read_bytes())


def run(cmd, cwd=None, timeout=900):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def build() -> bool:
    r = run(
        ["cargo", "build", "--lib", "--features", "python"],
        cwd=str(WT / "packages/temper-design-bundle"),
    )
    return r.returncode == 0


def gate() -> tuple[bool, str]:
    r = run(
        [str(DEV), "-m", "pytest", *GATE, "-x", "-q", "-p", "no:randomly", "--timeout=300"],
        cwd=str(PLACER),
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=None)
    args = ap.parse_args()

    selected = [m for m in MUTATIONS if not args.only or m[0] in args.only]

    backups = {}
    with tempfile.TemporaryDirectory() as tmp:
        for path in {TAGS, PARSE}:
            backups[path] = Path(tmp) / path.name
            shutil.copy2(path, backups[path])

        # Sanity: the unmutated tree must be green, or every "KILLED" is a lie.
        if not build():
            print("FATAL: baseline build failed")
            return 2
        ok, tail = gate()
        if not ok:
            print("FATAL: baseline gate suite is RED before any mutation:\n" + tail)
            return 2
        print("baseline: build OK, gate GREEN\n")

        results = []
        for mid, path, old, new, desc in selected:
            text = path.read_text()
            if text.count(old) != 1:
                results.append(
                    {
                        "id": mid,
                        "file": path.name,
                        "desc": desc,
                        "outcome": "NOT_APPLIED",
                        "detail": f"anchor occurs {text.count(old)}x, expected 1",
                    }
                )
                print(f"{mid}: NOT_APPLIED (anchor count {text.count(old)}) -- {desc}")
                continue
            path.write_text(text.replace(old, new))
            try:
                if not build():
                    outcome, detail = "KILLED_BY_COMPILER", "mutation does not compile"
                else:
                    ok, tail = gate()
                    outcome = "KILLED" if not ok else "SURVIVED"
                    detail = "" if not ok else "gate suite still green"
            finally:
                _restore(backups[path], path)
            results.append(
                {"id": mid, "file": path.name, "desc": desc, "outcome": outcome, "detail": detail}
            )
            print(f"{mid}: {outcome} -- {desc}")

        # Restore + verify we are back to green.
        for path, bak in backups.items():
            _restore(bak, path)
        assert build(), "restore failed to build"
        ok, tail = gate()
        print(f"\nrestored: gate {'GREEN' if ok else 'RED -- RESTORE FAILED'}")

    killed = sum(1 for r in results if r["outcome"].startswith("KILLED"))
    survived = [r for r in results if r["outcome"] == "SURVIVED"]
    print(f"\n{killed}/{len(results)} killed, {len(survived)} survived")
    for s in survived:
        print(f"  SURVIVOR {s['id']}: {s['desc']}")
    out = WT / "packages/temper-design-bundle/mutation_corpus_pcl_results.json"
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"results -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
