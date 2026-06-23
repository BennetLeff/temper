"""
Trace invocations of scripts/*.py from CI workflows, shell scripts, Makefile,
top-level Python files, and docs.

Outputs:
  - scripts/invocation_graph.json: {script: [caller_paths]}
  - scripts/manifest.yaml: updated `imports` field per entry (top-level imports
    of each script, extracted via AST)
"""
import ast
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
MANIFEST = SCRIPTS_DIR / "manifest.yaml"

# Patterns to match script invocations
# 1. CI workflow:  scripts/foo.py  or  python scripts/foo.py  or  uv run ... scripts/foo.py
# 2. Shell:        scripts/foo.py
# 3. Makefile:     scripts/foo.py
# 4. Python:       scripts/foo.py  (string literal)
SCRIPT_RE = re.compile(r"scripts/([a-zA-Z0-9_]+\.py)\b")


def iter_text_files():
    """Yield (path, content) for text files we scan."""
    # CI workflows
    yield_dir = REPO_ROOT / ".github" / "workflows"
    if yield_dir.is_dir():
        for f in yield_dir.glob("*.yml"):
            yield f, f.read_text()
        for f in yield_dir.glob("*.yaml"):
            yield f, f.read_text()

    # Shell scripts (root + subdirs, but skip vendored or generated)
    for f in REPO_ROOT.rglob("*.sh"):
        rel = f.relative_to(REPO_ROOT)
        parts = rel.parts
        if any(p.startswith(".") for p in parts[:-1]):
            continue
        if any(p in {"node_modules", "__pycache__", "venv", ".venv"} for p in parts):
            continue
        try:
            yield f, f.read_text()
        except (UnicodeDecodeError, OSError):
            pass

    # Makefile (root)
    makefile = REPO_ROOT / "Makefile"
    if makefile.exists():
        yield makefile, makefile.read_text()

    # Top-level Python files (NOT inside scripts/, packages/, or other subdirs)
    for f in REPO_ROOT.glob("*.py"):
        try:
            yield f, f.read_text()
        except (UnicodeDecodeError, OSError):
            pass

    # Packages — look for scripts/<name> references in package Python files
    # These are legitimate callers (e.g., test setup or wrapper scripts)
    for f in (REPO_ROOT / "packages").rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        try:
            yield f, f.read_text()
        except (UnicodeDecodeError, OSError):
            pass


def extract_imports(path: Path) -> list[str]:
    """Extract top-level import sources from a Python file via AST.

    Returns sorted, deduplicated list. `from X import Y` is recorded as
    just `X` (the module). `import X` is recorded as `X`.
    """
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, OSError):
        return []
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return sorted(imports)


def update_manifest_imports(imports_by_script: dict[str, list[str]]) -> bool:
    """Update the `imports` field of each manifest entry.

    Returns True if the manifest was modified.
    """
    if not MANIFEST.is_file():
        return False

    text = MANIFEST.read_text()
    new_text_lines: list[str] = []
    cur_path: str | None = None
    in_imports = False
    modified = False
    i = 0
    lines = text.splitlines()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect new entry
        if stripped.startswith("- path:"):
            cur_path = stripped.split(":", 1)[1].strip()
            in_imports = False
            new_text_lines.append(line)
            i += 1
            continue

        # Detect imports: field
        if cur_path and stripped.startswith("imports:"):
            new_imports = imports_by_script.get(cur_path, [])
            if new_imports:
                new_text_lines.append("    imports:")
                for imp in new_imports:
                    new_text_lines.append(f"      - {imp}")
                modified = True
                # Skip the rest of the imports block (if it's already populated)
                # We need to be careful: the existing format is `imports: []`
                # which is a single line, so no need to skip
                i += 1
                continue
            else:
                # No imports detected — keep as is
                new_text_lines.append(line)
                i += 1
                continue

        new_text_lines.append(line)
        i += 1

    if modified:
        MANIFEST.write_text("\n".join(new_text_lines) + "\n")
    return modified


def main():
    # Get all .py scripts
    scripts = sorted(
        f.name
        for f in SCRIPTS_DIR.glob("*.py")
        if f.name != "__init__.py" and f.is_file()
    )

    graph = {s: [] for s in scripts}

    for path, content in iter_text_files():
        for match in SCRIPT_RE.finditer(content):
            script_name = match.group(1)
            if script_name in graph:
                rel = str(path.relative_to(REPO_ROOT))
                if rel not in graph[script_name]:
                    graph[script_name].append(rel)

    # Sort callers within each entry
    for s in graph:
        graph[s].sort()

    # Compute stats
    dead = [s for s, callers in graph.items() if not callers]
    alive = [s for s, callers in graph.items() if callers]
    print(f"Total scripts: {len(scripts)}")
    print(f"With callers: {len(alive)}")
    print(f"Without callers (dead): {len(dead)}")
    print()
    print("=== DEAD SCRIPTS (no callers in CI/shell/Makefile/top-level .py/packages/) ===")
    for s in sorted(dead):
        print(f"  {s}")

    out_path = SCRIPTS_DIR / "invocation_graph.json"
    with open(out_path, "w") as f:
        json.dump(graph, f, indent=2, sort_keys=True)
    print(f"\nWrote {out_path}")

    # Extract imports per script and update manifest
    print("\nExtracting imports per script...")
    imports_by_script: dict[str, list[str]] = {}
    for s in scripts:
        path = SCRIPTS_DIR / s
        imports = extract_imports(path)
        if imports:
            imports_by_script[s] = imports
            print(f"  {s}: {len(imports)} imports")

    if update_manifest_imports(imports_by_script):
        print(f"\nUpdated {MANIFEST} with imports for {len(imports_by_script)} scripts")
    else:
        print("\nManifest imports already up-to-date")


if __name__ == "__main__":
    main()

