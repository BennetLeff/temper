"""Shared loaders for the native-21 coupling audit (validation-results/13-coupling).

Read-only on every input. Inputs (stage 32, tag native21s32, board 2fb346dc...):
  native-21/frozen/default.net            netlist (components, ato addresses, nets)
  native-21/layout/parts.json             ref -> ato path, footprint, legacy layout group
  native-21/placement.json                ato path -> [x, y, rot]
  native-21/verification/native21s32-all-copper.json.gz   every copper primitive (pads, tracks, vias, zone fills)
  validation-plan/enclosure-fit/native21-courtyards.json  courtyard boxes from the stage-32 chain (checked against the pads)
  native-21/layout/domains.py, rules21.py  isolation domain / potential group per net
History inputs come from the stage tags with `git show TAG:path` (read-only).
"""
import gzip
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
PS = HERE.parents[2]                       # zapote/power-stage-120v
REPO = PS.parents[1]
N21 = PS / "native-21"
VR = PS / "validation-results"
REL = "zapote/power-stage-120v"
BOARD_SHA = "2fb346dc8277e4295d8ef88effabdcc71dcd363fcaa93604800ddc2872fbfa4e"
TAG = "native21s32"
DUMP = N21 / "verification/native21s32-all-copper.json.gz"
S32_BUILD = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/s32/b2")
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")

GROUPS = [
    ("G01", "mains_emi_rectifier"), ("G02", "dc_link_clamp"), ("G03", "bridge_power_stage"),
    ("G04", "resonant_tank"), ("G05", "gate_drive"), ("G06", "bias_supplies"),
    ("G07", "bias_monitors_isolation"), ("G08", "sense_protect"), ("G09", "ct_zc_detect"),
    ("G10", "selv_interface_aux"),
]
GIDS = [g for g, _ in GROUPS]
GNAME = dict(GROUPS)


# ------------------------------------------------------------------ output
def rnd(o, nd=4):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {str(k): rnd(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [rnd(v, nd) for v in o]
    return o


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(rnd(obj), indent=1, sort_keys=True) + "\n"
    (OUT / name).write_text(txt)
    return hashlib.sha256(txt.encode()).hexdigest()


def load(name):
    return json.loads((OUT / name).read_text())


class Controls:
    """Collects control checks; exit 1 if any failed."""

    def __init__(self):
        self.rows = []

    def check(self, name, ok, detail=""):
        self.rows.append({"control": name, "pass": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
        return ok

    def ok(self):
        return all(r["pass"] for r in self.rows)

    def finish(self):
        if not self.ok():
            print("CONTROL FAILED")
            sys.exit(1)


def load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def git_show(tag, rel):
    """Read a file at a stage tag (read-only)."""
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{tag}:{REL}/{rel}"], capture_output=True, text=True)
    if r.returncode:
        raise FileNotFoundError(f"{tag}:{rel}")
    return r.stdout


# ------------------------------------------------------------------ netlist
def parse_netlist(text):
    """-> comps {ref: {mpn, desc, path}}, nets {name: [(ref, pin), ...]}"""
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\)(.*?)\(tstamps "[^"]+"\)\)', text, re.S):
        ref, body = m.group(1), m.group(2)
        part = re.search(r'\(part "([^"]*)"\)', body)
        desc = re.search(r'\(description "([^"]*)"\)', body)
        names = re.search(r'\(names "[^"]*::([^"]*)"\)', body)
        fp = re.search(r'\(footprint "([^"]*)"\)', body)
        comps[ref] = {"mpn": part.group(1) if part else "", "desc": desc.group(1) if desc else "",
                      "path": names.group(1) if names else "", "fp": fp.group(1) if fp else ""}
    nets = {}
    i = text.index("(nets")
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]+)"\)((?:\s*\(node[^\n]*\))*)', text[i:]):
        nets[m.group(1)] = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2))
    return comps, nets


def bom(tag=None):
    """ref -> MPN from the frozen BOM (default.csv 'Comment'); the netlist's libsource part is the ato type default."""
    import csv
    import io
    t = git_show(tag, "native-21/frozen/default.csv") if tag else (N21 / "frozen/default.csv").read_text()
    out = {}
    for r in csv.DictReader(io.StringIO(t)):
        for d in r["Designator"].split(","):
            out[d.strip()] = r["Comment"].strip()
    return out


def netlist(tag=None):
    t = git_show(tag, "native-21/frozen/default.net") if tag else (N21 / "frozen/default.net").read_text()
    comps, nets = parse_netlist(t)
    b = bom(tag)
    for r, c in comps.items():
        c["mpn"] = b.get(r, c["mpn"])
    return comps, nets


# ------------------------------------------------------------------ group assignment (stage 32)
def assign_19c(path, old_group):
    """The stage-19c rule of 11-candidates/scripts/map_groups.py:assign, copied verbatim."""
    if path in ("j_mains", "f1", "rv1", "cx1", "cx2", "rb1a", "rb1b", "l1", "cy1", "cy2", "br1", "j_pe"):
        return "G01"
    if path in ("c_bus1", "c_bus2", "tvs_bus", "tvs_bus_b", "r_bus1", "r_bus2") or path.startswith(("link_pos.", "link_neg.")):
        return "G02"
    if path.startswith("c_hf_") or (path.startswith("leg_") and path.split(".", 1)[1] in ("q_high", "q_low", "c_snub_h", "c_snub_l")):
        return "G03"
    if path.startswith("c_res") or path.startswith("r_crb") or path in ("j_coil", "j_coil_return"):
        return "G04"
    if path.startswith("leg_"):
        return "G05"
    if path in ("ps_gate", "j_tco", "c_v15") or path.startswith("bias_ls."):
        return "G06"
    if path.startswith(("bias_ha.", "bias_hb.")):
        return "G07" if ".monitor." in path else "G06"
    if path.startswith("monitor_ls.") or old_group == "bias_common":
        return "G07"
    if path == "r_shunt" or old_group == "hot_protect":
        return "G08"
    if old_group in ("ct_selv", "line_zc"):
        return "G09"
    if path in ("j_selv", "ps_selv", "r_fe", "f_blw", "j_blw_ac") or path.startswith("c_ref_xfer"):
        return "G10"
    return None


