"""Re-solve study 06's field-map cases (same geometry as followup_r32.py, imported read-only)
to get the PHASE of Br, Bz at the board relative to the tank current, and the signed values.
Writes field_phase.json here only."""
import sys, math, json, numpy as np
sys.path.insert(0, '/Users/bennet/Desktop/temper/output/temper-r32-studies/06-emi-strayfield')
sys.dont_write_bytecode = True
from fem_axi import Model, make_grid, MU0
import study
from study import SIG, MU_FERRITE
I = 45.0
R_OUT = math.sqrt(370 * 362.5 / math.pi) * 1e-3
GEOM = dict(seat=(0.158, R_OUT, 0.101825, 0.105), fence=(0.171, R_OUT, 0.105, 0.109064),
            base=(0.0, 0.221, 0.00897, 0.011))
rr = [(0.0, 0.025, 0.5e-3), (0.022, 0.125, 1e-3), (0.155, 0.21, 0.5e-3), (0.1835, 0.1852, 0.1e-3)]
zz = [(0.0088, 0.0112, 0.08e-3), (0.088, 0.1015, 0.5e-3), (0.1016, 0.1092, 0.12e-3),
      (0.1098, 0.1106, 0.035e-3), (0.1106, 0.1122, 0.15e-3), (0.011, 0.105, 4e-3)]
rr += [(v, v, 0.5e-3) for v in (0.022, 0.025, 0.116, 0.118, 0.110, 0.158, 0.171, R_OUT, 0.221, 0.18373, 0.185)]
zz += [(v, v, 0.1e-3) for v in (0.0935, 0.0975, 0.0985, 0.1025, 0.110, 0.112, 0.00897, 0.011, 0.101825, 0.105, 0.109064)]
R = make_grid(0, 4.0, rr, 0.08, 1.12); Z = make_grid(-4.0, 4.0, zz, 0.08, 1.12)
def build(pan, parts, N):
    m = Model(R, Z)
    fm = m.box(0.025, 0.118, 0.0935, 0.0975)
    p = np.minimum(1.0, 8 * 0.020 / (2 * np.pi * m.RC)); m.mur[fm] = (1 + p * (MU_FERRITE - 1))[fm]
    for name in parts:
        r0, r1, z0, z1 = GEOM[name]; m.add_conductor(name, r0, r1, z0, z1, SIG["Al5052"])
    if pan: m.add_conductor("pan", 0, 0.110, 0.110, 0.112, SIG["steel_pan"], study.MU_PAN)
    m.set_coil(0.022, 0.116, 0.0985, 0.1025, N, I)
    return m
N = math.sqrt(70e-6 / build(False, (), 1.0).solve(31e3)["L"])
out = {}
rq = np.arange(20, 266, 1.0) * 1e-3
for case, pan in (("pan_bars_31kHz_45Apk", True), ("nopan_envelope_bars_31kHz_45Apk", False)):
    m = build(pan, ("base", "seat", "fence"), N); m.solve(31e3)
    Br, Bz = m.B_at(rq, np.full_like(rq, 26.8e-3))
    out[case] = dict(r_mm=(rq * 1e3).tolist(),
                     Bz_re_uTrms=(Bz.real / math.sqrt(2) * 1e6).tolist(), Bz_im_uTrms=(Bz.imag / math.sqrt(2) * 1e6).tolist(),
                     Br_re_uTrms=(Br.real / math.sqrt(2) * 1e6).tolist(), Br_im_uTrms=(Br.imag / math.sqrt(2) * 1e6).tolist())
    print(case)
    for i in range(5, len(rq), 15):
        print('  r %5.0f  Bz %+7.1f %+6.1fj (%6.1f deg)  Br %+7.1f %+6.1fj (%6.1f deg)' % (
            rq[i] * 1e3, out[case]['Bz_re_uTrms'][i], out[case]['Bz_im_uTrms'][i], np.degrees(np.angle(Bz[i])),
            out[case]['Br_re_uTrms'][i], out[case]['Br_im_uTrms'][i], np.degrees(np.angle(Br[i]))))
json.dump(out, open('field_phase.json', 'w'), indent=1)
