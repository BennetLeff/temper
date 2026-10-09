"""Logic model of the captured trip path, built from the netlist itself.

Gates come from the MPN models in verify_controller.MODELS; comparators,
supervisors, the MCU, the expander and off-board inputs are free variables.
The pass criterion is an independent specification (HEALTHY_LEVEL), never the
circuit's own internal nets, so a miswired or missing fault input fails.
"""
from __future__ import annotations

import itertools

# Each trip source and the level it drives when its quantity is HEALTHY,
# from that block's own interface document. A source that reaches PERMIT but
# is not listed here fails the check, and so does a listed one that doesn't.
HEALTHY_LEVEL = {
    "j4:bus_fault": (0, "FAULT-INTERFACE.md: J4.10 low = healthy; high, or open (10 k pull-up) = fault"),
    "thermal.hs_comp": (0, "thermal-sense INTERFACES: hot comparator output high = heatsink hot"),
    "thermal.coil_comp": (0, "thermal-sense INTERFACES: hot comparator output high = coil hot"),
    "thermal.hs_open_comp": (0, "thermal-sense INTERFACES: open comparator high = open / short to VCC"),
    "thermal.coil_open_comp": (0, "thermal-sense INTERFACES: open comparator high = open / short to VCC"),
    "rtd_pan.low_window": (1, "RTD unit: window outputs both high only inside the RTD window"),
    "rtd_pan.high_window": (1, "RTD unit: window outputs both high only inside the RTD window"),
    "rtd_pan.rail_monitor": (1, "RTD unit: TPS389001 RESET high = RTD_AVDD above threshold"),
    "u_runaway": (0, "controller: runaway comparator high = pan over threshold, BIAS off or RTD open"),
    "u_rail": (1, "controller: TPS3703 RESET high = v3v3 in window and 10 ms delay elapsed"),
    "interlock.watchdog": (1, "interlock INTERFACES: TPS3823 RESET_N high = VDD ok and WDI serviced"),
}

GATE_EVAL = {
    "inv": lambda x: 1 - x[0],
    "buf": lambda x: x[0],
    "and": lambda x: int(all(x)),
    "or": lambda x: int(any(x)),
    "nand": lambda x: 1 - int(all(x)),
}


def build_logic(nl, merged, models, firmware_mpns, offboard):
    """Return (gates, free). gates: (kind, inputs, output(s), ref)."""
    find = merged.find
    gates, free = [], {}
    for ref, mpn in nl.mpn.items():
        model = models.get(mpn)
        if model is None:
            continue

        def net(p, ref=ref):
            return find(nl.net_of(ref, str(p)))
        path = nl.refs[ref]
        logic = model.logic
        if logic and logic.startswith("free:"):
            for p, role in model.pins.items():
                if role in ("out", "od"):
                    free[net(p)] = path
        elif logic == "dff":
            gates.append(("dff", [net(1), net(2), net(6), net(7)], (net(5), net(3)), ref))
        elif logic == "buf244":
            for a, y in [(2, 18), (4, 16), (6, 14), (8, 12), (11, 9), (13, 7), (15, 5), (17, 3)]:
                gates.append(("buf", [net(a)], net(y), ref))
        elif logic:
            for spec in logic.split(";"):
                kind, rest = spec.split(":")
                ins, out = rest.split(">")
                gates.append((kind, [net(int(i)) for i in ins.split(",")], net(int(out)), ref))
        elif mpn in firmware_mpns:
            for p, role in model.pins.items():
                if role in ("out", "od") and nl.net_of(ref, p):
                    free[net(p)] = f"firmware:{path}.{p}"
    outs = {g[2] for g in gates if g[0] != "dff"}
    for ref, pin, name in offboard:
        n = find(nl.net_of(ref, pin))
        if n not in outs and n not in free:
            free[n] = name
    return gates, free


class Sim:
    def __init__(self, gates, free, pull, gnd, vcc):
        self.gates, self.free, self.pull = gates, free, pull
        self.gnd, self.vcc = gnd, vcc
        self.dff = [g for g in gates if g[0] == "dff"]
        self.comb_outs = {g[2] for g in gates if g[0] != "dff"}

    def comb(self, assign):
        val = dict(assign)
        val[self.gnd], val[self.vcc] = 0, 1
        for n, lvl in self.pull.items():
            if n not in val and n not in self.comb_outs:
                val[n] = lvl
        for _ in range(64):
            changed = False
            for kind, ins, out, _ref in self.gates:
                if kind == "dff" or not all(i in val for i in ins):
                    continue
                x = [val[i] for i in ins]
                y = (0 if all(x) else self.pull.get(out)) if kind == "nand_od" else GATE_EVAL[kind](x)
                if y is not None and val.get(out) != y:
                    val[out] = y
                    changed = True
            if not changed:
                return val
        raise RuntimeError("combinational logic did not settle")

    def step(self, assign, reset_net, r_prev, r_now, q_prev):
        """Firmware moves RESET_N r_prev -> r_now with all sources held."""
        (_, ins, outs, _ref), = self.dff
        before = self.comb({**assign, reset_net: r_prev})
        after = self.comb({**assign, reset_net: r_now})
        clk0, clk1 = before.get(ins[0]), after.get(ins[0])
        d, clr, pre = after.get(ins[1]), after.get(ins[2]), after.get(ins[3])
        q = q_prev
        if clr == 0:
            q = 0
        elif pre == 0:
            q = 1
        elif clk0 == 0 and clk1 == 1:
            q = d
        after[outs[0]], after[outs[1]] = q, 1 - q
        return after, q


def fan_in_cone(gates, start):
    by_out = {}
    for g in gates:
        for o in (g[2] if g[0] == "dff" else (g[2],)):
            by_out.setdefault(o, []).append(g)
    cone, stack = set(), [start]
    while stack:
        n = stack.pop()
        if n in cone:
            continue
        cone.add(n)
        for g in by_out.get(n, []):
            stack.extend(g[1])
    return cone, by_out


def exhaustive(sim, sources, reset, healthy):
    violations, missed, unheld = [], [], 0
    for bits in itertools.product((0, 1), repeat=len(sources)):
        assign = dict(zip(sources, bits))
        trip = any(assign[n] != healthy[n] for n in sources)
        for q_prev, r_prev, r_now in itertools.product((0, 1), repeat=3):
            _, q = sim.step(assign, reset, r_prev, r_now, q_prev)
            if trip and q:
                violations.append({sim.free[n]: v for n, v in assign.items()}
                                  | {"q_prev": q_prev, "reset": (r_prev, r_now)})
            edge = r_prev == 1 and r_now == 0
            if not trip and edge and not q:
                missed.append(q_prev)
            if not trip and not edge and q != q_prev:
                unheld += 1
    return violations, missed, unheld
