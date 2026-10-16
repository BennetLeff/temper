#!/usr/bin/env python3
"""Per-pin absolute-maximum gate (a new class of model gap, found 2026-10-15).

    python3 -I native-21/layout/gates/pin_absmax.py [--root UNIT] [--registry pin_absmax_registry.json]
        [--netlist frozen/default.net] [--report OUT.json] [--expect-fail pin_absmax_expected.json]
        [--fail-undeclared] [--fail-fault] [--verify-datasheets DIR] [--list]

Why: four TPS70950 LDOs (U3, U37, U38, U39) had EN tied to IN, at up to 15.46 V and 17.43 V. TI SBVS186H gives VEN abs
max 7 V (6.1 p.4) and says "Do not connect EN to VIN" (7.4 p.13). The datasheet ledger checks part-level stresses and audit.rs
checks values; nobody compared a pin's net voltage with that pin's absolute maximum. This gate does, statically (stdlib only,
no board data, no simulation): netlist + registry in, a verdict per IC pin out.

Model (all in pin_absmax_registry.json; every number carries a citation):

  nets   Each net has a voltage range [lo, hi] relative to a named reference net (`ref`); a net with no ref is the root of a
         galvanic frame (LEG_RET, SELV_GND). Kinds:
           root     frame root, range [0, 0] by definition
           rail     declared range from a rail model, a DECISIONS figure or a datasheet row (`cite` required)
           divider  tap of a series resistor chain top -> tap -> bottom, from the frozen BOM values and a tolerance table;
                    the chain topology is checked against the netlist (a stale registry fails, it does not pass)
           logic    output swing [0, supply] relative to the driver's ground; `sources` (IC pins) are checked against the
                    part registry: the pin is an output, and its supply / ground pins sit on the declared nets
           follow   the same range as a source net through a series resistor (RC filter, gate resistor)
           hull     a net whose voltage is a convex combination of listed nets' (open-collector node, half-bridge midpoint)
           equal    the same voltage as another net, by a datasheet statement (TPS7A4700 NR pin = VOUT in ANY-OUT mode)
         Any other net is UNDECLARED. A pin on an undeclared net is a WARN and counts against coverage.
         A rail may carry a `fault` envelope (a protection clamp's trip band): checked separately, WARN only.
  parts  Per IC MPN: package pin -> function, and per function the absolute maximum (and recommended range) as
         V(pin) - V(reference pin) in [min, max], each with the datasheet page and a verbatim row `quote`.
  check  For each pin, V(pin) - V(reference pin) is evaluated as an interval with the common-ancestor trick (shared chain
         links cancel, so v15_ls - n_ls is the rail span, not the span widened by the neg-rail spread):
           over an absolute maximum        FAIL
           inside abs max, outside rec     WARN
           inside both, but over abs max under a `fault` envelope    WARN (FAULT)
           net (or reference net) undeclared, or the two nets share no frame    WARN (UNDECLARED / FRAME); with --fail-undeclared: FAIL
           a limit with no page or no quote, or a net with no citation    FAIL (UNCITED)

--expect-fail FILE lists known violations ("U3.3": reason); the exit status is 1 only on a FAIL that is not listed
(and, with --fail-stale, on a listed one that no longer fails). The report keeps every FAIL either way, and
report["failures"] is what the scorecard gate `pin_absmax` reads (True only when it is empty).

--verify-datasheets DIR checks, with pdftotext, that every limit's `quote` really sits on its cited `page` of the PDF
named in the part's `datasheet.file` (whitespace and dash-insensitive). Offline use skips it.

Limits (honest): static and DC. Switching overshoot, ringing, ESD, surge and transient rows are not modelled
(the registry names the rows it uses). Divider loading by comparator bias current is ignored. Pins whose datasheet gives no
voltage row (the TL431 REF pin, the LM4050 cathode, push-pull comparator outputs) are counted as covered but not checked. A rail range is only as good
as its cited model.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]                                    # zapote/power-stage-120v
EPS = 1e-9
IC_PREFIX = ("U", "Q")


# ------------------------------------------------------------------------------------------------------------- inputs
def parse_netlist(text):
    """{net: [(ref, pin), ...]} from a KiCad (export ...) netlist."""
    nets, cur = {}, None
    for line in text.splitlines():
        m = re.match(r'\s*\(net \(code "\d+"\) \(name "([^"]*)"\)', line)
        if m:
            cur = m.group(1)
            nets[cur] = []
        m = re.search(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', line)
        if m and cur is not None:
            nets[cur].append((m.group(1), m.group(2)))
    return nets


def load_bom(csv_path, resolved_path):
    """({designator: MPN} from default.csv Comment, {designator: (value, mpn)} from resolved-components.json)."""
    mpn = {}
    for row in csv.DictReader(open(csv_path)):
        for d in row["Designator"].split(","):
            mpn[d.strip()] = row["Comment"]
    val = {}
    for c in json.load(open(resolved_path))["components"]:
        a = c["attributes"]
        val[a["designator"]] = (a.get("value"), a.get("mpn"))
    return mpn, val


def parse_ohms(s):
    m = re.fullmatch(r"([\d.]+)\s*([kM]?)ohm", s or "")
    if not m:
        raise ValueError(f"unparsable resistor value {s!r}")
    return float(m.group(1)) * {"": 1.0, "k": 1e3, "M": 1e6}[m.group(2)]


# --------------------------------------------------------------------------------------------------------- intervals
def iadd(a, b):
    return (a[0] + b[0], a[1] + b[1])


def isub(a, b):
    return (a[0] - b[1], a[1] - b[0])


def ihull(items):
    return (min(i[0] for i in items), max(i[1] for i in items))


# --------------------------------------------------------------------------------------------------------- net model
class NetError(Exception):
    """A registry error (stale topology, missing citation, cycle): reported as a FAIL, never silently passed."""


class NetModel:
    """Voltage relations between nets. Node types:
      frame nodes  root / rail: an interval relative to a parent frame node (chains to a root)
      divider      tap = bottom + k (top - bottom), k from the resistor tolerances
      conv         V(net) lies in the convex hull of the member nets' voltages (logic outputs, open-collector nodes);
                   differences against a member are then exact, not widened by the members' own spread
      alias        follow: the same voltage as the source net
    diff(a, b) = V(a) - V(b) as an interval, or None when a net is undeclared or the two share no frame."""

    def __init__(self, reg, nets, val, mode="op"):
        self.reg, self.nets, self.val, self.mode = reg, nets, val, mode
        self.decl = reg["nets"]
        self.tol = reg.get("resistor_tolerance", {})
        self._k = {}

    def node(self, name):
        d = self.decl.get(name)
        if d is None:
            return None
        k = d["kind"]
        if k == "root":
            return ("root",)
        if k == "rail":
            lo, hi = d["lo"], d["hi"]
            if self.mode == "fault" and "fault" in d:
                lo, hi = d["fault"].get("lo", lo), d["fault"].get("hi", hi)
            if d["ref"] not in self.decl:
                raise NetError(f"net {name}: reference {d['ref']} is undeclared")
            return ("rail", d["ref"], lo, hi)
        if k == "divider":
            return ("div", d["top"], d["bottom"], *self.k_of(name, d))
        if k == "logic":
            return ("conv", [d["ref"], d["supply"]])
        if k == "hull":
            return ("conv", list(d["nets"]))
        if k in ("follow", "equal"):
            return ("alias", d["src"] if k == "follow" else d["to"])
        raise NetError(f"net {name}: unknown kind {k!r}")

    def declared(self, name):
        return self.node(name) is not None

    def rtol(self, des):
        v, mpn = self.val[des]
        for pre, t in self.tol.items():
            if pre != "_default" and mpn and mpn.startswith(pre):
                return parse_ohms(v), t["tol"]
        return parse_ohms(v), self.tol.get("_default", {}).get("tol", 0.05)

    def k_of(self, name, d):
        if name not in self._k:
            rt = [self.rtol(r) for r in d["r_top"]]
            rb = [self.rtol(r) for r in d["r_bot"]]
            Rt = (sum(v * (1 - t) for v, t in rt), sum(v * (1 + t) for v, t in rt))
            Rb = (sum(v * (1 - t) for v, t in rb), sum(v * (1 + t) for v, t in rb))
            self._k[name] = (Rb[0] / (Rt[1] + Rb[0]), Rb[1] / (Rt[0] + Rb[1]))
        return self._k[name]

    @staticmethod
    def kmul(k, iv):
        """k (a positive interval) times the interval iv."""
        c = [k[0] * iv[0], k[0] * iv[1], k[1] * iv[0], k[1] * iv[1]]
        return (min(c), max(c))

    def check_registry(self):
        """Static consistency of the derived declarations against the netlist; returns a list of error strings."""
        errs = []
        for name, d in self.decl.items():
            try:
                if d["kind"] == "divider":
                    self.check_divider_topology(name, d)
                elif d["kind"] == "follow":
                    self.check_follow(name, d)
                elif d["kind"] == "equal":
                    if d["to"] not in self.decl:
                        errs.append(f"net {name}: `to` net {d['to']} is undeclared")
                elif d["kind"] in ("logic", "hull"):
                    for m in ([d["ref"], d["supply"]] if d["kind"] == "logic" else d["nets"]):
                        if m not in self.decl:
                            errs.append(f"net {name}: member {m} is undeclared")
                elif d["kind"] == "rail":
                    self.node(name)
            except NetError as e:
                errs.append(str(e))
        return errs

    def check_follow(self, name, d):
        for r in d["via"]:
            ns = [n for n, members in self.nets.items() if any(m[0] == r for m in members)]
            if sorted(ns) != sorted([name, d["src"]]):
                raise NetError(f"net {name}: `via` resistor {r} sits on {ns}, not between {d['src']} and {name}")

    def check_divider_topology(self, name, d):
        """top -R-> n1 -R-> ... -> tap -R-> ... -> bottom, through resistors only; intermediate nodes carry no other
        resistive path (capacitors are DC-open; the tap may also feed IC pins, taken as high impedance)."""
        top, bot = d["top"], d["bottom"]
        order = list(d["r_top"]) + list(d["r_bot"])
        if not d["r_top"] or not d["r_bot"]:
            raise NetError(f"net {name}: divider needs top and bottom resistors")
        node = top
        for i, r in enumerate(order):
            pins = [n for n, members in self.nets.items() if any(m[0] == r for m in members)]
            if len(pins) != 2 or node not in pins:
                raise NetError(f"net {name}: divider resistor {r} does not continue the chain from {node} (nets {pins})")
            nxt = [p for p in pins if p != node][0]
            if i == len(d["r_top"]) - 1 and nxt != name:
                raise NetError(f"net {name}: last top resistor {r} lands on {nxt}, not on the tap")
            if i == len(order) - 1 and nxt != bot:
                raise NetError(f"net {name}: bottom resistor {r} lands on {nxt}, not on {bot}")
            if nxt not in (name, bot):                                   # an intermediate node
                for ref, pin in self.nets[nxt]:
                    if ref not in order and ref[0] != "C":
                        raise NetError(f"net {name}: intermediate node {nxt} also carries {ref}.{pin}")
            node = nxt
        allowed = set(d.get("loads", []))
        for ref, pin in self.nets.get(name, []):
            if ref in order or ref[0] == "C":
                continue
            if f"{ref}.{pin}" not in allowed and ref[0] not in IC_PREFIX:
                raise NetError(f"net {name}: divider tap also carries {ref}.{pin} (list it in `loads` if it is high impedance)")

    # -- frame arithmetic ----------------------------------------------------------------------------------------
    def chain(self, name):
        """[(net, interval relative to its parent), ...] from `name` up to its anchor: the first node that is not a rail
        (a root, or a conv / divider / alias node a frame hangs from, such as SW_A); the anchor carries (0, 0)."""
        out, seen = [], set()
        cur = name
        while True:
            if cur in seen:
                raise NetError(f"net {name}: reference cycle at {cur}")
            seen.add(cur)
            nd = self.node(cur)
            if nd is None:
                return None
            if nd[0] != "rail":
                out.append((cur, (0.0, 0.0)))
                return out
            out.append((cur, (nd[2], nd[3])))
            cur = nd[1]

    def up_to(self, x, target):
        """Sum of the rail intervals from x up to `target` when target is on x's chain, else None."""
        ch = self.chain(x)
        if ch is None:
            return None
        acc = (0.0, 0.0)
        for n, iv in ch:
            if n == target:
                return acc
            acc = iadd(acc, iv)
        return None

    def diff(self, a, b, _depth=0):
        """V(a) - V(b) as an interval, or None when undeclared / no common frame."""
        if _depth > 40:
            raise NetError(f"declaration cycle through {a} / {b}")
        if a == b:
            return (0.0, 0.0) if self.declared(a) else None
        na, nb = self.node(a), self.node(b)
        if na is None or nb is None:
            return None
        d = _depth + 1
        if na[0] != "rail" and nb[0] == "rail":                  # b hangs from a: exact, no widening
            u = self.up_to(b, a)
            if u is not None:
                return (-u[1], -u[0])
        if nb[0] != "rail" and na[0] == "rail":
            u = self.up_to(a, b)
            if u is not None:
                return u
        if na[0] == "alias":
            return self.diff(na[1], b, d)
        if nb[0] == "alias":
            return self.diff(a, nb[1], d)
        if na[0] == "conv":
            items = [self.diff(m, b, d) for m in na[1]]
            return None if any(i is None for i in items) else ihull(items)
        if nb[0] == "conv":
            r = self.diff(b, a, d)
            return None if r is None else (-r[1], -r[0])
        if na[0] == "div":
            top, bot, kmin, kmax = na[1:]
            D = self.diff(top, bot, d)
            if D is None:
                return None
            kD = self.kmul((kmin, kmax), D)
            if b == bot:
                return kD
            if b == top:
                return self.kmul((kmin - 1, kmax - 1), D)
            rb = self.diff(bot, b, d)
            return None if rb is None else iadd(rb, kD)
        if nb[0] == "div":
            r = self.diff(b, a, d)
            return None if r is None else (-r[1], -r[0])
        ca, cb = self.chain(a), self.chain(b)
        names_b = {n: i for i, (n, _) in enumerate(cb)}
        for ia, (n, _) in enumerate(ca):
            if n in names_b:
                sa = (0.0, 0.0)
                for _, iv in ca[:ia]:
                    sa = iadd(sa, iv)
                sb = (0.0, 0.0)
                for _, iv in cb[:names_b[n]]:
                    sb = iadd(sb, iv)
                return isub(sa, sb)
        anchor_a, anchor_b = ca[-1][0], cb[-1][0]
        if self.node(anchor_a)[0] != "root":                     # a hangs from a conv / divider node: go through it
            sa = (0.0, 0.0)
            for _, iv in ca[:-1]:
                sa = iadd(sa, iv)
            r = self.diff(anchor_a, b, d)
            return None if r is None else iadd(sa, r)
        if self.node(anchor_b)[0] != "root":
            sb = (0.0, 0.0)
            for _, iv in cb[:-1]:
                sb = iadd(sb, iv)
            r = self.diff(a, anchor_b, d)
            return None if r is None else isub(r, sb)
        return None


