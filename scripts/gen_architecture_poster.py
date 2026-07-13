#!/usr/bin/env python3
"""Generate a deterministic SVG architecture poster from monorepo build manifests.

Reads Cargo.toml, pyproject.toml, and CMakeLists.txt to discover packages,
resolve intra-repo dependencies, count non-blank non-comment lines of code,
and render a layered (Sugiyama) directed graph as a standalone SVG.

Usage:
    uv run python scripts/gen_architecture_poster.py [--check] [--graph-only]

    --check      Exit 1 if the generated SVG differs from the committed one.
    --graph-only Print the resolved dependency graph as JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "ARCHITECTURE.svg"

EXCLUDE_DIRS = {".git", "target", ".mypy_cache", ".ruff_cache", "__pycache__",
                "node_modules", ".venv", "venv", "build", "dist", ".tox",
                "egg-info", ".eggs", "benchmarks"}
EXCLUDE_FILES = {"firmware/config.h", "firmware/main/transition_table.h"}
LOC_EXCLUDE_PATTERNS: list[str] = [
    "**/benchmarks/**",
    "firmware/config.h",
    "firmware/main/transition_table.h",
]

CMAKE_TARGET_MAP: dict[str, dict[str, str]] = {
    "temper-firmware": {"name": "firmware", "src_dir": "firmware/main"},
    "hal":            {"name": "firmware (hal)", "src_dir": "firmware/components/hal"},
    "webui":          {"name": "firmware (webui)", "src_dir": "firmware/components/webui"},
}

LANGUAGE_COLORS: dict[str, str] = {
    "Rust": "#DEA584",
    "Python": "#306998",
    "C": "#555555",
}

LANGUAGE_FONT_COLORS: dict[str, str] = {
    "Rust": "#2d1e0f",
    "Python": "#ffffff",
    "C": "#ffffff",
}

SVG_NS = "http://www.w3.org/2000/svg"
LAYER_SPACING_X = 320
NODE_SPACING_Y = 64
MIN_BOX_WIDTH = 130
MAX_BOX_WIDTH = 320
BOX_HEIGHT = 44
CORNER_RADIUS = 6
FONT_SIZE_MIN = 11
FONT_SIZE_MAX = 14
ARROW_COLOR = "#4a4a4a"
ARROW_WIDTH = 1.2
MARGIN = 60


# ---------------------------------------------------------------------------
# Package discovery
# ---------------------------------------------------------------------------

def is_rust_package(pkg_dir: Path) -> bool:
    return (pkg_dir / "Cargo.toml").exists()


def is_python_package(pkg_dir: Path) -> bool:
    return (pkg_dir / "pyproject.toml").exists() and not is_rust_package(pkg_dir)


def is_c_package(pkg_dir: Path) -> bool:
    return (pkg_dir / "CMakeLists.txt").exists() and not is_rust_package(pkg_dir) and not is_python_package(pkg_dir)


def _read_toml(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _resolve_rust_dep_path(pkg_dir: Path, dep_path: str) -> Path | None:
    """Resolve a path= dependency to a real package directory."""
    raw = dep_path.strip()
    if not raw.startswith(".."):
        # Relative sibling path like "../other-crate"
        return None
    candidate = (pkg_dir / raw).resolve()
    if (candidate / "Cargo.toml").exists():
        return candidate
    return None


def _find_cargo_toml_dirs() -> list[Path]:
    """Find all directories containing a Cargo.toml under packages/ (including nested)."""
    result: list[Path] = []
    packages_dir = REPO_ROOT / "packages"
    if not packages_dir.is_dir():
        return result
    for root, dirs, files in os.walk(packages_dir):
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS and not d.startswith(".")]
        if "Cargo.toml" in files:
            result.append(Path(root))
    return result


def _find_pyproject_dirs() -> list[Path]:
    """Find all directories containing pyproject.toml under packages/."""
    result: list[Path] = []
    packages_dir = REPO_ROOT / "packages"
    if not packages_dir.is_dir():
        return result
    for root, dirs, files in os.walk(packages_dir):
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS and not d.startswith(".")]
        if "pyproject.toml" in files and "Cargo.toml" not in files:
            result.append(Path(root))
    return result


def _find_cmake_dirs() -> list[Path]:
    """Find CMakeLists.txt directories (firmware root only for V1)."""
    cmake_path = REPO_ROOT / "firmware"
    if (cmake_path / "CMakeLists.txt").exists():
        return [cmake_path]
    return []


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

def parse_cargo(pkg_dir: Path) -> dict[str, Any] | None:
    """Parse a Cargo.toml and return package info."""
    cargo_path = pkg_dir / "Cargo.toml"
    try:
        data = _read_toml(cargo_path)
    except Exception:
        return None

    pkg_info = data.get("package", {})
    name = pkg_info.get("name", pkg_dir.name)

    src_dir = pkg_dir / "src"

    deps: list[str] = []
    for dep_name, dep_spec in data.get("dependencies", {}).items():
        if isinstance(dep_spec, dict) and "path" in dep_spec:
            resolved = _resolve_rust_dep_path(pkg_dir, str(dep_spec["path"]))
            if resolved:
                deps.append(resolved.name)

    return {
        "name": name,
        "display_name": name,
        "language": "Rust",
        "src_dir": src_dir,
        "pkg_dir": pkg_dir,
        "deps": deps,
    }


def parse_python(pkg_dir: Path, known_package_names: set[str]) -> dict[str, Any] | None:
    """Parse a pyproject.toml and return package info."""
    pyproject_path = pkg_dir / "pyproject.toml"
    try:
        data = _read_toml(pyproject_path)
    except Exception:
        return None

    project = data.get("project", {})
    name = project.get("name", pkg_dir.name)

    # Source directory
    src_dir = pkg_dir / "src"
    hatch_config = data.get("tool", {}).get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    packages = hatch_config.get("packages", [])
    if packages:
        first_pkg = packages[0]
        if first_pkg.startswith("src/"):
            src_dir = pkg_dir / first_pkg

    # Intra-repo dependencies from [project] dependencies
    deps: list[str] = []
    dep_list = project.get("dependencies", [])
    for dep in dep_list:
        dep_name = re.split(r"[<>=!~;]", dep.strip())[0].strip()
        if dep_name in known_package_names and dep_name != name:
            deps.append(dep_name)

    return {
        "name": name,
        "display_name": name,
        "language": "Python",
        "src_dir": src_dir,
        "pkg_dir": pkg_dir,
        "deps": deps,
    }


def parse_cmake(pkg_dir: Path) -> dict[str, Any] | None:
    """Parse firmware CMakeLists.txt and return package info (V1: one unit)."""
    return {
        "name": "firmware",
        "display_name": "firmware",
        "language": "C",
        "src_dir": pkg_dir / "main",
        "pkg_dir": pkg_dir,
        "deps": [],
    }


# ---------------------------------------------------------------------------
# LoC counting
# ---------------------------------------------------------------------------

def _match_any_pattern(filepath: str, patterns: list[str]) -> bool:
    """Check if filepath matches any fnmatch-style pattern (relative to repo root)."""
    from fnmatch import fnmatch
    for p in patterns:
        if fnmatch(filepath, p):
            return True
    return False


def _count_python_loc(filepath: Path) -> int:
    """Count non-blank, non-comment lines in a Python file."""
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0
    count = 0
    in_triple_quote = False
    for line in lines:
        stripped = line.strip()
        if not stripped and not in_triple_quote:
            continue
        if not in_triple_quote and stripped.startswith("#"):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # Toggle docstring state
            in_triple_quote = not in_triple_quote
            if stripped.endswith('"""') or stripped.endswith("'''"):
                if len(stripped) >= 6:
                    # Single-line docstring like """foo"""
                    continue
            if in_triple_quote and stripped.endswith(('"""', "'''")) and len(stripped) > 3:
                in_triple_quote = False
            continue
        if in_triple_quote:
            if stripped.endswith('"""') or stripped.endswith("'''"):
                in_triple_quote = False
            continue
        count += 1
    return count


