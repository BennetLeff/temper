#!/usr/bin/env python3
"""Script sunset check: warn on stale scripts per the 30-day sunset clock.

Per the script-triage-sunset plan (U5), every script's `last_run` date in
scripts/manifest.yaml is checked against the invocation graph:
  - keep: WARNING if last_run >30 days ago AND zero callers AND not
    referenced by any .github/workflows/ job (a workflow reference means
    the script runs on every PR/push, so an aging last_run is not evidence
    of staleness -- see the false-positive fix below)
  - ticket: WARNING if last_run >30 days ago
  - ticket: ESCALATE (priority = delete) if last_run >60 days ago

False-positive fix (2026-08-19, script-sprawl cleanup phase 2.4): CI gates
that run on every PR used to surface as WARNINGs once their manifest
last_run aged past 30 days. The invocation graph records workflow callers,
but it is a committed artifact that goes stale between regenerations --
measured 2026-08-19: 20 scripts referenced in .github/workflows/*.yml were
absent from the graph, so the gates' staleness was invisible to the graph
check. The sunset clock therefore scans .github/workflows/ directly and
skips the keep-WARNING for any script referenced there (matched by script
basename, so nested entries like packages/temper-placer/scripts/*.py are
covered too). Ticket scripts are NOT skipped: a ticketed script that is
also referenced by a workflow still needs its ticket resolved.

Exit codes:
  0 - always (warnings only; never blocks PR merge)

Usage:
  uv run python scripts/check_script_sunset.py [--help] [--update-manifest]

On `--update-manifest`, the script writes back updated `last_run` dates for
keep scripts that have a caller in the invocation graph (auto-update on
main pushes). Run via CI bot or manually.
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
MANIFEST = SCRIPTS_DIR / "manifest.yaml"
GRAPH = SCRIPTS_DIR / "invocation_graph.json"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

WARN_DAYS = 30
ESCALATE_DAYS = 60

# Matches "scripts/<name>.py" references in workflow files. Also matches the
# nested form "packages/temper-placer/scripts/<name>.py" (the substring
# "scripts/<name>.py" appears in it).
_WORKFLOW_SCRIPT_RE = re.compile(r"scripts/([a-zA-Z0-9_]+\.py)\b")


def workflow_referenced_scripts() -> set[str]:
    """Basenames of scripts referenced as scripts/<name>.py in workflows.

    A script referenced by a workflow runs on PRs/pushes, so its manifest
    last_run aging past 30 days is not evidence of staleness. Checked
    directly against the workflow files rather than the invocation graph,
    because the graph is a committed artifact that goes stale between
    regenerations (20 scripts referenced in workflows were absent from it
    on 2026-08-19).
    """
    refs: set[str] = set()
    if not WORKFLOWS_DIR.is_dir():
        return refs
    files = sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(
        WORKFLOWS_DIR.glob("*.yaml")
    )
    for f in files:
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for match in _WORKFLOW_SCRIPT_RE.finditer(text):
            refs.add(match.group(1))
    return refs


def parse_manifest(path: Path) -> list[dict]:
    """Tiny YAML subset parser for the manifest.

    Avoids the PyYAML dependency for a script that should always be runnable.
    Each entry has lines: `  - path:`, `    purpose:`, `    owner:`, `    last_run:`,
    `    category:`, `    disposition:`, `    imports: [...]`.
    """
    text = path.read_text()
    entries: list[dict] = []
    current: dict | None = None
    in_imports = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("- path:"):
            if current is not None:
                entries.append(current)
            current = {
                "path": stripped.split(":", 1)[1].strip(),
                "imports": [],
            }
            in_imports = False
            continue
        if current is None:
            continue
        if stripped.startswith("- "):
            # imports list item
            if in_imports:
                current["imports"].append(stripped[2:].strip())
            continue
        if stripped:
            key, _, val = stripped.partition(":")
            val = val.strip().strip('"').strip("'")
            if key == "imports":
                in_imports = val == "" or val == "[]"
            else:
                current[key] = val
                in_imports = False
    if current is not None:
        entries.append(current)
    return entries


def serialize_manifest(entries: list[dict], header_lines: list[str], footer_lines: list[str]) -> str:
    """Re-serialize the manifest from entries, preserving header/footer."""
    out = "\n".join(header_lines) + "\n"
    for e in entries:
        out += f"  - path: {e['path']}\n"
        out += f"    purpose: \"{e['purpose']}\"\n"
        out += f"    owner: {e['owner']}\n"
        out += f"    last_run: \"{e['last_run']}\"\n"
        out += f"    category: {e['category']}\n"
        out += f"    disposition: {e['disposition']}\n"
        if e.get("imports"):
            out += "    imports:\n"
            for imp in e["imports"]:
                out += f"      - {imp}\n"
        else:
            out += "    imports: []\n"
    out += "\n" + "\n".join(footer_lines)
    return out


def parse_date(s: str) -> datetime.date | None:
    s = s.strip().strip('"').strip("'")
    if not s or s.lower() in {"null", "none"}:
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Write back updated last_run dates for keep scripts with callers",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Override today's date (ISO format) for testing",
    )
    args = parser.parse_args()

    today = (
        datetime.date.fromisoformat(args.today)
        if args.today
        else datetime.date.today()
    )

    if not MANIFEST.is_file():
        print(f"[SUNSET-ERROR] Manifest not found: {MANIFEST}", file=sys.stderr)
        sys.exit(5)
    if not GRAPH.is_file():
        print(f"[SUNSET-ERROR] Invocation graph not found: {GRAPH}", file=sys.stderr)
        print("Run scripts/trace_invocations.py first.", file=sys.stderr)
        sys.exit(5)

    with open(GRAPH) as f:
        graph = json.load(f)

    text = MANIFEST.read_text()
    header_end = text.find("scripts:\n")
    if header_end == -1:
        print("[SUNSET-ERROR] Malformed manifest: 'scripts:' header missing", file=sys.stderr)
        sys.exit(5)
    header = text[: header_end + len("scripts:\n")]
    entries = parse_manifest(MANIFEST)

    warnings: list[str] = []
    escalations: list[str] = []
    updated = False
    workflow_refs = workflow_referenced_scripts()

    for entry in entries:
        path = entry["path"]
        category = entry.get("category", "")
        disposition = entry.get("disposition", "")
        last_run_str = entry.get("last_run", "")
        last_run = parse_date(last_run_str)
        callers = graph.get(path, [])
        has_caller = bool(callers)

        # Update last_run for keep scripts that have a caller
        if (
            args.update_manifest
            and category == "keep"
            and has_caller
            and last_run != today
        ):
            entry["last_run"] = today.isoformat()
            updated = True

        if last_run is None:
            continue  # no last_run, skip

        days_since = (today - last_run).days

        if category == "keep" and not has_caller and days_since > WARN_DAYS:
            # A keep script referenced by a workflow runs on every PR/push;
            # its aging last_run is not staleness evidence. Skip the warning
            # (basename match covers nested entries such as
            # packages/temper-placer/scripts/gen_config_reference.py, whose
            # workflow reference uses the full relative path).
            if Path(path).name in workflow_refs:
                continue
            warnings.append(
                f"Script '{path}' is 'keep' but has no tracked invocation in "
                f"{days_since} days. Verify it is still needed or reclassify as 'ticket'."
            )
        elif category == "ticket" and days_since > ESCALATE_DAYS:
            escalations.append(
                f"Script '{path}' has been 'ticket' for {days_since} days. "
                f"Auto-promoting to 'delete' priority. Create a PR to delete it."
            )
            if args.update_manifest:
                entry["category"] = "delete"
                entry["disposition"] = (
                    f"auto-promoted from ticket after {ESCALATE_DAYS}-day sunset clock expired"
                )
                updated = True
        elif category == "ticket" and days_since > WARN_DAYS:
            warnings.append(
                f"Script '{path}' has been 'ticket' for {days_since} days with no invocation. "
                f"Resolve ticket or reclassify as 'delete'."
            )

    if warnings or escalations:
        print("=== SCRIPT SUNSET WARNINGS ===")
        for w in warnings:
            print(f"  WARNING: {w}")
        for e in escalations:
            print(f"  ESCALATE: {e}")
        print()
        print(f"Total: {len(warnings)} warnings, {len(escalations)} escalations")
    else:
        print(f"Script sunset check OK — no stale scripts (as of {today})")

    if updated:
        # Re-serialize manifest (preserve _meta block)
        new_text = header
        for entry in entries:
            new_text += f"  - path: {entry['path']}\n"
            new_text += f"    purpose: \"{entry['purpose']}\"\n"
            new_text += f"    owner: {entry['owner']}\n"
            new_text += f"    last_run: \"{entry['last_run']}\"\n"
            new_text += f"    category: {entry['category']}\n"
            new_text += f"    disposition: {entry['disposition']}\n"
            if entry.get("imports"):
                new_text += "    imports:\n"
                for imp in entry["imports"]:
                    new_text += f"      - {imp}\n"
            else:
                new_text += "    imports: []\n"
        MANIFEST.write_text(new_text)
        print(f"Updated {MANIFEST}")

    # Sunset never blocks PR merge
    sys.exit(0)


if __name__ == "__main__":
    main()