# --------------------------------------------------------------------------------------------------------- the check
def normalise(s):
    return re.sub(r"\s+", "", s.replace("–", "-").replace("−", "-").replace("—", "-"))


def pin_map(reg, mpn):
    p = reg["parts"].get(mpn)
    return p["pins"] if p else None


def check(root, reg, netlist_text, mpn_of, val, expect=None, fail_undeclared=False):
    nets = parse_netlist(netlist_text)
    node_net = {}
    for n, members in nets.items():
        for ref, pin in members:
            node_net[(ref, pin)] = n
    errors, rows, notes = [], [], []
    models = {m: NetModel(reg, nets, val, m) for m in ("op", "fault")}
    errors += models["op"].check_registry()

    # -- citations of the registry itself
    for name, d in reg["nets"].items():
        if not str(d.get("cite", "")).strip():
            errors.append(f"UNCITED net {name}: no `cite`")
        if d["kind"] == "rail" and "fault" in d and not str(d["fault"].get("cite", "")).strip():
            errors.append(f"UNCITED fault envelope of net {name}")
        if d["kind"] not in ("root", "rail") and not str(d.get("derive", "")).strip():
            errors.append(f"UNCITED net {name}: derived net without a `derive` line")
    for pre, t in reg.get("resistor_tolerance", {}).items():
        if pre != "_default" and not all(t.get(k) for k in ("file", "page", "quote")):
            errors.append(f"UNCITED resistor tolerance {pre}")
    for mpn, part in reg["parts"].items():
        for fn, f in part["functions"].items():
            for kind in ("limits", "rec"):
                for lim in f.get(kind, []):
                    if not lim.get("page") or not str(lim.get("quote", "")).strip():
                        errors.append(f"UNCITED limit {mpn} {fn} {kind} {lim.get('vs')} min={lim.get('min')} max={lim.get('max')}")
            if (f.get("role") == "nolimit" or (f.get("role") == "out" and not f.get("limits"))) and not (f.get("page") and f.get("quote")):
                errors.append(f"UNCITED no-voltage-limit statement {mpn} {fn}")
            for t in f.get("forbid_tie", []):
                if not t.get("page") or not str(t.get("quote", "")).strip():
                    errors.append(f"UNCITED forbidden tie {mpn} {fn} with {t.get('with')}")
        if not part.get("datasheet", {}).get("file"):
            errors.append(f"UNCITED part {mpn}: no datasheet file")

    # -- logic-source consistency (a stale `sources` list fails)
    for name, d in reg["nets"].items():
        if d["kind"] != "logic":
            continue
        for s in d.get("sources", []):
            des, pin = s.split(".")
            if (des, pin) not in node_net or node_net[(des, pin)] != name:
                errors.append(f"net {name}: source {s} is not on the net")
                continue
            mpn = mpn_of.get(des)
            part = reg["parts"].get(mpn)
            if part is None:
                if not d.get("external"):
                    errors.append(f"net {name}: source {s} ({mpn}) has no part entry (mark the net `external` if off-board)")
                continue
            fn = part["pins"][pin]
            if part["functions"][fn].get("role") != "out":
                errors.append(f"net {name}: source {s} is function {fn}, not an output")
                continue
            sup, gnd = part["functions"][fn]["supply"], part["functions"][fn]["ground"]
            sup_net = node_net.get((des, [p for p, f in part["pins"].items() if f == sup][0]))
            gnd_net = node_net.get((des, [p for p, f in part["pins"].items() if f == gnd][0]))
            if sup_net != d["supply"] or gnd_net != d["ref"]:
                errors.append(f"net {name}: source {s} is supplied from {sup_net} / {gnd_net}, registry says {d['supply']} / {d['ref']}")

    ic_des = sorted((d for d in mpn_of if d[0] in IC_PREFIX), key=lambda s: (s[0], int(re.sub(r"\D", "", s))))
    cov = {"pins_total": 0, "floating_or_nc": 0, "checked": 0, "reference_declared": 0, "nolimit_declared": 0,
           "undeclared": 0, "no_part_data": 0}
    by_part = {}
    for des in ic_des:
        mpn = mpn_of[des]
        part = reg["parts"].get(mpn)
        pins = sorted([p for (r, p) in node_net if r == des], key=lambda p: (len(p), p))
        for pin in pins:
            cov["pins_total"] += 1
            net = node_net[(des, pin)]
            members = nets[net]
            base = {"part": des, "mpn": mpn, "pin": pin, "net": net}
            if part is None:
                cov["no_part_data"] += 1
                rows.append({**base, "status": "NOPART", "note": "MPN has no registry entry"})
                continue
            fn = part["pins"].get(pin)
            if fn is None:
                errors.append(f"{des}.{pin}: pin not in the {mpn} package map")
                continue
            f = part["functions"][fn]
            base["function"] = fn
            if f.get("role") == "nc" or len(members) == 1:
                cov["floating_or_nc"] += 1
                rows.append({**base, "status": "FLOATING", "note": "single-node net or NC pin"})
                continue
            res = {}
            try:
                for m, model in models.items():
                    res[m] = _pin(model, part, des, pin, fn, f, node_net, net)
            except NetError as e:
                errors.append(f"{des}.{pin}: {e}")
                continue
            row = {**base, **_verdict(res, f, fail_undeclared)}
            for t in f.get("forbid_tie", []):
                others = [p for p, g in part["pins"].items() if g == t["with"] and p != pin]
                if any(node_net.get((des, p)) == net for p in others):
                    row.setdefault("violated", [])
                    row["violated"] = [{"kind": "forbidden tie", "vs": t["with"], "iv": None, "min": None, "max": None,
                                        "page": t["page"], "quote": t["quote"]}] + row.get("violated", [])
                    row["status"] = "FAIL"
            rows.append(row)
            st = row["status"]
            if st in ("FAIL", "WARN", "OK", "WARN-FAULT"):
                cov["checked"] += 1
            elif st == "REF":
                cov["reference_declared"] += 1
            elif st == "NOLIMIT":
                cov["nolimit_declared"] += 1
            else:
                cov["undeclared"] += 1
            by_part.setdefault(des, []).append(row)

    fails = [r for r in rows if r["status"] == "FAIL"]
    warns = [r for r in rows if r["status"] in ("WARN", "WARN-FAULT")]
    undecl = [r for r in rows if r["status"] in ("UNDECLARED", "FRAME")]
    expect = expect or {}
    keyf = lambda r: f"{r['part']}.{r['pin']}"
    new = [r for r in fails if keyf(r) not in expect]
    stale = sorted(k for k in expect if k not in {keyf(r) for r in fails})
    denom = cov["pins_total"] - cov["floating_or_nc"]
    cov["coverage_fraction"] = round((cov["checked"] + cov["reference_declared"] + cov["nolimit_declared"]) / denom, 4) if denom else 0.0
    cov["checked_fraction"] = round(cov["checked"] / denom, 4) if denom else 0.0
    cov["denominator"] = denom
    notes_map = reg.get("undeclared_notes", {})
    for r in undecl:
        r["note"] = notes_map.get(r["net"], r.get("note", ""))
    per_mpn = {}
    for r in rows:
        e = per_mpn.setdefault(r["mpn"], {"pins": 0, "floating_or_nc": 0, "checked": 0, "reference": 0, "current_rated": 0, "undeclared": 0, "designators": set()})
        e["pins"] += 1
        e["designators"].add(r["part"])
        e[{"FLOATING": "floating_or_nc", "REF": "reference", "NOLIMIT": "current_rated", "UNDECLARED": "undeclared", "FRAME": "undeclared",
           "NOPART": "undeclared"}.get(r["status"], "checked")] += 1
    for e in per_mpn.values():
        e["designators"] = sorted(e["designators"])
    margins = []
    for r in rows:
        if r["status"] in ("OK", "WARN", "WARN-FAULT") and r.get("headroom_V") is not None:
            h = min(r["headroom_V"], r["fault_headroom_V"] if r.get("fault_headroom_V") is not None else r["headroom_V"])
            margins.append({"pin": f"{r['part']}.{r['pin']}", "function": r["function"], "net": r["net"], "headroom_V": r["headroom_V"],
                            "fault_headroom_V": r.get("fault_headroom_V")})
    margins.sort(key=lambda m: min(m["headroom_V"], m["fault_headroom_V"] if m["fault_headroom_V"] is not None else 1e9))
    return {"errors": errors, "failures": [_slim(r) for r in fails], "per_mpn": per_mpn, "tightest_headroom": margins[:25], "new_failures": [_slim(r) for r in new],
            "stale_expected": stale, "warnings": [_slim(r) for r in warns], "undeclared": [_slim(r) for r in undecl],
            "coverage": cov, "rows": rows, "notes": notes}


