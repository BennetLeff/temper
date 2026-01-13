#!/usr/bin/env python3
"""
KiCad Environment Setup Tool.

1. Fetches required footprint libraries from official GitLab repo.
2. Generates local fp-lib-table for hermetic operation.
"""

import os
import subprocess
import sys
from pathlib import Path

# Official KiCad Footprints Repo
KICAD_GIT_URL = "https://gitlab.com/kicad/libraries/kicad-footprints.git"

# Libraries identified as missing in DRC logs
REQUIRED_LIBS = [
    "Capacitor_SMD",
    "Resistor_SMD",
    "Package_SO",
    "Package_TO_SOT_THT",
    "Package_TO_SOT_SMD",
    "Diode_THT",
    "Capacitor_THT",
    "Connector_PinHeader_2.54mm",
    "MountingHole",
    "Package_DFN_QFN",
    "Connector_USB",
    "Connector_Phoenix_MC",
    "Connector_IEC",
]


def run_cmd(cmd, cwd=None):
    """Run shell command with error handling."""
    try:
        subprocess.run(cmd, check=True, cwd=cwd, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        sys.exit(1)


def fetch_libraries(libs_dir: Path):
    """Fetch specific libraries using git sparse-checkout."""
    print(f"--> Setting up libraries in {libs_dir}...")
    libs_dir.mkdir(parents=True, exist_ok=True)

    # We will clone into a subdirectory 'kicad-footprints' to keep it clean
    repo_dir = libs_dir / "kicad-footprints"

    if not (repo_dir / ".git").exists():
        print("    Initializing git repo...")
        repo_dir.mkdir(exist_ok=True)
        run_cmd(f"git init", cwd=repo_dir)
        run_cmd(f"git remote add origin {KICAD_GIT_URL}", cwd=repo_dir)
        run_cmd("git config core.sparseCheckout true", cwd=repo_dir)
    else:
        print("    Repo exists, updating configuration...")

    # Update sparse-checkout definition
    print("    Configuring sparse-checkout...")
    sparse_file = repo_dir / ".git" / "info" / "sparse-checkout"

    # We need the .pretty folders
    paths = [f"{lib}.pretty" for lib in REQUIRED_LIBS]

    with open(sparse_file, "w") as f:
        f.write("\n".join(paths) + "\n")

    # Pull (shallow if possible, but sparse-checkout usually handles it)
    print("    Fetching data (this may take a minute)...")
    # Fetch depth 1 to save bandwidth
    try:
        run_cmd("git fetch --depth 1 origin master", cwd=repo_dir)
        run_cmd("git checkout master", cwd=repo_dir)
        print("    Fetch complete.")
    except Exception:
        # Fallback to main if master doesn't exist (GitLab specific)
        print("    Retrying with 'main' branch...")
        run_cmd("git fetch --depth 1 origin main", cwd=repo_dir)
        run_cmd("git checkout main", cwd=repo_dir)


def generate_lib_table(pcb_dir: Path, libs_dir: Path):
    """Generate fp-lib-table file."""
    table_path = pcb_dir / "fp-lib-table"
    print(f"--> Generating {table_path}...")

    # KIPRJMOD is relative to the project file (pcb_dir)
    # libs_dir is pcb/libs. relative is "libs/kicad-footprints"

    header = "(fp_lib_table\n"
    footer = ")\n"

    entries = []
    repo_dir = libs_dir / "kicad-footprints"

    for lib in REQUIRED_LIBS:
        # Path relative to project root: libs/kicad-footprints/Name.pretty
        # But fp-lib-table uses ${KIPRJMOD}

        # Check if directory actually exists
        lib_path = repo_dir / f"{lib}.pretty"
        if not lib_path.exists():
            print(f"    WARNING: Library {lib} was not downloaded correctly.")
            continue

        entry = f'  (lib (name "{lib}")(type "KiCad")(uri "${{KIPRJMOD}}/libs/kicad-footprints/{lib}.pretty")(options "")(descr "Local copy"))'
        entries.append(entry)

    with open(table_path, "w") as f:
        f.write(header)
        f.write("\n".join(entries))
        f.write("\n" + footer)

    print(f"    Table generated with {len(entries)} entries.")


def main():
    root_dir = Path(__file__).parent.parent
    pcb_dir = root_dir / "pcb"
    libs_dir = pcb_dir / "libs"

    fetch_libraries(libs_dir)
    generate_lib_table(pcb_dir, libs_dir)

    print("\nSUCCESS: KiCad environment is ready.")
    print("Use 'kicad-cli pcb drc' to verify.")


if __name__ == "__main__":
    main()