def _count_crust_loc(filepath: Path) -> int:
    """Count non-blank, non-comment lines in a Rust or C file."""
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0
    count = 0
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if not stripped and not in_block_comment:
            continue
        if in_block_comment:
            end_idx = stripped.find("*/")
            if end_idx != -1:
                in_block_comment = False
                rest = stripped[end_idx + 2:].strip()
                if not rest:
                    continue
            else:
                continue
        if stripped.startswith("//"):
            continue
        if stripped.startswith("/*"):
            end_idx = stripped.find("*/", 2)
            if end_idx == -1:
                in_block_comment = True
                continue
            rest = stripped[end_idx + 2:].strip()
            if not rest:
                continue
        count += 1
    return count


def count_loc(src_dir: Path) -> int:
    """Count non-blank, non-comment lines of code in a source directory."""
    if not src_dir.is_dir():
        return 0
    total = 0
    for root, dirs, files in os.walk(str(src_dir)):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for fname in sorted(files):
            fpath = Path(root) / fname
            rel = str(fpath.relative_to(REPO_ROOT))
            if any(rel == ef for ef in EXCLUDE_FILES):
                continue
            if _match_any_pattern(rel, LOC_EXCLUDE_PATTERNS):
                continue
            suffix = fpath.suffix
            if suffix == ".py":
                total += _count_python_loc(fpath)
            elif suffix in {".rs", ".c", ".h"}:
                total += _count_crust_loc(fpath)
    return total