def _slim(r):
    return {k: v for k, v in r.items() if k != "all"}


def _pin(model, part, des, pin, fn, f, node_net, net):
    """Evaluate one pin in one mode: list of (limit, interval-or-None) for abs and rec."""
    role = f.get("role")
    if role == "out" and not f.get("limits"):
        role = "nolimit"
    if role in ("ref", "nolimit"):
        # the net must at least be declared (and, for a reference pin, in some frame)
        return {"role": role, "declared": model.declared(net)}
    out = {"role": "lim", "abs": [], "rec": []}
    for kind in ("limits", "rec"):
        for lim in f.get(kind, []):
            vs = lim["vs"]
            rp = [p for p, g in part["pins"].items() if g == vs]
            rnets = {node_net.get((des, p)) for p in rp if (des, p) in node_net}
            rnets.discard(None)
            if len(rnets) != 1:
                raise NetError(f"reference function {vs} sits on {sorted(rnets)}; expected exactly one net")
            rnet = next(iter(rnets))
            if not model.declared(net) or not model.declared(rnet):
                iv, why = None, "UNDECLARED"
            else:
                iv = model.diff(net, rnet)
                why = None if iv is not None else "FRAME"
            out["abs" if kind == "limits" else "rec"].append({"lim": lim, "iv": iv, "why": why, "refnet": rnet})
    return out


