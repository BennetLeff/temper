"""
Crawler for collecting PCB designs from GitHub for ML dataset.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.validation.drc import KiCadDRCValidator

logger = logging.getLogger(__name__)

@dataclass
class PcbCrawler:
    """Collects and processes KiCad PCB projects for ML dataset generation."""
    dataset_dir: Path
    temp_dir: Path = field(default_factory=lambda: Path("/tmp/pcb_crawler"))

    def __post_init__(self):
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _find_pcb_files(self, project_dir: Path) -> list[Path]:
        """Find all .kicad_pcb files in a directory recursively."""
        return list(project_dir.rglob("*.kicad_pcb"))

    def process_repository(self, repo_url: str):
        """Clone a repository and process all PCB files found."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        repo_dir = self.temp_dir / repo_name

        logger.info(f"Cloning {repo_url}...")
        try:
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            subprocess.run(["git", "clone", "--depth", "1", repo_url, str(repo_dir)], check=True)
        except Exception as e:
            logger.error(f"Failed to clone {repo_url}: {e}")
            return

        pcbs = self._find_pcb_files(repo_dir)
        logger.info(f"Found {len(pcbs)} PCB files in {repo_name}")

        for pcb_path in pcbs:
            self._process_pcb(pcb_path, repo_name)

    def _process_pcb(self, pcb_path: Path, repo_name: str):
        """Extract data and labels from a single PCB file."""
        design_id = f"{repo_name}_{pcb_path.stem}"
        output_dir = self.dataset_dir / design_id
        output_dir.mkdir(exist_ok=True)

        logger.info(f"Processing {design_id}...")

        try:
            # 1. Parse Netlist and Placement
            parse_result = parse_kicad_pcb(pcb_path)

            # 2. Run DRC for labels
            validator = KiCadDRCValidator()
            if validator.is_available():
                drc_result = validator.run_drc(pcb_path)
                drc_data = {
                    "success": drc_result.success,
                    "error_count": drc_result.error_count,
                    "warning_count": drc_result.warning_count,
                    "violations": [v.to_dict() for v in drc_result.violations]
                }
            else:
                drc_data = {"error": "kicad-cli not available"}

            # 3. Store in standardized format
            data = {
                "source": str(pcb_path),
                "repo": repo_name,
                "netlist": {
                    "n_components": parse_result.netlist.n_components,
                    "n_nets": parse_result.netlist.n_nets,
                },
                "drc": drc_data
            }

            (output_dir / "metadata.json").write_text(json.dumps(data, indent=2))

            # Copy PCB for reference
            shutil.copy(pcb_path, output_dir / "board.kicad_pcb")

            logger.info(f"Successfully processed {design_id}")

        except Exception as e:
            logger.error(f"Error processing {pcb_path}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PCB Dataset Crawler")
    parser.add_argument("--dataset", type=Path, required=True, help="Output directory")
    parser.add_argument("--repo", type=str, required=True, help="GitHub repo URL")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    crawler = PcbCrawler(dataset_dir=args.dataset)
    crawler.process_repository(args.repo)
