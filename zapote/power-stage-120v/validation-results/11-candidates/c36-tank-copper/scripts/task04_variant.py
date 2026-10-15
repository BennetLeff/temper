"""Task-04 cases on a variant's power copper in a scratch unit (B3's rows on the nets stage 41 touches); the other
cases are the s40 fields.   python3 task04_variant.py NAME [NAME...]"""
import os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
R = Path(os.environ["S41_RUNS"])  # run root holding v-NAME/ and s40-task04/
U = Path(__file__).resolve().parents[4]
S = U / "validation-results/04-board-current-thermal/round5-native21"
ROWS_ALL = {"sw_a", "sw_a_low", "res_a", "coil_feed", "ac_n_main", "ac_l_main"}
ROWS = {"sw_b_high", "sw_b_low", "leg_a_18p7", "leg_b_18p7", "hv_mixed_a", "hv_mixed_b", "bus_mixed_q2", "bus_mixed_q5"}
sys.path.insert(0, str(S)); import run_cases
jobs = []
OZ3 = os.environ.get("NATIVE21_STACKUP")
if OZ3: ROWS |= ROWS_ALL
for v in sys.argv[1:]:
    unit = R / (f"unit-{v}-oz3" if OZ3 else f"unit-{v}"); st = unit / "validation-results/04-board-current-thermal/round5-native21"
    (st / "outputs").mkdir(parents=True, exist_ok=True); (st / "inputs").mkdir(exist_ok=True)
    for l in ("validation-plan", "native-21"):
        if not (unit / l).exists(): os.symlink(U / l, unit / l)
    shutil.copy(S / "run_board.py", st)
    shutil.copy(R / f"v-{v}/power_copper.json.gz", st / "inputs/power_copper.json.gz")
    for f in (R / "s40-task04").glob("*-pl*"):
        shutil.copy(f, st / "outputs" / f.name)
    for name, net, src, draws, sinks, _ in run_cases.CASES + [("ac_n_main", "ac_n_in", ["J1.2:15"], [], ["L1.2"], ""), ("ac_l_main", "ac_l_in", ["J1.1:15"], [], ["F1.1"], "")]:
        if name not in ROWS: continue
        pitch = "0.0625" if net in run_cases.FINE else "0.125"
        label = f"{name}-p{pitch.replace('.', '')}-pl18"
        cmd = [sys.executable, str(st / "run_board.py"), "--net", net, "--name", label, "--pitch", pitch, "--plating", "18"]
        for s_ in src: cmd += ["--source", s_]
        for d in draws: cmd += ["--draw", d]
        for k in sinks: cmd += ["--sink", k]
        jobs.append((v, label, cmd, st))
def one(j):
    v, label, cmd, st = j
    r = subprocess.run(cmd, cwd=st, capture_output=True, text=True, env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    return v, label, r.returncode, r.stdout.strip()[-200:], r.stderr[-300:]
with ThreadPoolExecutor(4) as ex:
    for v, label, rc, out, err in ex.map(one, jobs):
        print(v, label, rc, out, err if rc else "", flush=True)