# Stage 20-32 additions. Each rule names why; parts it touches are listed in assignment.json.
VERDICT_PATHS = ("bias_ha.link", "bias_ha.clink1", "bias_ha.clink2", "bias_hb.verdict", "bias_hb.cver1", "bias_hb.cver2")


def assign_32(path, old_group):
    """-> (group, rule). Stage-19c rule first, with these stage 20-32 rules ahead of it."""
    if path.startswith("hb."):
        return "G07", "R1 hb.* = stage-30 bias-monitor heartbeat (replaces the bias_common notice stages, DECISIONS 33)"
    if path in VERDICT_PATHS:
        return "G07", "R2 rail-verdict isolator + its caps (U43 / U44, stage 30): monitoring function, not supply (19c rule would say G06)"
    if path == "r_blw":
        return "G10", "R3 R130 = F2 blower-tap limiter in series with F2 / J11 (stage 28, DECISIONS 30)"
    if path in ("r_bf", "c_bf"):
        return "G09", "R4 BUS_FAULT RC R134 / C167 sits at U13.A, the fault OR (stage 30); ambiguous G08 / G09, see electrical vote"
    g = assign_19c(path, old_group)
    return g, "R0 stage-19c rule (map_groups.assign)"


def parts(tag=None):
    t = git_show(tag, "native-21/layout/parts.json") if tag else (N21 / "layout/parts.json").read_text()
    return json.loads(t)


def placement(tag=None):
    t = git_show(tag, "native-21/placement.json") if tag else (N21 / "placement.json").read_text()
    return json.loads(t)


def assignment(tag=None):
    """ref -> group for a stage's parts.json (stage-32 rule)."""
    out = {}
    for p in parts(tag):
        g, _ = assign_32(p["path"], p["group"])
        if g:
            out[p["ref"]] = g
    return out


# ------------------------------------------------------------------ nets: domains and classes
def domains():
    sys.path.insert(0, str(N21 / "layout"))
    d = load_mod(N21 / "layout/domains.py", "dom21_cpl")
    r = load_mod(N21 / "layout/rules21.py", "rules21_cpl")
    return d.domain, r


RAIL = {"n_ls", "selv_gnd", "v3v3", "n_ha", "n_hb", "v15_ls", "hot5", "p_ha", "p_hb", "v24_raw", "ls_v5",
        "bias_ha.monitor-v5", "bias_hb.monitor-v5", "ocp_kelvin_p", "v15_selv", "pe", "ref25"}
POWER = {"ac_l_in", "ac_n_in", "l_f", "l_filt", "n_filt", "bus_p", "hv_ret", "leg_ret", "sw_a", "sw_b", "res_a",
         "coil_feed", "blw_l", "blw_lr", "tco_l", "xbleed_mid", "busbleed_mid", "crbleed_1", "crbleed_2", "crbleed_3",
         "rect_p", "rect_n"}
PLANE_POWER = {"leg_ret", "hv_ret", "bus_p", "sw_a", "sw_b"}     # power nets that are also poured reference planes
SENSE_PAT = re.compile(r"(ocp_kelvin_n|ocp_node|ocp_thresh|ovp_thresh|vsense_in|vdiv_|vbus_|ct_s1|ct_s2|ct_sense_mon|"
                       r"ct_mon|ct_ref|ct_oc|line_zc_raw|led1|led2|r1mid|r2mid|hot5_uv|-uv$|-ov$|-span|-halfref|-ref$|"
                       r"-fb$|-fbm$|split-fb|ldo_nr)")


def net_class(n):
    if n in RAIL:
        return "rail"
    if n in POWER:
        return "power"
    if SENSE_PAT.search(n):
        return "sense"
    return "signal"


# ------------------------------------------------------------------ geometry
def dump(path=DUMP):
    return json.load(gzip.open(path))


def courtyards():
    return json.loads((PS / "validation-plan/enclosure-fit/native21-courtyards.json").read_text())


def pads_board():
    return json.loads((S32_BUILD / "pads-board.json").read_text())


def shapely():
    import shapely.geometry as sg
    import shapely.ops as so
    return sg, so


def copper_geoms(d, sg, so, nets=None):
    """-> {(net, layer): geometry} union of tracks, vias, pads and zone fills."""
    acc = defaultdict(list)
    for x in d["primitives"]:
        n = x.get("net")
        if not n or (nets is not None and n not in nets):
            continue
        L = x["layer"]
        k = x["kind"]
        if k == "track":
            g = sg.LineString([x["start"], x["end"]]).buffer(x["width_mm"] / 2, cap_style=1)
        elif k == "via":
            g = sg.Point(x["centre"]).buffer(x["diameter_mm"] / 2, 12)
        elif k == "zone":
            g = sg.Polygon(x["shell"], x.get("holes") or [])
        elif k == "pad":
            g = sg.Polygon(x["shell"]) if x.get("shell") and len(x["shell"]) >= 3 else sg.Point(x["centre"]).buffer(0.3)
        else:
            continue
        if not g.is_valid:
            g = g.buffer(0)
        acc[(n, L)].append(g)
    return {k: so.unary_union(v) for k, v in acc.items()}


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
