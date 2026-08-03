#!/usr/bin/env python3
"""Generate the repository's state blocks from source, so they cannot go stale.

Three blocks are emitted, each delimited by HTML comment markers in its host
document. Everything between the markers is machine-owned; everything outside is
hand-written and never touched.

    README.md            repo-map        every tracked top-level directory
    README.md            inventory       package count and source size
    docs/plans/README.md plan-status     plan counts by status + the active list

Why this exists
---------------
`docs/plans/README.md` was written in `cac98f5d` claiming `active` = 1. The very
next commit that day, `3b0e839d`, added two active plans. The index was false
within hours of being authored. `README.md`'s "Project Structure" table
separately documented 6 of 20 tracked top-level directories. Hand-maintained
state in this repository has an observed half-life measured in hours, so the
durable fix is to derive it and gate it.

Design rule: only mechanically-derivable facts are generated. Directory
*descriptions* are human judgment and live in DIRECTORY_PURPOSE below -- but
*completeness* is enforced: a tracked top-level directory with no description is
a hard error, so a new directory cannot silently appear undocumented.

Usage:
    uv run python scripts/gen_repo_state.py            # rewrite the blocks
    uv run python scripts/gen_repo_state.py --check     # exit 1 on drift

`--check` fails closed: drift, a missing marker, an undescribed directory, or an
unreadable source all exit non-zero. There is no soft-launch and no allowlist --
generated content starts clean, so it has no reason to be advisory.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Hand-written purpose for each tracked top-level directory. Completeness is
# machine-checked; the wording is not. Add an entry when you add a directory.
DIRECTORY_PURPOSE: dict[str, str] = {
    ".cargo": "Cargo config -- macOS pyo3 `-undefined dynamic_lookup` link flags",
    ".github": "CI workflows, issue templates, code owners",
    "benchmarks": "CP-SAT benchmark harness and external board corpora manifests",
    "components": "Local KiCad symbol/footprint libraries, one directory per part",
    "ci-corpus": "Incident regression corpus: seed/pristine fixtures and manifests the corpus oracle gate runs (plan 2026-08-02-032)",
    "configs": "Named placer configurations (deterministic, production)",
    "dashboard": "Static HTML/JS dashboard for placer metrics",
    "datasheets": "Vendor PDFs for parts used in the design",
    "docs": "Plans, brainstorms, solutions, evidence, specs, and strategy",
    "elec": "Atopile electrical source -- the schematic's source of truth",
    "firmware": "ESP32-S3 firmware (C), 8-state machine and protection monitoring",
    "max31865": "KiCad library for the MAX31865 RTD front-end (predates components/)",
    "metrics": "Recorded routing/placement metric snapshots (JSON)",
    "output_gerbers": "Exported Gerber/drill artifacts from a past routed revision",
    "packages": "Python and Rust workspace members -- placer, DRC, geometry, router",
    "pcb": "KiCad project: schematics, board, and project settings",
    "power_pcb_dataset": "Regression corpus, baselines, and DRC ceilings",
    "scripts": "CI gates, generators, and one-off analysis tooling",
    "simulation": "ngspice models and protection-gate simulation harnesses",
    "tools": "Developer utilities not wired into CI gates",
}

MARKER_BEGIN = (
    "<!-- BEGIN GENERATED: {name} -- edits here are overwritten by scripts/gen_repo_state.py -->"
)
MARKER_END = "<!-- END GENERATED: {name} -->"

PLAN_STATUS_MEANING = {
    "active": "Live work.",
    "completed": "Deliverables landed.",
    "stale": "Insufficient evidence -- needs human triage.",
    "abandoned": "Named deliverables largely absent; work never landed.",
    "superseded": "Replaced by a later plan or by STRATEGY.md.",
}
# Order is fixed so the generated table is deterministic regardless of dict order.
PLAN_STATUS_ORDER = ["active", "completed", "stale", "abandoned", "superseded"]


class GenError(Exception):
    """A condition that must fail the gate rather than produce partial output."""


def _git(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise GenError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def tracked_top_level_dirs() -> list[str]:
    """Names of tracked top-level directories, sorted.

    File *counts* are deliberately not returned. They change whenever anyone
    adds or removes any file anywhere, which made `--check` fail on unrelated
    work -- observed live when a concurrent session added one script and turned
    the gate red. That is the same volatility problem that removed line counts
    from the inventory block, one notch slower; a gate that fires without a
    defect behind it is the one that gets `continue-on-error` bolted on.

    Names alone change only when a top-level directory is added or removed,
    which is a genuinely structural event worth a diff -- and it is the only
    part that serves orientation anyway.
    """
    names = set()
    for path in _git("ls-files"):
        head, sep, _ = path.partition("/")
        if sep:
            names.add(head)
    if not names:
        raise GenError("git ls-files returned no paths under any directory")
    return sorted(names)


def parse_frontmatter_status(path: Path) -> str | None:
    """Return the `status:` value from a document's YAML frontmatter, if present.

    Handles multi-line YAML plain scalars: if the value is followed by indented
    continuation lines, they are concatenated with a single space.  This matches
    YAML's ``plain: scalar continuation`` behaviour for simple cases (no embedded
    blank lines, no comments mid-continuation).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GenError(f"could not read {path}: {exc}") from None
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    found = False
    parts: list[str] = []
    for _i, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if stripped == "---":
            break
        if found:
            # A continuation line: starts with whitespace and is not a blank
            # line that separates keys.  In YAML plain scalars, blank lines
            # terminate the continuation.
            if line and line[0] in (' ', '\t') and stripped != '':
                parts.append(stripped)
                continue
            # Not a continuation (next key, blank line, or dedented) — done.
            break
        if line.startswith("status:"):
            first = line.split(":", 1)[1].strip().strip("\"'")
            parts.append(first)
            found = True
    if parts:
        return " ".join(parts)
    return None


