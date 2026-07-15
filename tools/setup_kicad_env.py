#!/usr/bin/env python3
"""
KiCad Environment Setup Tool.

1. Fetches required footprint libraries from official KiCad GitLab repo.
2. Generates local fp-lib-table for hermetic operation.

The generated table uses ${KIPRJMOD}-relative paths so pure-Python
tooling (kiutils, gen_pcb_skeleton.py) can resolve footprints without
a KiCad install.  The committed fp-lib-table is the authoritative copy;
this script only generates it as a convenience for fresh checkouts.
"""

import os
import subprocess
import sys
from pathlib import Path

# Official KiCad Footprints Repo
KICAD_GIT_URL = "https://gitlab.com/kicad/libraries/kicad-footprints.git"

# Libraries the real netlist footprint nicknames reference, plus a few
# common extras that are cheap to fetch alongside.  This list must
# stay in sync with pcb/fp-lib-table.
REQUIRED_LIBS = [
    "Capacitor_SMD",
    "Capacitor_THT",
    "Diode_SMD",
    "Fuse",
    "Inductor_SMD",
    "Package_DFN_QFN",
    "Package_SO",
    "Package_TO_SOT_SMD",
    "Package_TO_SOT_THT",
    "Resistor_SMD",
    "Resistor_THT",
    "TestPoint",
]


def run_cmd(cmd: str, cwd=None):
    """Run shell command with error handling."""
    try:
        subprocess.run(cmd, check=True, cwd=cwd, shell=True)
    except subprocess.CalledProcessError:
        print(f"Error running command: {cmd}", file=sys.stderr)
        sys.exit(1)


def fetch_libraries(libs_dir: Path) -> None:
    """Fetch specific libraries using git sparse-checkout."""
    print(f"--> Setting up footprint libraries in {libs_dir}...")
    libs_dir.mkdir(parents=True, exist_ok=True)

    repo_dir = libs_dir / "kicad-footprints"

    if not (repo_dir / ".git").exists():
        print("    Initializing git repo...")
        repo_dir.mkdir(exist_ok=True)
        run_cmd("git init", cwd=repo_dir)
        run_cmd(f"git remote add origin {KICAD_GIT_URL}", cwd=repo_dir)
        run_cmd("git config core.sparseCheckout true", cwd=repo_dir)
    else:
        print("    Repo exists, updating configuration...")

    print("    Configuring sparse-checkout...")
    sparse_file = repo_dir / ".git" / "info" / "sparse-checkout"
    paths = [f"{lib}.pretty" for lib in REQUIRED_LIBS]
    with open(sparse_file, "w") as f:
        f.write("\n".join(paths) + "\n")

    print("    Fetching data (this may take a minute)...")
    try:
        run_cmd("git fetch --depth 1 origin master", cwd=repo_dir)
        run_cmd("git checkout master", cwd=repo_dir)
        print("    Fetch complete (master branch).")
    except Exception:
        print("    Retrying with 'main' branch...")
        run_cmd("git fetch --depth 1 origin main", cwd=repo_dir)
        run_cmd("git checkout main", cwd=repo_dir)
        print("    Fetch complete (main branch).")




def _create_stub_footprints(libs_dir: Path) -> None:
    """Create minimal footprints for netlist references that have no
    exact match in the standard KiCad libraries."""
    stubs = {
        "Fuse.pretty/Fuse_Holder_5x20mm.kicad_mod": """(footprint "Fuse_Holder_5x20mm"
  (version 20240108) (generator "stub")
  (descr "Stub for Schurter 0034.3128 fuse holder. 5x20mm, P=22.5mm. No exact match in standard KiCad library.")
  (attr through_hole)
  (pad "1" thru_hole circle (at 0 0) (size 2.5 2.5) (drill 1.4) (layers "*.Cu" "*.Mask"))
  (pad "2" thru_hole circle (at 22.5 0) (size 2.5 2.5) (drill 1.4) (layers "*.Cu" "*.Mask"))
)""",
        "Resistor_THT.pretty/R_Disc_D15.0mm_W7.0mm_P7.5mm.kicad_mod": """(footprint "R_Disc_D15.0mm_W7.0mm_P7.5mm"
  (version 20240108) (generator "stub")
  (descr "Stub for Ametherm SL32 10015 NTC inrush limiter. D=15.0mm, P=7.5mm. No exact match in standard KiCad library.")
  (attr through_hole)
  (pad "1" thru_hole circle (at 0 0) (size 2.0 2.0) (drill 1.0) (layers "*.Cu" "*.Mask"))
  (pad "2" thru_hole circle (at 7.5 0) (size 2.0 2.0) (drill 1.0) (layers "*.Cu" "*.Mask"))
)""",
        "Inductor_SMD.pretty/L_Bourns_SRP1265A.kicad_mod": """(footprint "L_Bourns_SRP1265A"
  (version 20240108) (generator "stub")
  (descr "Stub for Bourns SRP1265A power inductor. 13.5x12.5mm body. No exact match in standard KiCad library.")
  (attr smd)
  (pad "1" smd rect (at -5.0 0) (size 3.4 5.5) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "2" smd rect (at 5.0 0) (size 3.4 5.5) (layers "F.Cu" "F.Paste" "F.Mask"))
)""",
    }
    repo_dir = libs_dir / "kicad-footprints"
    for rel_path, content in stubs.items():
        path = repo_dir / rel_path
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"    Created stub: {rel_path}")


def main() -> None:
    root_dir = Path(__file__).parent.parent
    libs_dir = root_dir / "pcb" / "libs"
    fetch_libraries(libs_dir)

    # Create stub footprints for netlist references with no standard-library match
    _create_stub_footprints(libs_dir)

    print("\nFootprint libraries ready in pcb/libs/kicad-footprints/")
    print("fp-lib-table is committed; re-run this tool after adding libraries.")


if __name__ == "__main__":
    main()