# ---------------------------------------------------------------------------
# Graph & Layout
# ---------------------------------------------------------------------------

def build_graph(packages: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve dependency edges and compute a deterministic layered layout."""
    pkg_names = {p["name"] for p in packages}
    pkg_by_name = {p["name"]: p for p in packages}

    edges: list[tuple[str, str]] = []
    for pkg in packages:
        for dep_name in pkg["deps"]:
            if dep_name in pkg_names and dep_name != pkg["name"]:
                edges.append((pkg["name"], dep_name))

    # Build reverse adjacency for layering from leaves outward.
    # Leaf nodes (out_degree 0) get layer 0. Dependants get higher layers.
    out_degree: dict[str, int] = {p["name"]: 0 for p in packages}
    rev_adj: dict[str, list[str]] = {p["name"]: [] for p in packages}
    for src, dst in edges:
        out_degree[src] += 1
        rev_adj[dst].append(src)

    import heapq
    queue: list[str] = []
    for name, deg in out_degree.items():
        if deg == 0:
            heapq.heappush(queue, name)

    layers: dict[str, int] = {}
    while queue:
        name = heapq.heappop(queue)
        layer = layers.get(name, 0)
        for parent in sorted(rev_adj.get(name, [])):
            new_layer = max(layers.get(parent, 0), layer + 1)
            layers[parent] = new_layer
            out_degree[parent] -= 1
            if out_degree[parent] == 0:
                heapq.heappush(queue, parent)

    for pkg in packages:
        if pkg["name"] not in layers:
            layers[pkg["name"]] = 0

    # Group nodes by layer, sort alphabetically within each layer
    layer_nodes: dict[int, list[str]] = {}
    for name, lyr in layers.items():
        layer_nodes.setdefault(lyr, []).append(name)

    max_layer = max(layer_nodes.keys()) if layer_nodes else 0

    # Compute positions
    positions: dict[str, tuple[float, float]] = {}
    for lyr in sorted(layer_nodes.keys()):
        nodes = sorted(layer_nodes[lyr])
        total_height = len(nodes) * NODE_SPACING_Y
        start_y = -(total_height / 2) + NODE_SPACING_Y / 2
        # Reverse layers: max_layer is leftmost (most dependent), layer 0 rightmost (leaf)
        x = MARGIN + (max_layer - lyr) * LAYER_SPACING_X + BOX_HEIGHT / 2
        for i, name in enumerate(nodes):
            y = start_y + i * NODE_SPACING_Y
            positions[name] = (x, y)

    return {
        "packages": pkg_by_name,
        "edges": edges,
        "layers": layers,
        "positions": positions,
        "max_layer": max_layer,
    }


# ---------------------------------------------------------------------------
# SVG rendering
# ---------------------------------------------------------------------------

def _loc_to_width(loc: int) -> float:
    """Map LoC to box width using log scale."""
    if loc == 0:
        return MIN_BOX_WIDTH
    return MIN_BOX_WIDTH + (math.log10(loc + 1) / math.log10(50001)) * (MAX_BOX_WIDTH - MIN_BOX_WIDTH)


def _font_size_for_width(width: float) -> float:
    """Compute a font size that fits within the box width."""
    return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, width / 18.0))


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_svg(graph: dict[str, Any]) -> str:
    """Render the dependency graph as a deterministic SVG string."""
    packages = graph["packages"]
    edges = sorted(graph["edges"], key=lambda e: (e[0], e[1]))
    positions = graph["positions"]
    max_layer = graph["max_layer"]

    # Compute bounding box
    all_positions = list(positions.values())
    if not all_positions:
        min_x = min_y = 0
        max_x = max_y = 100
    else:
        xs = [p[0] for p in all_positions]
        ys = [p[1] for p in all_positions]
        min_x = min(xs) - MIN_BOX_WIDTH / 2 - MARGIN
        max_x = max(xs) + MAX_BOX_WIDTH / 2 + MARGIN
        min_y = min(ys) - BOX_HEIGHT / 2 - MARGIN
        max_y = max(ys) + BOX_HEIGHT / 2 + MARGIN

    total_width = max_x - min_x
    total_height = max_y - min_y

    lines: list[str] = []
    lines.append(f'<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="{SVG_NS}" viewBox="{min_x:.1f} {min_y:.1f} {total_width:.1f} {total_height:.1f}" '
        f'width="{total_width:.1f}" height="{total_height:.1f}">'
    )
    lines.append("<defs>")
    lines.append(
        f'<marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" '
        f'orient="auto" markerUnits="userSpaceOnUse">'
    )
    lines.append(f'<polygon points="0 0, 10 3.5, 0 7" fill="{ARROW_COLOR}"/>')
    lines.append("</marker>")
    lines.append("</defs>")

    # Background
    lines.append(
        f'<rect x="{min_x:.1f}" y="{min_y:.1f}" width="{total_width:.1f}" height="{total_height:.1f}" '
        f'fill="#fafafa" rx="4"/>'
    )

    # Edges
    for src_name, dst_name in edges:
        src_pos = positions.get(src_name)
        dst_pos = positions.get(dst_name)
        if not src_pos or not dst_pos:
            continue
        sx, sy = src_pos
        dx, dy = dst_pos
        # Dependant (src) is on the right, dependency (dst) is on the left.
        # Arrow goes from right edge of src to left edge of dst (dependant → dependency).
        src_w = _loc_to_width(packages[src_name]["loc"])
        dst_w = _loc_to_width(packages[dst_name]["loc"])
        x1 = sx + src_w / 2
        x2 = dx - dst_w / 2
        mid_x = (x1 + x2) / 2
        lines.append(
            f'<path d="M{x1:.1f},{sy:.1f} Q{mid_x:.1f},{sy:.1f} {mid_x:.1f},{dy:.1f} '
            f'Q{mid_x:.1f},{dy:.1f} {x2:.1f},{dy:.1f}" '
            f'fill="none" stroke="{ARROW_COLOR}" stroke-width="{ARROW_WIDTH:.1f}" '
            f'marker-end="url(#arrowhead)"/>'
        )

    # Nodes (sorted by name for determinism)
    for name in sorted(packages.keys()):
        pkg = packages[name]
        pos = positions.get(name)
        if not pos:
            continue
        cx, cy = pos
        loc = pkg["loc"]
        box_w = _loc_to_width(loc)
        box_h = BOX_HEIGHT
        x = cx - box_w / 2
        y = cy - box_h / 2
        color = LANGUAGE_COLORS.get(pkg["language"], "#888888")
        font_color = LANGUAGE_FONT_COLORS.get(pkg["language"], "#000000")
        display_name = pkg["display_name"]
        font_size = _font_size_for_width(box_w)

        lines.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" '
            f'rx="{CORNER_RADIUS}" ry="{CORNER_RADIUS}" fill="{color}" stroke="#333" stroke-width="1"/>'
        )

        # Loc label (small, top-right)
        loc_label = f"{loc:,} LoC"
        loc_font = max(8, font_size - 2)
        lines.append(
            f'<text x="{cx:.1f}" y="{y + box_h - 8:.1f}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="{loc_font:.0f}px" fill="{font_color}" opacity="0.85">'
            f'{loc_label}</text>'
        )

        # Package name (centered)
        lines.append(
            f'<text x="{cx:.1f}" y="{cy + font_size / 3:.1f}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="{font_size:.0f}px" font-weight="bold" '
            f'fill="{font_color}">{_xml_escape(display_name)}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def discover_packages() -> list[dict[str, Any]]:
    """Discover all packages in the monorepo."""
    packages: list[dict[str, Any]] = []

    # Rust packages (Cargo.toml, skip pure-Python with pyproject only)
    rust_dirs = _find_cargo_toml_dirs()

    # Collect all Rust packages first
    for pkg_dir in rust_dirs:
        info = parse_cargo(pkg_dir)
        if info:
            packages.append(info)

    # Build known package names from discovered so far
    known_names = {p["name"] for p in packages}

    # Python packages (pyproject.toml only, no Cargo.toml)
    py_dirs = _find_pyproject_dirs()
    for pkg_dir in py_dirs:
        # Skip if this directory is already covered by a Rust package (e.g. temper-constraints in temper-placer/)
        # Also skip directories whose pyproject.toml name matches an already-discovered Rust package
        try:
            data = _read_toml(pkg_dir / "pyproject.toml")
            name = data.get("project", {}).get("name", pkg_dir.name)
        except Exception:
            name = pkg_dir.name
        if name in known_names:
            continue
        info = parse_python(pkg_dir, known_names)
        if info:
            packages.append(info)
            known_names.add(info["name"])

    # Update known names again for subsequent Python packages
    known_names = {p["name"] for p in packages}
    # Re-parse Python packages with the complete known_names set
    for i, pkg in enumerate(packages):
        if pkg["language"] == "Python":
            updated = parse_python(pkg["pkg_dir"], known_names)
            if updated:
                packages[i] = updated

    # Firmware (C)
    cmake_dirs = _find_cmake_dirs()
    for pkg_dir in cmake_dirs:
        info = parse_cmake(pkg_dir)
        if info:
            packages.append(info)

    # Sort by name for determinism
    packages.sort(key=lambda p: p["name"])
    return packages


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate architecture poster SVG")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if generated SVG differs from committed one")
    parser.add_argument("--graph-only", action="store_true",
                        help="Print parsed graph as JSON to stdout")
    args = parser.parse_args()

    packages = discover_packages()

    for pkg in packages:
        pkg["loc"] = count_loc(pkg["src_dir"])

    # Filter out packages with 0 LoC and no deps (phantom packages)
    packages = [p for p in packages if p["loc"] > 0 or p["name"] == "firmware"]

    graph = build_graph(packages)

    if args.graph_only:
        output = {
            "packages": [
                {"name": p["name"], "language": p["language"], "loc": p["loc"],
                 "deps": sorted(graph["packages"][p["name"]]["deps"])}
                for p in sorted(packages, key=lambda x: x["name"])
            ],
            "edges": sorted(graph["edges"]),
        }
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    svg = render_svg(graph)

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: {OUTPUT_PATH} does not exist (run without --check first)", file=sys.stderr)
            sys.exit(1)
        existing = OUTPUT_PATH.read_text(encoding="utf-8")
        if existing.strip() != svg.strip():
            print(f"ERROR: {OUTPUT_PATH} is out of date. Run:", file=sys.stderr)
            print("  uv run python scripts/gen_architecture_poster.py", file=sys.stderr)
            sys.exit(1)
        print(f"{OUTPUT_PATH} is up to date.")
        return

    # Write atomically: temp file then rename
    tmp_path = OUTPUT_PATH.with_suffix(".svg.tmp")
    tmp_path.write_text(svg, encoding="utf-8")
    os.replace(str(tmp_path), str(OUTPUT_PATH))
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
