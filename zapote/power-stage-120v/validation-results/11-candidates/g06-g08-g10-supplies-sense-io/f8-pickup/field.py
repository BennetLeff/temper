"""Phasor stray field of the coil at the board plane (F.Cu, z = 26.8 mm), from field_phase_<kHz>.json
(field_phase.py, study 06's axisymmetric FEM, 45 A peak coil current, uT rms). Same interface as the
02-protection-timing/coil-pickup/field.py ComplexProfile; the CSV-map real profiles are dropped (31 kHz only)."""
import json, os
import numpy as np
AX = np.array([141.0, -25.0])
CASES = ['pan_bars_31kHz_45Apk', 'nopan_envelope_bars_31kHz_45Apk']
HERE = os.path.dirname(os.path.abspath(__file__))

class ComplexProfile:
    def __init__(self, case, khz):
        d = json.load(open(os.path.join(HERE, 'field_phase_%dkHz.json' % khz)))[case]
        self.rg = np.array(d['r_mm'])
        self.Bz = np.array(d['Bz_re_uTrms']) + 1j * np.array(d['Bz_im_uTrms'])
        self.Br = np.array(d['Br_re_uTrms']) + 1j * np.array(d['Br_im_uTrms'])
        self.z0 = 26.8
        f = self.Bz * self.rg
        self._rA = np.concatenate([[0], np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(self.rg))])
    def A(self, r):
        return (np.interp(r, self.rg, self._rA.real) + 1j * np.interp(r, self.rg, self._rA.imag)) / r
    def at(self, x, y):
        r = np.hypot(x - AX[0], y - AX[1])
        c = lambda v: np.interp(r, self.rg, v.real) + 1j * np.interp(r, self.rg, v.imag)
        return c(self.Bz), c(self.Br), r
