"""Round-trip candidate library copies through the installed native KiCad IO.

The original generated copies remain in generated-01. This loads library
footprints, never the board, so board edits cannot redefine the DRC oracle.
"""

from pathlib import Path
import hashlib, json
import pcbnew

base = Path(__file__).resolve().parents[1]
io = pcbnew.PCB_IO_KICAD_SEXPR()
records = []
for p in sorted((base / "candidate/candidate-libs").glob("*.pretty/*.kicad_mod")):
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    fp = io.FootprintLoad(str(p.parent), p.stem, False, None)
    if fp is None:
        raise ValueError(f"cannot load {p}")
    io.FootprintSave(str(p.parent), fp)
    records.append(
        {
            "path": str(p.relative_to(base)),
            "before_sha256": before,
            "after_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    )
(base / "evidence/library-normalization.json").write_text(
    json.dumps(
        {
            "native": pcbnew.Version(),
            "scope": "native round-trip of original library files; board not read",
            "files": records,
        },
        indent=2,
    )
    + "\n"
)
