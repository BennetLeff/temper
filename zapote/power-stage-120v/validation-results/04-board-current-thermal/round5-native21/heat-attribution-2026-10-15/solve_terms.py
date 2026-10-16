#!/usr/bin/env python3
"""Heat attribution on the B3 body-level model: one solve per attribution term (step 1 of 2).

    python3 solve_terms.py [--snap SNAPSHOT_ROOT] [--workers 3] [--pitches 0.25,0.5] [--only TERM,...]
        -> cache/p<pitch>/<term>.npz   (rise on the four copper sheets, float32; junction rises; balance receipt)
        -> cache/p<pitch>/meta.npz/json (board mask, copper fractions, cell centres, report pads, part order)

The B3 body model (b3-convergence/thermal_body.py) is one sparse SPD system M T = q: constant k per cell (Cu/FR-4
fill-fraction mix), constant-h convection (10 W/m2K both faces, h * area on the outer sheets), constant package
conductances (pad, r_top + film), and the FET drain-lead ties g (t_rise - w.T). Nothing in M depends on T and there is
no radiation, so T is linear in q, and q is linear in (A4 copper fields, part watts, lead tie temperatures). Each term
is therefore solved alone with the SAME matrix: every part's package network and every lead tie stays in M, only the
right-hand side changes (part watts zeroed outside the term, tie t_rise zero outside the term, A4 heat only the term's
field). Unit bases:
  A4 field f            : f at scale 1 (the case multiplies by run_study.cases()'s I^2 factor)
  part group g          : the group's rows at their c18_h10 release-case watts (run_basis.inputs, I_line 13.5 A)
  tie_hs / tie_ls       : t_rise = 1 K on Q2/Q5 (HS) or Q3/Q6 (LS) drain pads, 0 on the others
plus two controls: full_c18 and full_c22 (every term at once, the gate's own case inputs) at 0.5 mm, compared field by
field with the synthesized sum in analyze.py.

Imports only from the read-only snapshot (default: ../snap-cb48). The B3 code writes its fine-mask cache under the
snapshot's b3-ratings/runs/cache (as run_basis.py does). Workers: at most 3 (shared machine).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
DEFAULT_SNAP = HERE.parent / "snap-cb48"
CACHE = HERE / "cache"

# part-heat attribution groups (refs of the c28 heat file; every heat row is in exactly one group - checked)
PART_GROUPS = {
    "R5": ["R5"],
    "R_on": ["R10", "R12", "R18", "R20"],
    "R_off": ["R53", "R54", "R57", "R58"],
    "bank": ["C21", "C22", "C23", "C151", "C152"],
    "C5_C6": ["C5", "C6"],
    "HF_film": ["C38", "C39", "C40", "C41"],
    "RECOM": ["U41", "U42"],
    "U26": ["U26"],
    "small_LDO": ["U3", "U37", "U38", "U39"],
    "PS2": ["PS2"],
    "L1": ["L1"],
    "drivers": ["U1", "U2"],
    "R39": ["R39"],
    "rest": ["R22", "R23", "R24", "R25", "R67", "R68", "R69", "R70"],
}
TIES = {"tie_hs": ("Q2", "Q5"), "tie_ls": ("Q3", "Q6")}
FET_REFS = ("Q2", "Q3", "Q5", "Q6")


def snap_paths(snap: Path):
    ps = snap / "zapote/power-stage-120v"
    r5n = ps / "validation-results/04-board-current-thermal/round5-native21"
    return ps, r5n


_ENV = {}


def env(snap: str):
    """Import the snapshot's B3 modules once per process and patch the network-part builder (watts mask)."""
    if _ENV:
        return _ENV
    _, r5n = snap_paths(Path(snap))
    for p in (r5n / "b3-ratings", r5n / "b3-convergence", r5n):
        sys.path.insert(0, str(p))
    import run_basis  # noqa: E402  (b3-ratings: inputs(), LEAD_G, i_trip)
    import body_runs as br  # noqa: E402
    import thermal_body as tb  # noqa: E402
    import fet_case  # noqa: E402
    import b3_ratings_gate as gate  # noqa: E402
    for mod in (run_basis, br, tb, fet_case, gate):
        assert str(Path(mod.__file__).resolve()).startswith(str(Path(snap).resolve())), (mod.__name__, mod.__file__)
    orig = tb.build_network_parts

    def build_masked(*a, **k):
        parts, omitted = orig(*a, **k)
        active = _ENV.get("active")            # None: every part heated; else the set of refs that keep their watts
        if active is not None:
            for p in parts:
                if p.ref not in active:
                    p.watts = 0.0
        return parts, omitted
    tb.build_network_parts = build_masked
    _ENV.update(run_basis=run_basis, br=br, tb=tb, fet_case=fet_case, gate=gate, rs=br.rs, snap=Path(snap), active=None)
    return _ENV


