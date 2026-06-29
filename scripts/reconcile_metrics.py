#!/usr/bin/env python3
"""Reconcile artifact-uploaded pipeline metrics NDJSON with committed JSONL.

Merges artifact .ndjson files with the existing committed pipeline_metrics.jsonl,
deduplicates by (git_commit, module, stage) with existing committed records taking
priority, sorts by timestamp, and writes the reconciled output.
"""

import json
import sys
from pathlib import Path


def reconcile(existing_path: Path, artifact_dir: Path, output_path: Path) -> int:
    """Merge existing JSONL with artifact .ndjson files, deduplicate, write output.

    Deduplication: (git_commit, module, stage) key. Existing committed records
    take priority over artifact records (first loaded wins). If two artifact
    records collide on the same key, the first encountered artifact wins.

    Returns the total number of records written.
    """
    records: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    # Load existing committed records first (they take priority)
    if existing_path.exists() and existing_path.stat().st_size > 0:
        for line in existing_path.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"WARNING: Skipping invalid JSON line in {existing_path}: "
                    f"{line[:80]}...",
                    file=sys.stderr,
                )
                continue
            key = (r["git_commit"], r.get("module", "pipeline"), r["stage"])
            if key in seen:
                continue
            seen.add(key)
            records.append(r)
        print(f"Loaded {len(records)} existing records from {existing_path}")

    # Load artifact records (existing committed records take priority)
    artifact_count = 0
    ndjson_files = sorted(artifact_dir.glob("*.ndjson"))
    if not ndjson_files:
        print("No artifact .ndjson files found in artifact directory.")

    for ndjson_file in ndjson_files:
        file_count = 0
        for line in ndjson_file.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"WARNING: Skipping invalid JSON line in {ndjson_file}: "
                    f"{line[:80]}...",
                    file=sys.stderr,
                )
                continue
            key = (r["git_commit"], r.get("module", "pipeline"), r["stage"])
            if key in seen:
                continue  # deduplicate: existing > first artifact wins
            seen.add(key)
            records.append(r)
            file_count += 1
        artifact_count += file_count
        if file_count > 0:
            print(f"  Loaded {file_count} new records from {ndjson_file.name}")

    # Sort by timestamp
    records.sort(key=lambda r: r.get("timestamp", ""))

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")

    print(f"Total reconciled records: {len(records)} "
          f"(existing: {len(records) - artifact_count}, "
          f"new from artifacts: {artifact_count})")
    return len(records)


def main():
    import argparse

    p = argparse.ArgumentParser(
        description="Reconcile artifact pipeline metrics with committed JSONL"
    )
    p.add_argument(
        "--existing-path",
        required=True,
        type=Path,
        help="Path to the committed pipeline_metrics.jsonl on main branch",
    )
    p.add_argument(
        "--artifact-dir",
        required=True,
        type=Path,
        help="Directory containing downloaded .ndjson artifact files",
    )
    p.add_argument(
        "--output-path",
        required=True,
        type=Path,
        help="Path to write the reconciled pipeline_metrics.jsonl",
    )
    args = p.parse_args()

    if not args.existing_path.exists():
        print(
            f"WARNING: Existing metrics file not found at {args.existing_path}, "
            "starting from scratch.",
            file=sys.stderr,
        )

    if not args.artifact_dir.is_dir():
        print(
            f"ERROR: Artifact directory not found: {args.artifact_dir}",
            file=sys.stderr,
        )
        return 1

    count = reconcile(args.existing_path, args.artifact_dir, args.output_path)
    return 0 if count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
