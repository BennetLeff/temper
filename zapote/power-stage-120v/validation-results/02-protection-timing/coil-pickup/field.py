"""Radial profiles of the native-21 stray field (axisymmetric model) and signed reconstruction.

The map stores rms magnitudes |Bz|, |Br| on a board grid. The source model is axisymmetric about
board (141, -25), so each column is a function of r only. Signs: Bz flips at its radial null
(minimum of |Bz|); Br's sign relative to Bz is fixed by div B = 0 using the two z planes.
"""
import csv, numpy as np
MAP = '/Users/bennet/Desktop/temper/output/temper-r32-studies/06-emi-strayfield/native21_field_map.csv'
AX = np.array([141.0, -25.0])
CASES = ['pan_bars_31kHz_45Apk', 'nopan_envelope_bars_31kHz_45Apk']

def load():
    rows = list(csv.DictReader(open(MAP)))
    out = {}
    for c in CASES:
        for z in ('26.8', '28.4'):
            pts = [(float(r['x_k_mm']), float(r['y_k_mm']), float(r['Br_rms_uT']), float(r['Bz_rms_uT']))
                   for r in rows if r['case'] == c and r['z_w_mm'] == z]
            a = np.array(pts)
            rr = np.hypot(a[:, 0] - AX[0], a[:, 1] - AX[1])
            out[(c, float(z))] = (rr, a[:, 2], a[:, 3])
    return out

class Profile:
    """Signed Br(r), Bz(r) in uT rms at 45 A pk, on a fine radial grid, z = z0."""
    def __init__(self, data, case, z0=26.8, dr=0.25):
        rr, br, bz = data[(case, z0)]
        self.rg = np.arange(np.floor(rr.min()), np.ceil(rr.max()) + dr, dr)
        # axisymmetry: bin and take the median, report the scatter
        idx = np.digitize(rr, self.rg)
        self.scatter = []
        def prof(v):
            o = np.interp(self.rg, *zip(*sorted(zip(rr, v))))
            return o
        order = np.argsort(rr)
        self.Br_abs = np.interp(self.rg, rr[order], br[order])
        self.Bz_abs = np.interp(self.rg, rr[order], bz[order])
        # axisymmetry residual: compare each sample with the profile
        self.axisym_resid = float(np.max(np.abs(np.interp(rr, self.rg, self.Bz_abs) - bz)))
        # Bz sign flips at the interior minimum of |Bz|
        m = (self.rg > 60) & (self.rg < 200)
        self.r0 = float(self.rg[m][np.argmin(self.Bz_abs[m])])
        self.Bz = np.where(self.rg < self.r0, 1.0, -1.0) * self.Bz_abs
        self.Br = self.Br_abs.copy()  # sign fixed by fix_br_sign
        self.z0 = z0

    def fix_br_sign(self, other):
        """div B = 0: (1/r) d(r Br)/dr = -dBz/dz.  other = Profile at z0 + dz (same case)."""
        dz = other.z0 - self.z0
        bz2 = np.where(self.rg < other.r0, 1.0, -1.0) * np.interp(self.rg, other.rg, other.Bz_abs)
        dbzdz = (bz2 - self.Bz) / dz
        # integrate r*Br = -int r dBz/dz dr + const; test both Br signs at mid radii
        lhs = np.gradient(self.rg * self.Br_abs, self.rg) / self.rg
        m = (self.rg > 40) & (self.rg < 220)
        cp = np.corrcoef(lhs[m], -dbzdz[m])[0, 1]
        cm = np.corrcoef(-lhs[m], -dbzdz[m])[0, 1]
        self.br_sign = 1.0 if cp > cm else -1.0
        self.br_sign_corr = (cp, cm)
        self.Br = self.br_sign * self.Br_abs

    def A(self, r):
        """A_phi(r) [uT*mm] with Bz = (1/r) d(r A)/dr; additive C/r gauge is curl-free off-axis."""
        if not hasattr(self, '_rA'):
            f = self.Bz * self.rg
            self._rA = np.concatenate([[0], np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(self.rg))])
        return np.interp(r, self.rg, self._rA) / r

    def at(self, x, y):
        r = np.hypot(x - AX[0], y - AX[1])
        return np.interp(r, self.rg, self.Bz), np.interp(r, self.rg, self.Br), r

def profiles():
    d = load()
    P = {}
    for c in CASES:
        p = Profile(d, c, 26.8); q = Profile(d, c, 28.4)
        p.fix_br_sign(q)
        P[c] = p
    return P

if __name__ == '__main__':
    P = profiles()
    for c, p in P.items():
        print(c, 'r range %.0f-%.0f' % (p.rg[0], p.rg[-1]), 'Bz null r0 = %.1f' % p.r0,
              'axisym resid %.2f uT' % p.axisym_resid, 'Br sign %+d corr' % p.br_sign, p.br_sign_corr)
        for r in (30, 50, 70, 90, 110, 124, 140, 160, 190, 220):
            i = np.searchsorted(p.rg, r)
            print('   r %3d  Bz %+7.1f  Br %+7.1f' % (r, p.Bz[i], p.Br[i]))

class ComplexProfile:
    """Phasor field from the FEM re-solve (field_phase.py): Bz, Br complex, uT rms at 45 A pk,
    phase referenced to the tank current (real). Same interface as Profile; A is complex."""
    def __init__(self, case, path=None):
        import json, os
        path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'field_phase.json')
        d = json.load(open(path))[case]
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
