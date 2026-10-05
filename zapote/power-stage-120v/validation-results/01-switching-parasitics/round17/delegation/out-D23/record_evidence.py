"""Record source identities and brief excerpts; no electrical acceptance logic."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
POWER = HERE.parents[4]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity() -> None:
    files = [
        POWER / "frozen/default.net", POWER / "frozen/default.csv",
        POWER / "native-19/section.kicad_pcb", POWER / "DECISIONS.md",
        HERE.parents[1] / "d2/leg_matrix.cir",
        HERE.parents[1] / "d2/legA-h0-best.matrix.txt",
        HERE.parents[1] / "d2/results/grid-best-longdt/results.jsonl",
        POWER / "validation-results/01-switching-parasitics/round4/c1-zvs/sources/ucc21550-revc.pdf",
        POWER / "validation-plan/sim-kit/common/run_ngspice.py",
        POWER / "validation-plan/sim-kit/smoke_test.py",
    ]
    doc = {
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "dirty": True,
        "scope": "out-D23 evidence only; board and source files read-only",
        "inputs": {str(p.relative_to(ROOT)): sha(p) for p in files},
        "vendor": {
            "ti": {"url": "https://www.ti.com/lit/zip/slum881", "version": "UCC21550-Q1 Rev. A, 2023-10-19",
                   "product_listing": "https://www.ti.com/product/es-mx/UCC21550-Q1",
                   "archive_sha256": sha(HERE / "vendor/slum881.zip"),
                   "library_sha256": sha(HERE / "vendor/ucc21550-q1.lib"),
                   "applicability": "B-Q1 proxy; equivalence to selected catalog BDWKR unestablished"},
            "infineon": {"library_sha256": sha(HERE / "vendor/IFX_CFD7_650V.lib"),
                         "use": "upstream kit smoke test only"},
        },
        "scripts": {p.name: sha(p) for p in HERE.glob("*.py")},
        "probe_decks": {str(p.relative_to(HERE)): sha(p) for p in HERE.rglob("*.cir") if "vendor" not in p.parts},
        "result": "INDETERMINATE: model compatibility not demonstrated; no decision-case reruns",
    }
    (HERE / "provenance.json").write_text(json.dumps(doc, indent=2) + "\n")
    net = (POWER / "frozen/default.net").read_text()
    snippets = []
    for ref in ("U1", "U2", "R9", "R17"):
        start = net.index(f'    (comp (ref "{ref}")')
        end = net.find('    (comp (ref ', start + 1)
        snippets.append(net[start:end])
    board = (POWER / "native-19/section.kicad_pcb").read_text()
    for block in board.split('\n\t(footprint ')[1:]:
        if any(f'(property "Reference" "{ref}"' in block for ref in ("R9", "R17", "U1", "U2")):
            snippets.append("\n".join(line.strip() for line in block.splitlines()
                                      if any(f'(property "{key}"' in line for key in ("Reference", "Value", "MPN", "SourceInstance"))))
    snippets.extend(line for line in (POWER / "frozen/default.csv").read_text().splitlines()
                    if any(ref in line for ref in ("R9", "UCC21550")))
    (HERE / "identity-excerpts.txt").write_text("\n\n".join(snippets) + "\n")


if __name__ == "__main__":
    source_identity()
