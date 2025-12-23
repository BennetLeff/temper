#!/usr/bin/env python3
"""
Clone and Extract KiCad PCBs from Known Repositories

Clones well-known open hardware repositories and extracts modern KiCad PCB files.

Usage:
    python3 tools/clone_and_extract_pcbs.py --output packages/temper-validation/data/reference_layouts
"""

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


# Known good repositories with modern KiCad files
KNOWN_REPOS = [
    # SparkFun boards
    "https://github.com/sparkfun/SparkFun_Thing_Plus_RP2350.git",
    "https://github.com/sparkfun/SparkFun_Qwiic_Micro_OLED.git",
    "https://github.com/sparkfun/SparkFun_MicroMod_Main_Board_Double.git",
    "https://github.com/sparkfun/SparkFun_MicroMod_RP2040_Processor.git",
    "https://github.com/sparkfun/SparkFun_RedBoard_Plus.git",
    "https://github.com/sparkfun/SparkFun_RedBoard_Artemis.git",
    "https://github.com/sparkfun/SparkFun_Qwiic_Buzzer.git",
    "https://github.com/sparkfun/SparkFun_Qwiic_Button.git",
    
    # Adafruit boards (may be Eagle, but worth checking)
    "https://github.com/adafruit/Adafruit-QT-Py-RP2040-PCB.git",
    "https://github.com/adafruit/Adafruit-Feather-RP2040-PCB.git",
    
    # OLIMEX
    "https://github.com/OLIMEX/ESP32-POE.git",
    "https://github.com/OLIMEX/ESP32-DevKit-LiPo.git",
]


def count_components(pcb_path: Path) -> int:
    """Count components in a KiCad PCB file."""
    try:
        with open(pcb_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Modern KiCad (v5+) uses (footprint
        modern_count = content.count("(footprint ")
        # Old KiCad (v3-4) uses (module
        old_count = content.count("(module ")
        
        return modern_count if modern_count > 0 else old_count
    except Exception:
        return 0


def is_modern_kicad(pcb_path: Path) -> bool:
    """Check if PCB file is modern KiCad format (v5+)."""
    try:
        with open(pcb_path, 'r', encoding='utf-8') as f:
            header = f.read(500)
        
        # Check for version in header
        version_match = re.search(r'\(version (\d+)\)', header)
        if version_match:
            version = int(version_match.group(1))
            return version >= 20  # KiCad v5+ uses version 20+
        
        # Fallback: check for (footprint instead of (module
        return "(footprint " in header
    except Exception:
        return False


def categorize_by_complexity(component_count: int) -> str:
    """Categorize PCB by component count."""
    if component_count < 50:
        return "simple"
    elif component_count < 100:
        return "medium"
    elif component_count < 200:
        return "complex"
    else:
        return "very_complex"


def clone_and_extract(repo_url: str, temp_dir: Path) -> list[dict]:
    """Clone a repository and extract KiCad PCB files."""
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    clone_path = temp_dir / repo_name
    
    print(f"\n📦 Cloning {repo_name}...")
    
    try:
        # Clone with depth 1 for speed
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(clone_path)],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"  ❌ Failed to clone: {e}")
        return []
    
    # Find all .kicad_pcb files
    pcb_files = list(clone_path.rglob("*.kicad_pcb"))
    
    if not pcb_files:
        print(f"  ⚠️  No .kicad_pcb files found")
        return []
    
    print(f"  Found {len(pcb_files)} PCB file(s)")
    
    candidates = []
    for pcb_file in pcb_files:
        # Skip backup files
        if "-backups" in str(pcb_file) or pcb_file.name.startswith("."):
            continue
        
        # Check if modern KiCad
        if not is_modern_kicad(pcb_file):
            print(f"  ⚠️  {pcb_file.name}: Old KiCad format, skipping")
            continue
        
        # Count components
        component_count = count_components(pcb_file)
        if component_count == 0:
            print(f"  ⚠️  {pcb_file.name}: No components found, skipping")
            continue
        
        category = categorize_by_complexity(component_count)
        print(f"  ✓ {pcb_file.name}: {component_count} components ({category})")
        
        candidates.append({
            "repo": repo_name,
            "path": pcb_file,
            "component_count": component_count,
            "category": category,
        })
    
    return candidates


def main():
    parser = argparse.ArgumentParser(description="Clone repos and extract KiCad PCBs")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packages/temper-validation/data/reference_layouts"),
        help="Output directory for downloaded PCBs",
    )
    parser.add_argument(
        "--repos",
        type=Path,
        help="Optional file with additional repo URLs (one per line)",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Clone and Extract KiCad PCBs")
    print("=" * 60)
    
    # Load additional repos if provided
    repos = KNOWN_REPOS.copy()
    if args.repos and args.repos.exists():
        with open(args.repos) as f:
            repos.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))
    
    print(f"\nProcessing {len(repos)} repositories...")
    
    all_candidates = []
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for repo_url in repos:
            candidates = clone_and_extract(repo_url, temp_path)
            all_candidates.extend(candidates)
        
        print(f"\n\n{'=' * 60}")
        print(f"Found {len(all_candidates)} valid PCBs")
        print("=" * 60)
        
        # Sort by component count
        all_candidates.sort(key=lambda x: x["component_count"])
        
        # Count by category
        counts = {"simple": 0, "medium": 0, "complex": 0, "very_complex": 0}
        for candidate in all_candidates:
            counts[candidate["category"]] += 1
        
        print(f"\nBreakdown:")
        print(f"  Simple (10-50): {counts['simple']}")
        print(f"  Medium (50-100): {counts['medium']}")
        print(f"  Complex (100-200): {counts['complex']}")
        print(f"  Very Complex (200+): {counts['very_complex']}")
        
        # Copy to output directory BEFORE temp dir is deleted
        print(f"\n💾 Copying to {args.output}")
        
        for i, candidate in enumerate(all_candidates, 1):
            category = candidate["category"]
            repo_name = candidate["repo"]
            filename = f"{repo_name}_{candidate['path'].stem}.kicad_pcb"
            
            output_dir = args.output / category
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / filename
            
            # Skip if already exists
            if output_path.exists():
                print(f"{i}. {filename} (already exists, skipping)")
                continue
            
            print(f"{i}. {filename}")
            print(f"   Components: {candidate['component_count']}")
            print(f"   Category: {category}")
            
            shutil.copy2(candidate["path"], output_path)
            print(f"   ✓ Saved")
    
    print(f"\n{'=' * 60}")
    print("✅ Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
