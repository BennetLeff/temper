"""R2-01 cross-check (lead, 2026-10-13): can the stage-14 bus alone meet DC-LINK-CLAMP.md's requested 2 J minimum
inside the 520 V screen?  V_peak = sqrt(V0^2 + 2 E / C), lossless, all energy into the bus capacitance.
Inputs: C5/C6 2 x 9 uF + 4 x 100 nF leg caps = 18.4 uF (ALT-D3 s3.1), tolerance corners as bus_peak_no_clamp.py;
V0 198 V (127 V +10 % crest) and 286 V (static OVP corner, DC-LINK-CLAMP.md); E = 2 J (requested) and 0.46 J (ALT-D3 s1.1
worst modelled return)."""
import math
SCREEN = 520.0
print(f"{'C':>22} {'V0':>5} {'E (J)':>6} {'V_peak':>8}  vs {SCREEN:.0f} V")
worst = {}
for label, c in (("18.4 uF nominal", 18.4e-6), ("-10 % (K tol.)", 18.4e-6 * 0.9), ("-19 % (tol.+ageing)", 18.4e-6 * 0.81)):
    for v0 in (198.0, 286.0):
        for e in (2.0, 0.46):
            v = math.sqrt(v0 ** 2 + 2 * e / c)
            worst[e] = max(worst.get(e, 0), v)
            print(f"{label:>22} {v0:5.0f} {e:6.2f} {v:8.1f}  {'FAIL' if v > SCREEN else 'ok'}")
for e, v in sorted(worst.items()):
    print(f"worst for {e} J: {v:.1f} V ({'over' if v > SCREEN else 'under'} the {SCREEN:.0f} V screen)")
# energy the bus alone can take from the static OVP corner before the screen, nominal C
for label, c in (("nominal", 18.4e-6), ("-19 %", 18.4e-6 * 0.81)):
    print(f"bus-only absorption 286 V -> 520 V, {label}: {0.5 * c * (SCREEN ** 2 - 286.0 ** 2):.2f} J")
