"""Stage registry for the native-21 coupling audit: which board each stage tag is, where its files are, which stages
form the adopted history chain.

A stage run reads its in-repo inputs from a power-stage ROOT directory (`zapote/power-stage-120v` of a checkout, or an
export made by export_stage.sh at the stage's `root_ref`), its chain outputs from `build` (the chain's BUILDDIR under
runs-native21, outside the repo), and its legacy B3 heat maps from `b3` (see b3_maps.py). History reads each chain
stage's netlist / BOM / parts / placement with `git show REF:...` (read-only) and its as-built copper dump from ROOT.

Adopted chain only. Stage 33 (six layers, DECISIONS 39 / 40) was not adopted and stage 37 (cleanup pass on s35,
DECISIONS 48) was not merged; stages 34, 36 and 39 were never built. Each later stage is built on the one before it:
s35 on s32, s38 on s35, s40 on s38, s41 on s40, s42 on s41, s43 on s42 (DECISIONS 44, 50, 52, 53, 55, 57).
"""
from pathlib import Path

RUNS = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21")      # chain BUILDDIRs (outside the repo)
REPO = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate")      # git history (read-only), if ROOT is not a checkout

# history chain: (stage tag, git ref of the commit that made it the board of record)
CHAIN = [
    ("native21s19c", "native21s19c"), ("native21s20", "native21s20"), ("native21s21", "native21s21"),
    ("native21s21b", "native21s21b"), ("native21s22", "native21s22"), ("native21s26", "native21s26"),
    ("native21s27", "native21s27"), ("native21s28", "native21s28"), ("native21s29", "native21s29"),
    ("native21s30", "native21s30"), ("native21s31", "native21s31"), ("native21s32", "native21s32"),
    ("native21s35", "65c6bd08e"),     # DECISIONS 44, candidate 35 (SMT coil terminals)
    ("native21s38", "7f1fe9d3a"),     # DECISIONS 50, candidate 23 (PS1 deleted, PS2 MPM-20-24)
    ("native21s40", "95e24e554"),     # DECISIONS 52, candidate 30 (U44 ISO6721FB, C161 / C168)
    ("native21s41", "57fc55409"),     # DECISIONS 53, candidate 36 (tank / FET-row copper)
    ("native21s42", "5ff4aded2"),     # DECISIONS 55, candidate 39 (gate network)
    ("native21s43", "719084486"),     # DECISIONS 57, candidate 43 (cleanup pass, snubber MPN)
]
NOT_ADOPTED = {"native21s33": "six layers, phase A; not adopted on price (DECISIONS 39, 40)",
               "native21s37": "cleanup pass on s35; tool merged, board commit 5e81ba1c6 not merged (DECISIONS 48)"}

B3_DIR = "04-board-current-thermal/round5-native21/b3"      # under validation-results/

STAGES = {
    "native21s32": {
        "n": "32", "decisions": 35,
        "board_sha256": "2fb346dc8277e4295d8ef88effabdcc71dcd363fcaa93604800ddc2872fbfa4e",
        "root_ref": "f7e98c0ec",        # the commit that ran the stage-32 audit (its tree is the stage-32 input set)
        "build": RUNS / "s32/b2",
        "b3_dir": "inputs/native21s32",     # relative to 13-coupling/: a copy of the stage-32 chain's gitignored npz
        # the committed c28_h25 B3 run; its npz is gitignored, so it is named by hash (b3_maps.py --check)
        "b3": [{"run": "c28_h25_p1p0", "role": "primary", "source": "committed",
                "npz_sha256": "e5222d6c126f3fa1451f73c7b8d7b99699b5478b7208dc924b1a3ddd820928ac"}],
        "rules_upto": 32,
    },
    "native21s43": {
        "n": "43", "decisions": 57,
        "board_sha256": "61447816b9dd4921525b4f610aca40486989964368d69abb17bf7071cbf4d8df",
        "root_ref": "cb48a12e6",
        "build": RUNS / "s43/c43",
        "b3_dir": "cache/native21s43/b3",   # relative to 13-coupling/: b3_maps.py writes the regenerated runs here
        # c18_h10: the release case (DECISIONS 56), built as b3-ratings/run_basis.inputs builds it; c28_h25: the case the
        # stage-32 audit used, kept for continuity. Both are legacy thermal.py solves (b3_maps.py), the c28 one checked
        # against the stage's committed B3 output (peak and source watts) and the npz hash of the chain's own run.
        "b3": [{"run": "c18_h10_p1p0", "role": "primary", "source": "regenerate", "op": "c18", "ceiling_a": 18.0,
                "h": 10, "pitch": 1.0},
               {"run": "c28_h25_p1p0", "role": "continuity", "source": "regenerate", "op": "c28", "h": 25, "pitch": 1.0,
                "npz_sha256": "36d283950dab15c8db5ba79831f60fb416a9a97d599ef4c3b4b86bd8629254a6"}],
        "rules_upto": 43,
    },
}
LATEST = "native21s43"


def chain_upto(tag):
    """Adopted chain from 19c up to and including `tag`."""
    out = []
    for t, ref in CHAIN:
        out.append((t, ref))
        if t == tag:
            return out
    raise KeyError(tag)


def short(tag):
    """'native21s43' -> 's43'."""
    return tag[len("native21"):]
