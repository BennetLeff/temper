#!/usr/bin/env python3
"""
PCB download and cache utility for external test fixtures.

Downloads KiCad PCB files from GitHub repositories defined in manifest.yaml
and caches them locally for testing.

Usage:
    # Download all PCBs
    python -m tests.fixtures.external.download_pcbs --all

    # Download specific project
    python -m tests.fixtures.external.download_pcbs --project bitaxe_ultra

    # List available projects
    python -m tests.fixtures.external.download_pcbs --list

    # Force re-download
    python -m tests.fixtures.external.download_pcbs --project bitaxe_ultra --force
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

# Package paths
EXTERNAL_DIR = Path(__file__).parent
MANIFEST_PATH = EXTERNAL_DIR / "manifest.yaml"
DEFAULT_CACHE_DIR = EXTERNAL_DIR / ".cache"


def load_manifest() -> dict[str, Any]:
    """Load the manifest.yaml file."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")

    with open(MANIFEST_PATH) as f:
        return yaml.safe_load(f)


def get_cache_dir() -> Path:
    """Get the cache directory, creating it if necessary."""
    manifest = load_manifest()
    cache_dir_name = manifest.get("cache_dir", ".cache")
    cache_dir = EXTERNAL_DIR / cache_dir_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_project_config(project_name: str) -> dict[str, Any] | None:
    """Get configuration for a specific project."""
    manifest = load_manifest()
    projects = manifest.get("projects", {})
    return projects.get(project_name)


def get_cached_pcb_path(project_name: str, pcb_index: int = 0) -> Path | None:
    """
    Get the local cache path for a PCB file.

    Args:
        project_name: Name of the project
        pcb_index: Index of PCB file if project has multiple

    Returns:
        Path where the PCB would be cached, or None if project not found
    """
    config = get_project_config(project_name)
    if config is None:
        return None

    pcb_files = config.get("pcb_files", [])
    if pcb_index >= len(pcb_files):
        return None

    pcb_file = pcb_files[pcb_index]
    # Use project name and original filename for cache path
    filename = Path(pcb_file).name
    cache_dir = get_cache_dir()
    return cache_dir / project_name / filename


def build_github_raw_url(repo: str, ref: str, file_path: str) -> str:
    """Build a GitHub raw content URL."""
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{file_path}"