def _headroom(items):
    """Smallest distance (V) from an interval to its abs-max limit over a list of evaluated limits; None when unbounded."""
    best = None
    for x in items:
        if x["why"]:
            continue
        lo, hi = x["iv"]
        lim = x["lim"]
        for h in ((lim["max"] - hi) if lim.get("max") is not None else None, (lo - lim["min"]) if lim.get("min") is not None else None):
            if h is not None and (best is None or h < best):
                best = h
    return None if best is None else round(best, 4)


def _verdict(res, f, fail_undeclared):
    op, fa = res["op"], res["fault"]
    role = op["role"]
    if role == "ref":
        return {"status": "REF" if op["declared"] else "UNDECLARED", "note": "reference pin" if op["declared"] else "reference net undeclared"}
    if role == "nolimit":
        return {"status": "NOLIMIT" if op["declared"] else "UNDECLARED", "note": f.get("note", "no voltage limit in the datasheet")}
    worst, details, status = None, [], "OK"
    undecl = [x for x in op["abs"] if x["why"]]
    if undecl:
        st = "FAIL" if fail_undeclared else "UNDECLARED" if undecl[0]["why"] == "UNDECLARED" else "FRAME"
        if fail_undeclared:
            st = "FAIL"
        return {"status": st, "note": f"{undecl[0]['why']}: pin net or reference net {undecl[0]['refnet']} has no range in this frame"}
    over = []
    for x in op["abs"]:
        lo, hi = x["iv"]
        lim = x["lim"]
        v = {"vs": lim["vs"], "iv": [round(lo, 4), round(hi, 4)], "min": lim.get("min"), "max": lim.get("max"),
             "page": lim.get("page"), "quote": lim.get("quote")}
        details.append(v)
        if (lim.get("max") is not None and hi > lim["max"] + EPS) or (lim.get("min") is not None and lo < lim["min"] - EPS):
            over.append(v)
    hr, fhr = _headroom(op["abs"]), _headroom(fa["abs"])
    if over:
        return {"status": "FAIL", "violated": over, "limits": details, "headroom_V": hr}
    warn = []
    for x in op["rec"]:
        if x["why"]:
            continue
        lo, hi = x["iv"]
        lim = x["lim"]
        if (lim.get("max") is not None and hi > lim["max"] + EPS) or (lim.get("min") is not None and lo < lim["min"] - EPS):
            warn.append({"vs": lim["vs"], "iv": [round(lo, 4), round(hi, 4)], "min": lim.get("min"), "max": lim.get("max"),
                         "page": lim.get("page"), "quote": lim.get("quote"), "kind": "recommended"})
    if warn:
        return {"status": "WARN", "violated": warn, "limits": details, "headroom_V": hr}
    fover = []
    for x in fa["abs"]:
        if x["why"]:
            continue
        lo, hi = x["iv"]
        lim = x["lim"]
        if (lim.get("max") is not None and hi > lim["max"] + EPS) or (lim.get("min") is not None and lo < lim["min"] - EPS):
            fover.append({"vs": lim["vs"], "iv": [round(lo, 4), round(hi, 4)], "min": lim.get("min"), "max": lim.get("max"),
                          "page": lim.get("page"), "quote": lim.get("quote"), "kind": "fault envelope"})
    if fover:
        return {"status": "WARN-FAULT", "violated": fover, "limits": details, "headroom_V": hr, "fault_headroom_V": fhr}
    return {"status": "OK", "limits": details, "headroom_V": hr, "fault_headroom_V": fhr}


