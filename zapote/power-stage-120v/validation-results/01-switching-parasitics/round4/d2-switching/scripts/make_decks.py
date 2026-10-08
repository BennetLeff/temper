from pathlib import Path

OUT = Path(__file__).resolve().parent
UNIT = OUT.parents[4]
SOURCE = UNIT / "validation-results/01-switching-parasitics/round3/b1-board-grid/complementary_leg.cir"
base = SOURCE.read_text()
assert ".tran {TRMAX} {T1+DT+0.8u} 0 {TRMAX}" in base
assert "Ldhs bus d_hs {LD_HS}\nXQH d_hs g_hs s_hs" in base
assert "Lcap bus capn {LCAP}" in base

(OUT / "legacy_control.cir").write_text(base)

extended = base.replace("Ldhs bus d_hs {LD_HS}\nXQH d_hs g_hs s_hs",
                        "Ldhs bus d_hs {LD_HS}\nVidh d_hs d_hs_pin 0\nXQH d_hs_pin g_hs s_hs")
extended = extended.replace(".tran {TRMAX} {T1+DT+0.8u} 0 {TRMAX}",
                            ".tran {TRMAX} {T1+DT+1.02u} 0 {TRMAX}")
old_save = next(line for line in extended.splitlines() if line.startswith(".save "))
new_save = (old_save + " v(bus) v(capn) v(capm) v(gdl) v(gdh) v(g_ls) v(g_hs) "
            "i(vidh) i(ldhs) i(v.xql.x1.v_ichannel) i(v.xqh.x1.v_ichannel) "
            "i(v.xql.x1.v_iepi) i(v.xqh.x1.v_iepi) "
            "i(v.xql.x1.v_sense2) i(v.xqh.x1.v_sense2)")
extended = extended.replace(old_save, new_save)
(OUT / "extended_instrumented.cir").write_text(extended)

# NGspice exposes the flattened model nodes xql.g/xql.s. Clamp the die gate
# only after the original turn-off trajectory has crossed 3 V; the clamp
# switch's current is an imposed counterfactual current, never a fault current.
clamp = extended.replace(
    ".tran {TRMAX} {T1+DT+1.02u} 0 {TRMAX}",
    "Boff xql.g xql.s I={v(xql.g,xql.s)*(1e-12+100*(1+tanh((time-(T1+345n))/1n))/2)}\n"
    ".tran {TRMAX} {T1+DT+1.02u} 0 {TRMAX}")
(OUT / "heuristic_ideal_offgate.cir").write_text(clamp)
