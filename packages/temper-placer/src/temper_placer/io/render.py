"""
PCB Rendering Utilities.

Wraps kicad-cli pcb export commands for visual verification.
"""

import subprocess
import shutil
from pathlib import Path


def export_layers_svg(
    pcb_path: Path,
    output_dir: Path,
    layers: list[str],
    filename_suffix: str = "render",
    page_size_mode: int = 2,
) -> Path:
    """
    Export specified PCB layers to SVG.

    Args:
        pcb_path: Path to .kicad_pcb file.
        output_dir: Directory to save SVG file.
        layers: List of layer names (e.g. ["F.Cu", "B.Cu"]).
        filename_suffix: Suffix for output filename (default: "render").

    Returns:
        Path to the generated SVG file.
    """
    # Ensure kicad-cli exists
    if not shutil.which("kicad-cli"):
        raise RuntimeError("kicad-cli not found in PATH")

    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{pcb_path.stem}_{filename_suffix}.svg"

    cmd = [
        "kicad-cli",
        "pcb",
        "export",
        "svg",
        str(pcb_path),
        "--layers",
        ",".join(layers),
        "--output",
        str(output_file),
        "--page-size-mode",
        "2",  # 2 = Board Area Only (Smart Crop)
        "--exclude-drawing-sheet",  # Clean output
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"kicad-cli failed: {e.stderr}")

    return output_file
