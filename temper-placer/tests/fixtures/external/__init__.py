"""
External PCB test fixtures for temper-placer.

This package provides infrastructure for downloading and caching
production-quality KiCad PCB files from open-source hardware projects.

Usage:
    # Download all PCBs defined in manifest.yaml
    python -m tests.fixtures.external.download_pcbs --all

    # Download specific project
    python -m tests.fixtures.external.download_pcbs --project bitaxe_ultra

    # In tests
    from tests.fixtures.external import get_pcb_path, is_pcb_available

    @pytest.mark.skipif(not is_pcb_available("bitaxe_ultra"), reason="PCB not downloaded")
    def test_bitaxe():
        pcb_path = get_pcb_path("bitaxe_ultra")
        ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

# Package directory
EXTERNAL_DIR = Path(__file__).parent

# Manifest file location
MANIFEST_PATH = EXTERNAL_DIR / "manifest.yaml"

# Cache directory for downloaded PCBs
CACHE_DIR = EXTERNAL_DIR / ".cache"


def get_pcb_path(project_name: str, pcb_index: int = 0) -> Optional[Path]:
    """
    Get the local path to a downloaded PCB file.

    Args:
        project_name: Name of the project as defined in manifest.yaml
        pcb_index: Index of the PCB file if project has multiple (default: 0)

    Returns:
        Path to the PCB file if it exists, None otherwise
    """
    from .download_pcbs import get_cached_pcb_path

    return get_cached_pcb_path(project_name, pcb_index)


def is_pcb_available(project_name: str, pcb_index: int = 0) -> bool:
    """
    Check if a PCB file has been downloaded and is available.

    Args:
        project_name: Name of the project as defined in manifest.yaml
        pcb_index: Index of the PCB file if project has multiple (default: 0)

    Returns:
        True if the PCB file exists locally
    """
    path = get_pcb_path(project_name, pcb_index)
    return path is not None and path.exists()


def list_available_projects() -> List[str]:
    """
    List all projects defined in the manifest.

    Returns:
        List of project names
    """
    from .download_pcbs import load_manifest

    manifest = load_manifest()
    return list(manifest.get("projects", {}).keys())


def list_downloaded_projects() -> List[str]:
    """
    List projects that have been downloaded to the cache.

    Returns:
        List of project names that are available locally
    """
    return [name for name in list_available_projects() if is_pcb_available(name)]
