#!/usr/bin/env python3
"""
GitHub KiCad PCB Scraper

Searches GitHub for modern KiCad PCB files, analyzes component counts,
and downloads the best candidates for reference layouts.

Usage:
    python3 tools/scrape_github_pcbs.py --output packages/temper-validation/data/reference_layouts
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def count_components(pcb_content: str) -> int:
    """Count components in a KiCad PCB file."""
    # Modern KiCad (v5+) uses (footprint
    modern_count = pcb_content.count("(footprint ")
    # Old KiCad (v3-4) uses (module
    old_count = pcb_content.count("(module ")
    
    return modern_count if modern_count > 0 else old_count


def is_modern_kicad(pcb_content: str) -> bool:
    """Check if PCB file is modern KiCad format (v5+)."""
    # Check for version in header
    version_match = re.search(r'\(version (\d+)\)', pcb_content[:500])
    if version_match:
        version = int(version_match.group(1))
        return version >= 20  # KiCad v5+ uses version 20+
    
    # Fallback: check for (footprint instead of (module
    return "(footprint " in pcb_content


def search_github_code(query: str, max_results: int = 30) -> list[dict]:
    """
    Search GitHub code for KiCad PCB files.
    
    Note: GitHub API has rate limits (60 requests/hour unauthenticated).
    For authenticated requests, set GITHUB_TOKEN environment variable.
    """
    import os
    
    base_url = "https://api.github.com/search/code"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    # Check for GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
        print("✓ Using GitHub token (higher rate limits)")
    else:
        print("⚠ No GITHUB_TOKEN set (60 requests/hour limit)")
    
    params = {
        "q": query,
        "per_page": min(max_results, 100),
        "sort": "indexed",  # Most recently indexed
    }
    
    url = f"{base_url}?{urlencode(params)}"
    
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        print(f"Found {data.get('total_count', 0)} total results")
        return data.get("items", [])
    
    except (URLError, HTTPError) as e:
        print(f"Error searching GitHub: {e}")
        return []


def download_raw_file(repo: str, path: str, ref: str = "HEAD") -> Optional[str]:
    """Download raw file content from GitHub."""
    # Use raw.githubusercontent.com for direct file access
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    
    try:
        with urlopen(url, timeout=10) as response:
            return response.read().decode('utf-8')
    except (URLError, HTTPError):
        return None


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


def main():
    parser = argparse.ArgumentParser(description="Scrape GitHub for KiCad PCB files")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packages/temper-validation/data/reference_layouts"),
        help="Output directory for downloaded PCBs",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum number of search results to process",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=15,
        help="Target number of PCBs to download",
    )
    parser.add_argument(
        "--min-components",
        type=int,
        default=10,
        help="Minimum component count",
    )
    parser.add_argument(
        "--max-components",
        type=int,
        default=500,
        help="Maximum component count",
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("GitHub KiCad PCB Scraper")
    print("=" * 60)
    
    # Search queries targeting different complexity levels
    queries = [
        "extension:kicad_pcb size:>50000 size:<500000",  # Medium files
        "extension:kicad_pcb size:>500000 size:<2000000",  # Large files
        "extension:kicad_pcb Hardware path:Hardware",  # Common structure
    ]
    
    all_candidates = []
    
    for query in queries:
        print(f"\n🔍 Searching: {query}")
        results = search_github_code(query, max_results=args.max_results // len(queries))
        
        for item in results:
            repo = item["repository"]["full_name"]
            path = item["path"]
            
            # Skip if already processed
            if any(c["repo"] == repo and c["path"] == path for c in all_candidates):
                continue
            
            print(f"\n📄 {repo}/{path}")
            
            # Download and analyze
            content = download_raw_file(repo, path)
            if not content:
                print("  ❌ Failed to download")
                continue
            
            # Check if modern KiCad
            if not is_modern_kicad(content):
                print("  ⚠️  Old KiCad format (v3-4), skipping")
                continue
            
            # Count components
            component_count = count_components(content)
            if component_count < args.min_components:
                print(f"  ⚠️  Too few components ({component_count}), skipping")
                continue
            
            if component_count > args.max_components:
                print(f"  ⚠️  Too many components ({component_count}), skipping")
                continue
            
            category = categorize_by_complexity(component_count)
            print(f"  ✓ {component_count} components ({category})")
            
            all_candidates.append({
                "repo": repo,
                "path": path,
                "component_count": component_count,
                "category": category,
                "content": content,
            })
    
    print(f"\n\n{'=' * 60}")
    print(f"Found {len(all_candidates)} valid candidates")
    print("=" * 60)
    
    # Sort by component count for diversity
    all_candidates.sort(key=lambda x: x["component_count"])
    
    # Select diverse set
    selected = []
    targets = {"simple": 3, "medium": 4, "complex": 4, "very_complex": 4}
    counts = {"simple": 0, "medium": 0, "complex": 0, "very_complex": 0}
    
    for candidate in all_candidates:
        category = candidate["category"]
        if counts[category] < targets[category]:
            selected.append(candidate)
            counts[category] += 1
        
        if len(selected) >= args.target_count:
            break
    
    print(f"\n📦 Selected {len(selected)} PCBs:")
    print(f"  Simple: {counts['simple']}/{targets['simple']}")
    print(f"  Medium: {counts['medium']}/{targets['medium']}")
    print(f"  Complex: {counts['complex']}/{targets['complex']}")
    print(f"  Very Complex: {counts['very_complex']}/{targets['very_complex']}")
    
    # Download selected PCBs
    print(f"\n💾 Downloading to {args.output}")
    
    for i, candidate in enumerate(selected, 1):
        category = candidate["category"]
        repo_name = candidate["repo"].split("/")[-1]
        filename = f"{repo_name}_{Path(candidate['path']).stem}.kicad_pcb"
        
        output_dir = args.output / category
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / filename
        
        print(f"\n{i}. {filename}")
        print(f"   Source: {candidate['repo']}/{candidate['path']}")
        print(f"   Components: {candidate['component_count']}")
        print(f"   Category: {category}")
        
        with open(output_path, "w") as f:
            f.write(candidate["content"])
        
        print(f"   ✓ Saved to {output_path}")
    
    print(f"\n{'=' * 60}")
    print("✅ Done!")
    print("=" * 60)
    
    # Create summary
    summary_path = args.output / "SCRAPED_INVENTORY.md"
    with open(summary_path, "w") as f:
        f.write("# Scraped PCB Inventory\n\n")
        f.write(f"Downloaded {len(selected)} PCBs from GitHub\n\n")
        
        for category in ["simple", "medium", "complex", "very_complex"]:
            category_pcbs = [c for c in selected if c["category"] == category]
            if not category_pcbs:
                continue
            
            f.write(f"## {category.replace('_', ' ').title()} ({len(category_pcbs)} PCBs)\n\n")
            
            for candidate in category_pcbs:
                repo_name = candidate["repo"].split("/")[-1]
                filename = f"{repo_name}_{Path(candidate['path']).stem}.kicad_pcb"
                f.write(f"### {filename}\n")
                f.write(f"- **Source**: [{candidate['repo']}](https://github.com/{candidate['repo']})\n")
                f.write(f"- **Path**: `{candidate['path']}`\n")
                f.write(f"- **Components**: {candidate['component_count']}\n\n")
    
    print(f"\n📝 Summary written to {summary_path}")


if __name__ == "__main__":
    main()
