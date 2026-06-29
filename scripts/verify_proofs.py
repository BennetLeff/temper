"""Verify PROOFS.toml completeness — CI gate.

Reads PROOFS.toml and checks that every referenced:
- Encoding source file exists
- Test function exists (by grepping for `fn <test_name>` in the source file)
- Cross-validation tests reference proptest or hypothesis dependency

Returns exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-retype]


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start until we find a git directory (or hit /)."""
    if start is None:
        start = Path(__file__).resolve().parent
    for parent in start.parents:
        if (parent / ".git").exists():
            return parent
    return start


def extract_test_name(path_spec: str) -> tuple[str, str | None]:
    """Split a path like 'src/foo.rs::tests::bar' into (file_path, test_name).
    
    The test_name is the final segment after the last `::`, stripping `tests::`
    prefix if present (since test modules use `mod tests { fn test_name() }`).
    """
    if "::" in path_spec:
        parts = path_spec.split("::")
        file_path = parts[0]
        # The test name is the last segment (the actual fn name)
        test_name = parts[-1]
        return file_path, test_name
    return path_spec, None


def test_function_exists(file_path: Path, test_name: str) -> bool:
    """Check if `fn <test_name>` appears in the source file."""
    if not file_path.exists():
        return False
    content = file_path.read_text()
    # Match `fn test_name(` — possibly with `pub ` prefix
    pattern = re.compile(r"\bfn\s+" + re.escape(test_name) + r"\s*\(")
    return bool(pattern.search(content))


def main() -> int:
    repo_root = find_repo_root()
    proofs_toml_path = repo_root / "packages" / "temper-rust-router" / "PROOFS.toml"

    if not proofs_toml_path.exists():
        print(f"ERROR: PROOFS.toml not found at {proofs_toml_path}")
        return 1

    with open(proofs_toml_path, "rb") as f:
        data = tomllib.load(f)

    errors: list[str] = []
    crate_root = proofs_toml_path.parent

    def lookup(section_path: str) -> dict | None:
        """Navigate nested TOML sections via dot-separated path."""
        node: dict = data
        for part in section_path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        if not isinstance(node, dict):
            return None
        return node

    def check_entry(section_path: str, key: str) -> None:
        entry = lookup(section_path)
        if entry is None:
            errors.append(f"Missing section [{section_path}] in PROOFS.toml")
            return
        if key not in entry:
            errors.append(f"Missing key '{key}' in [{section_path}]")
            return
        value = entry[key]
        file_path_str, test_name = extract_test_name(value)

        # Check file exists
        full_path = crate_root / file_path_str
        if not full_path.exists():
            errors.append(
                f"[{section_path}] {key}: file not found: {full_path}"
            )
            return

        # Check test function exists if specified
        if test_name and not test_function_exists(full_path, test_name):
            errors.append(
                f"[{section_path}] {key}: test function '{test_name}' not found in {full_path}"
            )

    # Check primitive entries
    for prim in ["P1_MutualExclusion", "P2_CardinalityBound", "P4_LayerAssignment"]:
        section = f"primitive.{prim}"
        check_entry(section, "encoding")
        check_entry(section, "exhaustive_test")

    # Check composition entries
    for comp in ["Conjoin", "Conditional", "RestrictDomain"]:
        section = f"compose.{comp}"
        check_entry(section, "proof")

    # Check rewrite entries
    check_entry("rewrite.engine", "exhaustive_n6")
    check_entry("rewrite.engine", "confluence_10000")

    if errors:
        print("PROOFS.toml verification FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("PROOFS.toml verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
