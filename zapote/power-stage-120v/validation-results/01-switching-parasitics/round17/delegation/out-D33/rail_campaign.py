"""F6 screening with a loaded shunt/reservoir, reusing f6_legs' jobs/verdicts.

This is a candidate rail model, not transformer qualification. The regulator
upstream of the split is a 17V Thevenin source (1ohm), not a switching model.
Manufacturer TLVH431 model is downloaded and hash checked, never committed.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
D2 = HERE.parents[1] / "d2"
sys.path.insert(0, str(D2))
import f6_legs as f6  # noqa: E402

URL = "https://www.ti.com/lit/zip/slvm672"
SHA = "b658a78537ed2ba314fcfadf053686280c74e234f3e2ea6c2d846db245def7a6"


def model() -> Path:
    cache = HERE / ".models"
    cache.mkdir(exist_ok=True)
    archive = cache / "slvm672.zip"
    if not archive.exists():
        archive.write_bytes(urllib.request.urlopen(URL, timeout=60).read())
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA:
        raise ValueError("TI archive hash mismatch")
    path = cache / "TLVH431.lib"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read("TLVH431_PSPICE_TRANS/TLVH431.lib").decode("latin1")
    # ngspice's PSpice TABLE translation creates XSPICE A devices that abort
    # at ~2ps in this mixed vendor deck. Preserve the published piecewise
    # transfer using algebraic B sources, including endpoint clamping.
    text = text.replace("\r\n", "\n")
    old = "G_G4         K A TABLE { V(STAGE2, A) } \n+ ( (-10,0)(0,0)(80m,80m)(10,81m) )"
    assert old in text
    text = text.replace(old, "B_G4 K A I={v(STAGE2,A)<=0 ? 0 : (v(STAGE2,A)<0.08 ? v(STAGE2,A) : (v(STAGE2,A)<10 ? 0.08+(v(STAGE2,A)-0.08)*0.001/9.92 : 0.081))}")
    old = "G1 A C TABLE { V(A, C) } ( (-1,-1n)(0,0)(1m,1) (2m,10) (3m,1000) )"
    assert old in text
    text = text.replace(old, "B1 A C I={v(A,C)<-1 ? -1n : (v(A,C)<0 ? v(A,C)*1n : (v(A,C)<1m ? v(A,C)*1000 : (v(A,C)<2m ? 1+(v(A,C)-1m)*9000 : (v(A,C)<3m ? 10+(v(A,C)-2m)*990000 : 1000))))}")
    path.write_text(text)
    return path


def deck_text(cap_u: float, cww_p: float, off_r: float, gmin: float = 1e-7,
              esl_n: float = .125, itl4: int = 100000) -> str:
    deck = (f6.D13 / "decks/F6.cir").read_text()
    deck = deck.replace(".include params.inc", f".include params.inc\n.options itl4={itl4} gmin={gmin}")
    old = ".model D6D D(Is=1u N=1 Rs=0.05 Cjo=20p Tt=0)\nDoffl gdl3 offl D6D"
    assert old in deck
    deck = deck.replace(old, f".include {f6.PMEG}\nXDoffl gdl3 offl PMEG6030EP")
    deck = deck.replace("Doffh gdh3 offh D6D", "XDoffh gdh3 offh PMEG6030EP")
    deck = deck.replace("1.34482758621", str(off_r))
    additions = [f".include {model()}"]
    for letter, source in (("l", "s_ls"), ("h", "sw")):
        old_driver = next(s for s in deck.splitlines() if s.startswith(f"Bg{letter} "))
        # Branch return terminals matter: a B source returning to SOURCE would
        # keep the negative rail unloaded and manufacture a false pass.
        new_driver = (f"Bg{letter}off gd{letter} n{letter} I={{v(gd{letter},n{letter})*(1-v(g{letter}_cmd,{source})/VDRV)/ROL}}\n"
                      f"Bg{letter}on gd{letter} p{letter} I={{v(gd{letter},p{letter})*v(g{letter}_cmd,{source})/(VDRV*ROH)}}")
        deck = deck.replace(old_driver, new_driver)
        additions.extend([
            f"Vspan{letter} raw{letter} n{letter} 17",
            f"Rsp{letter} raw{letter} p{letter} 1",
            f"Cspan{letter} p{letter} n{letter} 47u",
            f"Rbleed{letter} p{letter} {source} 4.99k",
            f"Rtop{letter} {source} fb{letter} 6.12k",
            f"Rbot{letter} fb{letter} n{letter} 10k",
            # Evaluate the behavioural control poles in a local zero frame.
            # A direct G-source carries cathode current into the floating port.
            # All state nodes stay in a local zero frame.
            f"Efb{letter} fs{letter} 0 fb{letter} n{letter} 1",
            # SLVM672 active-region equations. Clamp-free state is permitted
            # only when st1 remains within 0..80mV for the entire record.
            # The verdict below rejects a row outside that domain.
            f"Vref{letter} ref{letter} 0 1.24",
            f"Gerr{letter} 0 st1{letter} fs{letter} ref{letter} 4",
            f"Rst1{letter} st1{letter} 0 1",
            f"Cst1{letter} st1{letter} 0 159u",
            f"Gst2{letter} 0 st2{letter} st1{letter} 0 1",
            f"Rst2{letter} st2{letter} 0 1",
            f"Cst2{letter} st2{letter} 0 80n",
            f"Gsh{letter} {source} n{letter} st2{letter} 0 1",
            f".meas tran st1{letter}_min MIN v(st1{letter})",
            f".meas tran st1{letter}_max MAX v(st1{letter})",
            f".meas tran st2{letter}_min MIN v(st2{letter})",
            f".meas tran st2{letter}_max MAX v(st2{letter})",
            f"Lneg{letter} n{letter} ne{letter} {esl_n}n",
            f"Rneg{letter} ne{letter} nc{letter} 20m",
            f"Cneg{letter} nc{letter} {source} {cap_u}u",
            f"Lhf{letter} n{letter} he{letter} 0.1n",
            f"Rhf{letter} he{letter} hc{letter} 50m",
            f"Chf{letter} hc{letter} {source} 100n",
            f".meas tran n{letter}_at_edge FIND par('v(n{letter})-v({source})') AT={{T1+DT}}",
            f".meas tran n{letter}_least_negative MAX par('v(n{letter})-v({source})') from={{T1}} to={{T1+DT+0.75u}}",
            f".meas tran n{letter}_partner_max MAX par('v(n{letter})-v({source})') from={{T1+DT}} to={{T1+DT+0.75u}}",
        ])
    additions.append(f"Cww nh nl {cww_p}p")
    return deck.replace(".end", "\n".join(additions) + "\n.end")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap-u", type=float, default=10)
    ap.add_argument("--cww-p", type=float, default=3,
                    help="WE 750320775 typical; sweep separately, not a maximum")
    ap.add_argument("--esl-n", type=float, default=.125,
                    help="aggregate reservoir layout scenario, not measured")
    ap.add_argument("--itl4", type=int, default=100000)
    ap.add_argument("--off-r", type=float, default=1.0,
                    help="physical discharge resistor; old F6 used 1.3448 parallel 3.9")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--gmin", type=float, default=1e-7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="candidate")
    args = ap.parse_args()
    if min(args.cap_u, args.cww_p, args.off_r, args.workers) <= 0:
        ap.error("positive model values required")
    out = HERE / args.tag
    out.mkdir(exist_ok=True)
    (out / ".gitignore").write_text("runs/\n")
    deck = out / "F6.cir"
    deck.write_text(deck_text(args.cap_u, args.cww_p, args.off_r, args.gmin, args.esl_n, args.itl4))
    f6.OUT = out
    f6.MATRICES["B"] = D2 / "legB-h0-corr-n19.matrix.txt"
    jobs = f6.jobs((27, 100, 150)) + f6.jobs((27, 100, 150), "startup")
    if args.limit:
        jobs = jobs[:args.limit]
    original_run = f6.run_d2.run

    def run_with_record(*a, **kw):
        result = original_run(*a, **kw)
        (kw["keep"] / "measurements.json").write_text(json.dumps(result["meas"]))
        return result

    f6.run_d2.run = run_with_record

    def one(job):
        row = f6.one(job)
        leg, temp, (case, vbus, il, dt), direction, esl = job
        name = f"{leg}_T{temp}_{case}_v{vbus}_i{il}_d{direction}_dt{dt}_esl{esl}"
        measurements = json.loads((out / "runs" / name / "measurements.json").read_text())
        keys = ("nl_at_edge", "nh_at_edge", "nl_least_negative", "nh_least_negative", "nl_partner_max", "nh_partner_max")
        row.update({k: measurements.get(k) for k in keys})
        # DECISIONS specifies the partner's edge; retain the earlier outgoing
        # turn-off peak separately rather than changing the requirement.
        row["rail_pass"] = all(measurements.get(k, 0) < -1.6 for k in ("nl_at_edge", "nh_at_edge", "nl_partner_max", "nh_partner_max"))
        row["shunt_active_region"] = all(0 < measurements.get(f"st{stage}{x}_min", -1) <= measurements.get(f"st{stage}{x}_max", 1) < .08 for x in "lh" for stage in (1, 2))
        row["pass_candidate"] = row.get("pass_hot", False) and row["rail_pass"] and row["shunt_active_region"]
        (out / "runs" / name / "verdict.json").write_text(json.dumps(row, indent=2) + "\n")
        print(name, row["status"], row["pass_candidate"], flush=True)
        return row

    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, jobs))
    (out / "results.json").write_text(json.dumps(rows, indent=1) + "\n")
    complete = [r for r in rows if r["status"] == "complete"]
    summary = {"model_status": "candidate, unqualified transformer Cww and upstream source",
               "args": vars(args), "cases": len(rows), "complete": len(complete),
               "hot_pass": sum(r.get("pass_hot", False) for r in rows),
               "rail_pass": sum(r["rail_pass"] for r in rows),
               "shunt_active_region": sum(r["shunt_active_region"] for r in rows),
               "pass_candidate": sum(r["pass_candidate"] for r in rows),
               "max_off_V": max((r["off_V"] for r in complete), default=None),
               "max_die_VDS_V": max((r["vds_pk"] for r in complete), default=None),
               "inputs_sha256": {str(p.relative_to(HERE.parents[6])): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), deck, *f6.MATRICES.values(), f6.PMEG, model())}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