def release_inputs(e, work: Path, ceil=18.0, op="c18"):
    """The gate's own case inputs (run_basis.inputs): A4 case string and heat json at I_line 13.5 A."""
    work.mkdir(parents=True, exist_ok=True)
    return e["run_basis"].inputs(op, ceil, str(work))


def a4_names(case_str):
    return [it.split(":")[0] for it in case_str.split(",")]


def all_terms(case_str):
    return [f"a4:{n}" for n in a4_names(case_str)] + [f"part:{g}" for g in PART_GROUPS] + [f"tie:{t}" for t in TIES]


def one(job):
    snap, pitch, term, outdir = job
    e = env(snap)
    br, tb, rb, fc = e["br"], e["tb"], e["run_basis"], e["fet_case"]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{term.replace(':', '__')}.npz"
    if f.exists():
        return term, pitch, "cached", 0.0
    t0 = time.time()
    work = out.parent / "inputs"
    case18, heat18, mode = release_inputs(e, work / f"c18_{os.getpid()}", 18.0, "c18")
    hp = json.loads(Path(heat18).read_text())["parts"]
    refs_heat = {p["ref"] for p in hp if p.get("board_fraction") and p.get("watts_nominal")}
    grouped = [r for g in PART_GROUPS.values() for r in g]
    assert sorted(grouped) == sorted(refs_heat), (sorted(set(refs_heat) - set(grouped)), sorted(set(grouped) - set(refs_heat)))
    t_zero = {r: 0.0 for r in FET_REFS}
    kind, name = term.split(":", 1)
    use_a4, case_str, active, t_rise = False, case18, set(), dict(t_zero)
    bay = None
    if kind == "a4":
        use_a4, case_str = True, f"{name}:1"
    elif kind == "part":
        active = set(PART_GROUPS[name])
    elif kind == "tie":
        t_rise.update({r: 1.0 for r in TIES[name]})
    elif kind == "full":                      # control: the gate's own case, every term at once
        ceil, bay = {"c18": (18.0, 61.0), "c22": (22.0, 55.0)}[name]
        case_str, heat18, mode = release_inputs(e, work / f"{name}_{os.getpid()}", ceil, name)
        use_a4, active = True, None
        t_rise = {r: t - bay for r, t in fc.t_case(ceil, i_line=rb.I_LINE_A).items()}
    else:
        raise KeyError(term)
    e["active"] = active
    br.op_inputs = lambda _op, _c=(case_str, heat18, mode): _c
    brd = tb.Board(e["rs"].GEOM, rb.RUNS / "cache")
    leads = {"pad": "2", "g": rb.LEAD_G, "t_rise": t_rise}
    res, rise = br.run_case(brd, "c18", 10, pitch, "fraction", "network", {}, None, None, use_a4, True,
                            label=f"{term}@{pitch}", return_rise=True, leads=leads)
    cu = tb.CU_INDEX
    zs = [cu[n] for n in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")]
    tj = {r["ref"]: r["tj_c"] - tb.TAMB_C for r in res["parts"] if "tj_c" in r}
    np_save = dict(cu=rise[zs].astype("float32"), tj_refs=list(tj), tj=list(tj.values()))
    import numpy as np
    tmp = f.with_name(f.stem + f".{os.getpid()}.tmp.npz")
    np.savez_compressed(tmp, cu=np_save["cu"], tj_refs=np.array(np_save["tj_refs"]), tj=np.array(np_save["tj"]))
    (out / f"{term.replace(':', '__')}.json").write_text(json.dumps(
        {"term": term, "pitch": pitch, "balance": res["balance"], "a4_placed_w": res["a4_placed_w"],
         "board_sha256": brd.data["board_sha256"], "runtime_s": res["runtime_s"], "t_rise": t_rise,
         "active": None if active is None else sorted(active), "case_str": case_str if use_a4 else None,
         "bay_c": bay, "rows": res["parts"], "peak_1mm_block": res["peak_1mm_block"],
         "fet_row_max_c": res["fet_row_max_c"]}, indent=1) + "\n")
    os.replace(tmp, f)                         # the npz marks the term done (written last)
    if not (out / "meta.npz").exists():
        write_meta(e, brd, pitch, out, hp)
    return term, pitch, "solved", time.time() - t0


def write_meta(e, brd, pitch, out, hp):
    """Geometry the metrics need: board mask, copper fractions, cell centres, each heated part's reported pad cells."""
    import numpy as np
    br, tb = e["br"], e["tb"]
    nx, ny = brd.grid_n(pitch)
    board, cfrac = brd.window_arrays(pitch, 0, nx, 0, ny)
    x = brd.xmin + (np.arange(nx) + 0.5) * pitch
    y = brd.ymin + (np.arange(ny) + 0.5) * pitch
    names = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    pads = {}
    for p in hp:
        if p.get("board_fraction") in (None, 0) or p.get("watts_nominal") in (None, 0):
            continue
        layer, ent = br.report_entries(brd, p["ref"], p.get("pad_numbers"), pitch, 0, 0, nx, ny)
        pads[p["ref"]] = {"layer": names.index(layer), "ii": np.concatenate([q[1] for q in ent]).tolist(),
                          "jj": np.concatenate([q[2] for q in ent]).tolist(),
                          "a": np.concatenate([q[3] for q in ent]).tolist()}
    pid = os.getpid()
    (out / f"meta.{pid}.json").write_text(json.dumps({"pitch": pitch, "layers": names, "pads": pads,
                                                      "board_sha256": brd.data["board_sha256"]}) + "\n")
    os.replace(out / f"meta.{pid}.json", out / "meta.json")
    np.savez_compressed(out / f"meta.{pid}.tmp.npz", board=board, cfrac=np.stack([cfrac[n] for n in names]).astype("float32"), x=x, y=y)
    os.replace(out / f"meta.{pid}.tmp.npz", out / "meta.npz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap", default=str(DEFAULT_SNAP))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--pitches", default="0.25,0.5")
    ap.add_argument("--only", help="comma list of terms (default: every term + the 0.5 mm full-case controls)")
    a = ap.parse_args()
    e = env(a.snap)
    sys.path.insert(0, str(snap_paths(Path(a.snap))[1]))
    import a4_fields
    if not a4_fields.check():
        raise SystemExit("task-04 heat fields do not match outputs/cache.json")
    case18, _, _ = release_inputs(e, CACHE / "inputs" / "c18", 18.0, "c18")
    terms = all_terms(case18)
    pitches = [float(p) for p in a.pitches.split(",")]
    jobs = []
    for p in sorted(pitches):                  # coarse first: the 0.5 mm set is the fast sanity pass
        sel = a.only.split(",") if a.only else terms + (["full:c18", "full:c22"] if p == 0.5 else [])
        jobs += [(a.snap, p, t, str(CACHE / f"p{str(p).replace('.', 'p')}")) for t in sel]
    e["tb"].Board(e["rs"].GEOM, e["run_basis"].RUNS / "cache").fine()
    print(f"{len(jobs)} solves, {min(a.workers, 3)} workers", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, min(a.workers, 3))) as ex:
        for term, p, st, dt in ex.map(one, jobs):
            print(f"  {st} {term} @ {p} mm  {dt:.0f} s", flush=True)


if __name__ == "__main__":
    main()