# ---------------------------------------------------------------------------------------------------- datasheet check
def verify_datasheets(reg, dl_dir):
    """Every limit / rec / tolerance quote must sit on its cited page of the named PDF. Returns a list of errors."""
    errs, cache = [], {}

    def pages(fname):
        if fname not in cache:
            pdf = Path(dl_dir) / "pdf" / fname
            if not pdf.exists():
                cache[fname] = None
            else:
                out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
                cache[fname] = [normalise(p) for p in out.split("\f")]
        return cache[fname]

    def one(what, fname, page, quote):
        pg = pages(fname)
        if pg is None:
            errs.append(f"{what}: PDF {fname} not in {dl_dir}/pdf")
        elif not (1 <= page <= len(pg)):
            errs.append(f"{what}: page {page} out of range for {fname} ({len(pg)} pages)")
        elif normalise(quote) not in pg[page - 1]:
            errs.append(f"{what}: quote {quote!r} not on {fname} p.{page}")

    def numbers(what, lim):
        q = normalise(lim["quote"])
        for key in ("min", "max"):
            v = lim.get(key)
            if v in (None, 0, 0.0):
                continue
            forms = {f"{abs(v):g}", f"{abs(v)}", f"{abs(v):.1f}", f"{abs(v):.2f}"}
            if not any(f in q for f in forms):
                errs.append(f"{what}: {key} {v} does not appear in the quote {lim['quote']!r}")

    for mpn, part in reg["parts"].items():
        f0 = part["datasheet"]["file"]
        for fn, f in part["functions"].items():
            for kind in ("limits", "rec"):
                for lim in f.get(kind, []):
                    one(f"{mpn} {fn} {kind} vs {lim['vs']}", lim.get("file", f0), lim["page"], lim["quote"])
                    numbers(f"{mpn} {fn} {kind} vs {lim['vs']}", lim)
            if f.get("role") == "nolimit" or (f.get("role") == "out" and not f.get("limits")):
                one(f"{mpn} {fn} no voltage limit", f0, f["page"], f["quote"])
            for t in f.get("forbid_tie", []):
                one(f"{mpn} {fn} forbidden tie with {t['with']}", f0, t["page"], t["quote"])
    for pre, t in reg.get("resistor_tolerance", {}).items():
        if pre != "_default":
            one(f"resistor tolerance {pre}", t["file"], t["page"], t["quote"])
    for name, d in reg["nets"].items():
        for c in d.get("datasheet_cites", []):
            one(f"net {name}", c["file"], c["page"], c["quote"])
    return errs