def plan_inventory() -> tuple[dict[str, int], int, list[tuple[str, str]]]:
    """Return (counts by status, count lacking frontmatter status, active plans)."""
    plans_dir = REPO_ROOT / "docs" / "plans"
    if not plans_dir.is_dir():
        raise GenError("docs/plans/ not found")
    counts: dict[str, int] = {}
    no_status = 0
    active: list[tuple[str, str]] = []
    for path in sorted(plans_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        status = parse_frontmatter_status(path)
        if status is None:
            no_status += 1
            continue
        counts[status] = counts.get(status, 0) + 1
        if status == "active":
            active.append((path.name, _plan_title(path)))
    if not counts:
        raise GenError("no plan documents carried a frontmatter status")
    return counts, no_status, active


def _plan_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return path.stem


def render_repo_map() -> str:
    names = tracked_top_level_dirs()
    undescribed = sorted(set(names) - set(DIRECTORY_PURPOSE))
    if undescribed:
        raise GenError(
            "tracked top-level directories have no description in "
            f"DIRECTORY_PURPOSE: {', '.join(undescribed)}. Add one so the map "
            "stays complete."
        )
    rows = ["| Directory | Purpose |", "|---|---|"]
    for name in names:
        rows.append(f"| `{name}/` | {DIRECTORY_PURPOSE[name]} |")
    return "\n".join(
        [
            f"*All {len(names)} tracked top-level directories. Generated -- a new "
            "directory without a description fails CI.*",
            "",
            *rows,
        ]
    )


def render_inventory() -> str:
    """Package inventory. Deliberately excludes line counts -- see below.

    Two kinds of fact were tried here and only one belongs in a gated block:

    - **Line counts are too volatile to gate.** They change on nearly every
      commit, so `--check` would fail on unrelated work and force a README
      regeneration into every source PR. A gate that fires constantly for
      no defect is the one that gets `continue-on-error: true` bolted on --
      exactly the pattern this file exists to avoid. LOC is already reported,
      per package and kept current automatically, by `ARCHITECTURE.svg` via
      `gen_architecture_poster.py`; duplicating it here bought nothing.
    - **Markdown counts were also self-referential.** This block renders into a
      Markdown file, so reporting Markdown lines meant emitting the block
      changed the number it reported, with no guaranteed fixpoint.

    What remains changes only when a package is added or removed, which is a
    real structural event worth a diff.
    """
    pkg_dirs = sorted(p.name for p in (REPO_ROOT / "packages").iterdir() if p.is_dir())
    return "\n".join(
        [
            f"**{len(pkg_dirs)} workspace packages** under `packages/`:",
            "",
            *(f"- `{name}`" for name in pkg_dirs),
            "",
            "Sizes and dependency edges are in [`ARCHITECTURE.svg`](./ARCHITECTURE.svg),"
            " regenerated automatically on push.",
        ]
    )


def render_plan_status() -> str:
    counts, no_status, active = plan_inventory()
    total = sum(counts.values()) + no_status
    rows = ["| Status | Count | Meaning |", "|---|---:|---|"]
    for status in PLAN_STATUS_ORDER:
        if status in counts:
            rows.append(f"| `{status}` | {counts[status]} | {PLAN_STATUS_MEANING[status]} |")
    for status in sorted(set(counts) - set(PLAN_STATUS_ORDER)):
        rows.append(f"| `{status}` | {counts[status]} | -- |")
    if no_status:
        rows.append(
            f"| *(no frontmatter)* | {no_status} | Legacy documents predating the plan format. |"
        )

    lines = [f"*{total} plan documents. Generated from frontmatter.*", "", *rows]
    lines.append("")
    if active:
        lines.append(f"**Active plans ({len(active)}):**")
        lines.append("")
        for name, title in sorted(active):
            lines.append(f"- [`{name}`](./{name}) — {title}")
    else:
        lines.append("**No active plans.**")
    return "\n".join(lines)


BLOCKS: dict[str, tuple[str, str]] = {
    # block name -> (host document, renderer key)
    "repo-map": ("README.md", "repo_map"),
    "inventory": ("README.md", "inventory"),
    "plan-status": ("docs/plans/README.md", "plan_status"),
}

RENDERERS = {
    "repo_map": render_repo_map,
    "inventory": render_inventory,
    "plan_status": render_plan_status,
}


def splice(text: str, name: str, body: str, doc_label: str) -> str:
    begin = MARKER_BEGIN.format(name=name)
    end = MARKER_END.format(name=name)
    if begin not in text or end not in text:
        raise GenError(
            f"{doc_label} is missing the '{name}' markers. Expected:\n  {begin}\n  {end}"
        )
    head, _, rest = text.partition(begin)
    _, _, tail = rest.partition(end)
    return f"{head}{begin}\n\n{body}\n\n{end}{tail}"


def build() -> dict[str, str]:
    """Return {relative doc path: full new content}."""
    rendered: dict[str, str] = {}
    docs: dict[str, str] = {}
    for name, (doc, renderer) in BLOCKS.items():
        rendered[name] = RENDERERS[renderer]()
        if doc not in docs:
            path = REPO_ROOT / doc
            if not path.is_file():
                raise GenError(f"host document not found: {doc}")
            docs[doc] = path.read_text(encoding="utf-8")
    for name, (doc, _) in BLOCKS.items():
        docs[doc] = splice(docs[doc], name, rendered[name], doc)
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if committed content differs from generated (no writes)",
    )
    args = parser.parse_args()

    try:
        docs = build()
    except GenError as exc:
        print(f"[gen_repo_state] ERROR: {exc}", file=sys.stderr)
        return 2

    drifted = []
    for doc, new_text in docs.items():
        path = REPO_ROOT / doc
        if path.read_text(encoding="utf-8") == new_text:
            continue
        drifted.append(doc)
        if not args.check:
            path.write_text(new_text, encoding="utf-8")

    if args.check:
        if drifted:
            print(
                "[gen_repo_state] DRIFT: generated state differs from committed in:\n"
                + "\n".join(f"  {d}" for d in drifted)
                + "\n\nRun: uv run python scripts/gen_repo_state.py",
                file=sys.stderr,
            )
            return 1
        print("[gen_repo_state] OK — generated state matches committed.")
        return 0

    if drifted:
        print("[gen_repo_state] updated:\n" + "\n".join(f"  {d}" for d in drifted))
    else:
        print("[gen_repo_state] no changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