def download_file(url: str, dest: Path, timeout: int = 120) -> bool:
    """
    Download a file from URL to destination.

    Args:
        url: URL to download from
        dest: Destination path
        timeout: Request timeout in seconds

    Returns:
        True if download succeeded
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        print(f"  Downloading: {url}")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "temper-placer-test-fixtures/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()

        # Verify it looks like a KiCad PCB file
        content_str = content.decode("utf-8", errors="ignore")
        if not content_str.strip().startswith("(kicad_pcb"):
            print(f"  WARNING: File does not appear to be a KiCad PCB: {url}")
            # Still save it, tests will handle validation
        dest.write_bytes(content)
        print(f"  Saved to: {dest}")
        return True

    except urllib.error.HTTPError as e:
        print(f"  ERROR: HTTP {e.code} - {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"  ERROR: {e.reason}")
        return False
    except TimeoutError:
        print(f"  ERROR: Request timed out after {timeout}s")
        return False


def download_project(project_name: str, force: bool = False, timeout: int = 120) -> tuple[int, int]:
    """
    Download all PCB files for a project.

    Args:
        project_name: Name of the project to download
        force: Re-download even if cached
        timeout: Request timeout in seconds

    Returns:
        Tuple of (successful_downloads, failed_downloads)
    """
    config = get_project_config(project_name)
    if config is None:
        print(f"ERROR: Unknown project: {project_name}")
        return (0, 1)

    repo = config["repo"]
    ref = config.get("ref", "main")
    pcb_files = config.get("pcb_files", [])
    license_id = config.get("license", "Unknown")

    print(f"\n[{project_name}] ({repo})")
    print(f"  License: {license_id}")
    print(f"  Branch/Tag: {ref}")

    success = 0
    failed = 0

    for pcb_file in pcb_files:
        cache_path = get_cached_pcb_path(project_name, pcb_files.index(pcb_file))
        if cache_path is None:
            failed += 1
            continue

        if cache_path.exists() and not force:
            print(f"  [CACHED] {pcb_file}")
            success += 1
            continue

        url = build_github_raw_url(repo, ref, pcb_file)
        if download_file(url, cache_path, timeout):
            success += 1
        else:
            failed += 1

    return (success, failed)


def download_all(force: bool = False, timeout: int = 120) -> tuple[int, int]:
    """
    Download all projects defined in manifest.

    Args:
        force: Re-download even if cached
        timeout: Request timeout in seconds

    Returns:
        Tuple of (total_successful, total_failed)
    """
    manifest = load_manifest()
    projects = manifest.get("projects", {})

    total_success = 0
    total_failed = 0

    for project_name in projects:
        success, failed = download_project(project_name, force, timeout)
        total_success += success
        total_failed += failed

    return (total_success, total_failed)


def list_projects(show_status: bool = True) -> None:
    """List all projects defined in manifest."""
    manifest = load_manifest()
    projects = manifest.get("projects", {})

    print(f"\nProjects defined in manifest ({len(projects)} total):\n")

    for name, config in projects.items():
        repo = config.get("repo", "unknown")
        complexity = config.get("complexity", "unknown")
        license_id = config.get("license", "Unknown")

        # Check cache status
        status = "[ ]"
        cache_path = get_cached_pcb_path(name)
        if cache_path and cache_path.exists():
            status = "[✓]"

        if show_status:
            print(f"  {status} {name}")
        else:
            print(f"  {name}")
        print(f"      repo: {repo}")
        print(f"      complexity: {complexity}, license: {license_id}")


def verify_downloads() -> tuple[int, int]:
    """
    Verify all cached files are valid KiCad PCBs.

    Returns:
        Tuple of (valid_count, invalid_count)
    """
    manifest = load_manifest()
    projects = manifest.get("projects", {})

    valid = 0
    invalid = 0

    print("\nVerifying cached PCB files:\n")

    for name in projects:
        cache_path = get_cached_pcb_path(name)
        if cache_path is None or not cache_path.exists():
            continue

        try:
            content = cache_path.read_text(errors="ignore")
            if content.strip().startswith("(kicad_pcb"):
                print(f"  [✓] {name}: Valid KiCad PCB")
                valid += 1
            else:
                print(f"  [✗] {name}: Not a valid KiCad PCB")
                invalid += 1
        except Exception as e:
            print(f"  [✗] {name}: Error reading file - {e}")
            invalid += 1

    return (valid, invalid)


def main():
    parser = argparse.ArgumentParser(
        description="Download and cache external KiCad PCB files for testing"
    )
    parser.add_argument(
        "--project",
        "-p",
        help="Download specific project by name",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Download all projects",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available projects",
    )
    parser.add_argument(
        "--verify",
        "-v",
        action="store_true",
        help="Verify cached files are valid KiCad PCBs",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-download even if cached",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=120,
        help="Download timeout in seconds (default: 120)",
    )

    args = parser.parse_args()

    if args.list:
        list_projects()
        return 0

    if args.verify:
        valid, invalid = verify_downloads()
        print(f"\nResult: {valid} valid, {invalid} invalid")
        return 0 if invalid == 0 else 1

    if args.all:
        print("Downloading all external PCB fixtures...")
        success, failed = download_all(args.force, args.timeout)
        print(f"\nComplete: {success} downloaded, {failed} failed")
        return 0 if failed == 0 else 1

    if args.project:
        success, failed = download_project(args.project, args.force, args.timeout)
        return 0 if failed == 0 else 1

    # No action specified, show help
    parser.print_help()
    print("\nExamples:")
    print("  python -m tests.fixtures.external.download_pcbs --list")
    print("  python -m tests.fixtures.external.download_pcbs --all")
    print("  python -m tests.fixtures.external.download_pcbs -p bitaxe_ultra")
    return 0


if __name__ == "__main__":
    sys.exit(main())
