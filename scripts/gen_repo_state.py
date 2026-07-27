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
    ".github": "CI workflows, issue templates, code owners",
    "benchmarks": "CP-SAT benchmark harness and external board corpora manifests",
    "components": "Local KiCad symbol/footprint libraries, one directory per part",
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


def tracked_top_level_dirs() -> dict[str, int]:
    """Tracked top-level directories mapped to their tracked file count."""
    counts: dict[str, int] = {}
    for path in _git("ls-files"):
        head, sep, _ = path.partition("/")
        if sep:
            counts[head] = counts.get(head, 0) + 1
    if not counts:
        raise GenError("git ls-files returned no paths under any directory")
    return counts


def count_source_lines(paths: list[str]) -> int:
    total = 0
    for rel in paths:
        f = REPO_ROOT / rel
        try:
            with f.open("rb") as fh:
                total += sum(1 for _ in fh)
        except OSError:
            # A tracked-but-absent path is a real inconsistency, not something to
            # paper over with a silently low number.
            raise GenError(f"tracked source file could not be read: {rel}") from None
    return total


def parse_frontmatter_status(path: Path) -> str | None:
    """Return the `status:` value from a document's YAML frontmatter, if present."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GenError(f"could not read {path}: {exc}") from None
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip().strip("\"'")
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
    counts = tracked_top_level_dirs()
    undescribed = sorted(set(counts) - set(DIRECTORY_PURPOSE))
    if undescribed:
        raise GenError(
            "tracked top-level directories have no description in "
            f"DIRECTORY_PURPOSE: {', '.join(undescribed)}. Add one so the map "
            "stays complete."
        )
    rows = [
        "| Directory | Files | Purpose |",
        "|---|---:|---|",
    ]
    for name in sorted(counts):
        rows.append(f"| `{name}/` | {counts[name]} | {DIRECTORY_PURPOSE[name]} |")
    return "\n".join(
        [
            f"*Every tracked top-level directory ({len(counts)} of {len(counts)}). "
            "Generated -- a new directory without a description fails CI.*",
            "",
            *rows,
        ]
    )


def render_inventory() -> str:
    pkg_dirs = sorted(p.name for p in (REPO_ROOT / "packages").iterdir() if p.is_dir())
    py = _git("ls-files", "*.py")
    rs = _git("ls-files", "*.rs")
    # Markdown is deliberately NOT counted. This block is itself rendered into a
    # Markdown file, so reporting Markdown line counts makes the output
    # self-referential: emitting the block changes the count the block reports,
    # which requires re-emitting it. There is no guarantee that iteration
    # reaches a fixpoint, and `--check` would flap. Source LOC has no such loop
    # because generating never writes a .py or .rs file.
    return "\n".join(
        [
            f"- **{len(pkg_dirs)} workspace packages** under `packages/`",
            f"- **{count_source_lines(py):,} lines** of Python across {len(py)} files",
            f"- **{count_source_lines(rs):,} lines** of Rust across {len(rs)} files",
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