# ------------------------------------------------------------------------------------------------------------- driver
def load_expect(path):
    if not path:
        return {}
    d = json.load(open(path))
    return {k: v for k, v in d["expected"].items()}


def run(root, registry, netlist, report=None, expect_path=None, fail_undeclared=False, fail_stale=False, fail_fault=False,
        dl=None, list_rows=False, quiet=False):
    root = Path(root)
    reg = json.load(open(registry))
    mpn_of, val = load_bom(root / "native-21/frozen/default.csv", root / "native-21/frozen/resolved-components.json")
    text = Path(netlist).read_text()
    expect = load_expect(expect_path)
    r = check(root, reg, text, mpn_of, val, expect, fail_undeclared)
    if dl:
        r["errors"] += verify_datasheets(reg, dl)
    r["registry"] = str(Path(registry))
    r["expect_fail"] = expect_path
    if fail_fault:
        r["new_failures"] += [x for x in r["warnings"] if x["status"] == "WARN-FAULT" and f"{x['part']}.{x['pin']}" not in expect]
    if fail_stale and r["stale_expected"]:
        r["errors"] += [f"STALE expect-fail entry {k}: it no longer fails (remove it)" for k in r["stale_expected"]]
    if report:
        Path(report).write_text(json.dumps({k: v for k, v in r.items()}, indent=1))
    if not quiet:
        c = r["coverage"]
        print(f"pin_absmax: {c['pins_total']} IC pins ({c['floating_or_nc']} floating/NC); "
              f"coverage {c['coverage_fraction']:.1%} of {c['denominator']} connected pins "
              f"(voltage-checked {c['checked']} = {c['checked_fraction']:.1%}, reference {c['reference_declared']}, "
              f"no voltage rating {c['nolimit_declared']}, undeclared {c['undeclared']}, no part data {c['no_part_data']})")
        for x in r["failures"]:
            tag = "EXPECTED" if f"{x['part']}.{x['pin']}" in expect else "NEW"
            for v in x["violated"]:
                what = (f"tied to {v['vs']} (forbidden)" if v.get("kind") == "forbidden tie"
                        else f"V vs {v['vs']} in {v['iv']} outside [{v['min']}, {v['max']}]")
                print(f"  FAIL[{tag}] {x['part']}.{x['pin']} {x['function']} on {x['net']}: {what} ({x['mpn']} p.{v['page']})")
        for x in r["warnings"]:
            v = x["violated"][0]
            print(f"  WARN {x['part']}.{x['pin']} {x['function']} on {x['net']}: V vs {v['vs']} in {v['iv']} "
                  f"outside [{v['min']}, {v['max']}] {v.get('kind', '')} ({x['mpn']} p.{v['page']})")
        print(f"  undeclared/frame pins: {len(r['undeclared'])}; stale expected: {r['stale_expected']}")
        for x in r["undeclared"]:
            print(f"    UNDECLARED {x['part']}.{x['pin']} {x['function']} on {x['net']}" + (f": {x['note']}" if x.get("note") else ""))
        for e in r["errors"]:
            print("  ERROR " + e)
        if list_rows:
            for x in r["rows"]:
                print("  ", x["part"], x["pin"], x.get("function"), x["net"], x["status"])
    bad = r["errors"] or r["new_failures"] or (fail_undeclared and r["undeclared"])
    return r, (1 if bad else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(UNIT))
    ap.add_argument("--registry", default=str(HERE / "pin_absmax_registry.json"))
    ap.add_argument("--netlist")
    ap.add_argument("--report")
    ap.add_argument("--expect-fail", dest="expect")
    ap.add_argument("--fail-undeclared", action="store_true")
    ap.add_argument("--fail-stale", action="store_true")
    ap.add_argument("--fail-fault", action="store_true")
    ap.add_argument("--verify-datasheets", dest="dl")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    root = Path(a.root)
    _, rc = run(root, a.registry, a.netlist or root / "native-21/frozen/default.net", a.report, a.expect,
                a.fail_undeclared, a.fail_stale, a.fail_fault, a.dl, a.list)
    sys.exit(rc)


if __name__ == "__main__":
    main()
