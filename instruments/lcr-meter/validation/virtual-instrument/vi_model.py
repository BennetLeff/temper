"""Virtual-instrument core: transfer model, DUT library, noise model, record synthesis and a
host-equivalent analysis pipeline for the Temper LCR Rev C (C-local100p).

Everything that depends on the analog chain comes from data/transfer_<config>.npz, extracted from
the full-chain SPICE deck by chain_spice.py.  Everything that depends on digital behaviour
reproduces host/src/lib.rs at commit recorded in data/host-commit.txt (frequency_word,
divider_for, decode_word, crc32, fit, calibration_coefficients, correct).

Noise-model inputs are datasheet values (sources/ti/*.txt, sources/new/AD9833.txt) unless a
comment says ESTIMATE.  Units: volts, amps, ohms, hertz, seconds.
"""
from __future__ import annotations

import json
import math
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# ---------------------------------------------------------------- host constants (lib.rs)
DDS_CLOCK_HZ = 24_000_000.0
SAMPLE_BASE_HZ = 1_000_000.0
DEFAULT_COUNT = 16_384
HARDWARE_REVISION = "C-local100p"
LSB_V = 8.192 / 65536.0          # ADS9224R +/-4.096 V differential full scale, 16 bit
CLIP_CODE = 32700                 # host clipping threshold

K_B = 1.380649e-23
T_K = 300.15                      # 27 C, the vendor-model temperature
FMAX = 200e6                      # top of the SPICE AC grid; integration limit


def frequency_word(hz: float) -> int:
    if not (100.0 <= hz <= 100_000.0):
        raise ValueError("frequency must be 100..100000 Hz")
    return int(math.floor(hz * 268_435_456.0 / DDS_CLOCK_HZ + 0.5))


def frequency_hz(word: int) -> float:
    return word * DDS_CLOCK_HZ / 268_435_456.0


def divider_for(hz: float) -> int:
    return int(min(20.0, max(1.0, math.floor(SAMPLE_BASE_HZ / max(hz * 10.0, 50_000.0)))))


def feedback(range_ohm: float, hz: float, cap_pf: float = 100.0) -> complex:
    return 1.0 / complex(1.0 / range_ohm, 2 * math.pi * hz * cap_pf * 1e-12)


# ---------------------------------------------------------------- transfer model
class Transfer:
    """Bilinear-in-Z transfers H(Z) = (p + q Z)/(1 + s Z) from every injection source to the
    differential ADC inputs of channel A and B, interpolated in log-frequency."""

    ADC_BW_HZ = 52e6  # ADS9224R analog input bandwidth (-3 dB), applied as one pole

    def __init__(self, tag: str):
        z = np.load(DATA / f"transfer_{tag}.npz")
        self.tag = tag
        self.freq = z["freq"]
        self.s = z["s"]
        self.names = [str(n) for n in z["names"]]
        self.coef = z["coef"]  # (J, 4, F): pA qA pB qB
        self.meta = json.loads(str(z["meta"]))
        self.lf = np.log10(self.freq)

    def _interp(self, y, f):
        lf = np.log10(np.clip(f, self.freq[0], self.freq[-1]))
        return np.interp(lf, self.lf, y.real) + 1j * np.interp(lf, self.lf, y.imag)

    def H(self, f, Z, names=None):
        """Return HA, HB with shape (J, len(f)) for the requested sources."""
        f = np.atleast_1d(np.asarray(f, float))
        Z = np.broadcast_to(np.asarray(Z, complex), f.shape)
        idx = [self.names.index(n) for n in (names or self.names)]
        s = self._interp(self.s, f)
        den = 1.0 + s * Z
        adc = 1.0 / (1.0 + 1j * f / self.ADC_BW_HZ)
        HA = np.empty((len(idx), f.size), complex)
        HB = np.empty_like(HA)
        for r, j in enumerate(idx):
            pa, qa, pb, qb = (self._interp(self.coef[j, k], f) for k in range(4))
            HA[r] = (pa + qa * Z) / den * adc
            HB[r] = (pb + qb * Z) / den * adc
        HA[:, f > self.freq[-1]] = 0.0
        HB[:, f > self.freq[-1]] = 0.0
        return HA, HB


_TRANSFER_CACHE: dict[str, Transfer] = {}


def transfer(tag: str) -> Transfer:
    if tag not in _TRANSFER_CACHE:
        _TRANSFER_CACHE[tag] = Transfer(tag)
    return _TRANSFER_CACHE[tag]


# ---------------------------------------------------------------- DUT library
@dataclass(frozen=True)
class Dut:
    """Two-terminal DUT.  kind: 'R' (series R+L, parallel C), 'coil', 'cap', 'tank'."""
    name: str
    kind: str
    r: float = 0.0          # series resistance at f_ref (ohm)
    l: float = 0.0          # series inductance (H)
    c: float = 0.0          # capacitance (F) for 'cap'/'tank'; parallel C for 'coil'/'R'
    tan_d: float = 0.0      # capacitor dissipation factor (cap, tank capacitor)
    esl: float = 0.0        # capacitor series inductance
    r_exp: float = 0.0      # coil copper R ~ f^r_exp (referenced to f_ref)
    r_pan: float = 0.0      # pan reflected R at f_ref (~ f^0.5)
    f_ref: float = 40e3
    nominal: float = 0.0    # value the user enters for a standard (ohm)

    def z(self, f):
        f = np.asarray(f, float)
        w = 2 * np.pi * np.maximum(f, 1e-3)
        if self.kind == "R":
            zs = self.r + 1j * w * self.l
            return zs if self.c == 0 else zs / (1 + 1j * w * self.c * zs)
        if self.kind == "coil":
            r = self.r * (np.maximum(f, 1.0) / self.f_ref) ** self.r_exp
            r = r + self.r_pan * (np.maximum(f, 1.0) / self.f_ref) ** 0.5
            zs = r + 1j * w * self.l
            return zs if self.c == 0 else zs / (1 + 1j * w * self.c * zs)
        if self.kind == "cap":
            return self.tan_d / (w * self.c) + 1j * w * self.esl + 1 / (1j * w * self.c)
        raise ValueError(self.kind)


@dataclass(frozen=True)
class Series:
    name: str
    parts: tuple

    def z(self, f):
        return sum(p.z(f) for p in self.parts)


# Coil: TANK_COIL_SPECIFICATION.md rows 1/3/5; pan reflection from coil_mc.rs pan classes.
L_INSTALLED = 66.3e-6          # 70 uH design, 0.95x installed (spec row 1)
R_AC_40K = 0.193               # 25 C acceptance limit at 40 kHz, f^0.55 shape (row 5)
C_WINDING = 50e-12             # ESTIMATE: two-section pancake self-capacitance (SRF ~2.7 MHz)
KL_REF = 0.633                 # 41.95 uH / 66.3 uH: spec's nominal coil on the reference pan
R40_NOM = 0.0334               # ohm per uH of L_no_pan at 40 kHz (Infineon kit chart anchor)
R40_LOW = 0.012                # lowest pan class bound (offset/small pan), coil_mc.rs
KL_LOW = 0.85

DUTS = {
    "short": Dut("short", "R", r=0.3e-3, l=2e-9, nominal=0.0),
    "std20": Dut("std20", "R", r=20.0, l=1.5e-9, c=0.2e-12, nominal=20.0),
    "std100": Dut("std100", "R", r=100.0, l=1.5e-9, c=0.2e-12, nominal=100.0),
    "chk47": Dut("chk47", "R", r=47.0, l=1.5e-9, c=0.2e-12, nominal=47.0),
    "coil_nopan": Dut("coil_nopan", "coil", r=R_AC_40K, l=L_INSTALLED, c=C_WINDING, r_exp=0.55),
    "coil_pan": Dut("coil_pan", "coil", r=R_AC_40K, l=L_INSTALLED * KL_REF, c=C_WINDING, r_exp=0.55,
                    r_pan=R40_NOM * L_INSTALLED * 1e6),
    "coil_pan_lowR": Dut("coil_pan_lowR", "coil", r=R_AC_40K, l=L_INSTALLED * KL_LOW, c=C_WINDING,
                         r_exp=0.55, r_pan=R40_LOW * L_INSTALLED * 1e6),
    # TDK B32654A1104K000 polypropylene: tan d ESTIMATE 2e-4; ESL ESTIMATE 10 nH (leads)
    "cap100n": Dut("cap100n", "cap", c=100e-9, tan_d=2e-4, esl=10e-9),
    # five in parallel plus ESTIMATE 15 nH of bank wiring
    "bank500n": Dut("bank500n", "cap", c=500e-9, tan_d=2e-4, esl=15e-9),
    # 9 uF bus film capacitor at 1 kHz; tan d / ESL ESTIMATES
    "bus9u": Dut("bus9u", "cap", c=9e-6, tan_d=2e-4, esl=20e-9),
}
DUTS["tank_nopan"] = Series("tank_nopan", (DUTS["coil_nopan"], DUTS["bank500n"]))
DUTS["tank_pan"] = Series("tank_pan", (DUTS["coil_pan"], DUTS["bank500n"]))


def tank_f0(name):
    """Frequency where Im Z = 0 for a tank DUT (bisection on the true model)."""
    d = DUTS[name]
    lo, hi = 10e3, 80e3
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if np.imag(d.z(mid)) < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------- noise model
@dataclass(frozen=True)
class NoiseOpts:
    dds_amp_v: float = 0.3          # AD9833 VOUT ~0.6 Vpp (0.038..0.65 V levels), validated decks
    dds_snr_db: float = 60.0        # AD9833 SNR typ 60 dB (min 55 dB), 0..MCLK/2
    dds_band_hz: float = 12e6       # DDS quantization noise band ~ MCLK/2
    opa_en: float = 6.0e-9          # OPA2810 flatband (500 kHz) en
    opa810_en: float = 6.3e-9       # OPA810 flatband en
    opa_fc: float = 1500.0          # 1/f corner: OPA810 spec 1.5 kHz; OPA2810 ESTIMATE same die
    opa_in: float = 5e-15           # OPA2810/OPA810 current noise at 10 kHz
    fda_en: float = 3.3e-9          # THS4551 differential input en, 1/f < 150 Hz
    fda_fc: float = 150.0
    fda_in: float = 0.5e-12         # THS4551 input current noise, 1/f < 10 kHz
    fda_in_fc: float = 1e4
    opa_scale: float = 1.0          # multiplies every amplifier noise density (corner studies)
    adc_lsb_rms: float = 0.4        # ADS9224R transition noise 0.4 LSB typ, per conversion
    ref_common_ppm: float = 5.0     # ESTIMATE: shared reference gain noise per conversion
    ref_indep_ppm: float = 2.0      # ESTIMATE: per-channel REFP buffer gain noise
    clock_jitter_s: float = 50e-12  # ESTIMATE: RP2040 PLL CONVST jitter (common to A and B)
    aperture_jitter_s: float = 2e-12  # ADS9224R aperture jitter, per channel
    enable: tuple = ()               # if non-empty, only these noise sources (budget studies)
    src_scale: float = 1.0           # excitation-chain gain multiplier (what-if b2): scales DDS and
                                     # OPA810-stage noise with the signal


def densities(tr: Transfer, f, zdut, o: NoiseOpts):
    """One-sided PSD (V^2/Hz or A^2/Hz) of every injection source, shape (J, F)."""
    f = np.asarray(f, float)
    ff = np.maximum(f, 1e-3)
    S = np.zeros((len(tr.names), f.size))
    kt4 = 4 * K_B * T_K
    res = {"R30": 330.0, "R31": 330.0, "R32": 100e3, "R33": 5e3, "R34": 1e3}
    p = tr.meta["params"]
    res.update(RG=p["rg"], RF=p["rf"], Risolo=p.get("riso", 0.0) or 1.0)
    for ch, rin in (("a", p["rin_a"]), ("b", p["rin_b"])):
        res.update({f"R{ch}i1": rin, f"R{ch}i2": rin, f"R{ch}f1": p["rfb"], f"R{ch}f2": p["rfb"],
                    f"R{ch}int1": 22.0, f"R{ch}int2": 22.0, f"R{ch}iso1": 4.32, f"R{ch}iso2": 4.32})
    dds_rms = o.dds_amp_v / math.sqrt(2) * 10 ** (-o.dds_snr_db / 20)
    for j, n in enumerate(tr.names):
        if o.enable and n not in o.enable:
            continue
        if n == "dds":
            S[j] = np.where(f < o.dds_band_hz, dds_rms ** 2 / o.dds_band_hz, 0.0)
        elif n == "en_x5":
            S[j] = (o.opa_scale * o.opa810_en) ** 2 * (1 + o.opa_fc / ff)
        elif n.startswith("en_x"):
            if n in ("en_xa", "en_xb"):
                S[j] = (o.opa_scale * o.fda_en) ** 2 * (1 + o.fda_fc / ff)
            else:
                S[j] = (o.opa_scale * o.opa_en) ** 2 * (1 + o.opa_fc / ff)
        elif n == "in_x7a_m":
            S[j] = (o.opa_scale * o.opa_in) ** 2
        elif n.startswith("in_x"):
            S[j] = (o.opa_scale * o.fda_in) ** 2 * (1 + o.fda_in_fc / ff)
        elif n == "dut":
            zd = np.asarray(zdut, complex)
            safe = np.where(np.abs(zd) > 0, zd, 1.0)
            S[j] = np.where(np.abs(zd) > 0, kt4 * np.maximum(np.real(1.0 / safe), 0.0), 0.0)
        elif n.startswith("nr_"):
            S[j] = kt4 / res[n[3:]]
        else:
            raise KeyError(n)
        if n in SOURCE_CHAIN:
            S[j] *= o.src_scale ** 2
    return S


SOURCE_CHAIN = ("dds", "en_x5", "nr_R30", "nr_R31", "nr_R32", "nr_R33", "nr_R34")


def folded_csd(tr, dut, fs, nu, o: NoiseOpts, split_hz=2e6):
    """Folded one-sided cross-spectral matrix of the analog noise at the ADC (V^2/Hz).

    Aliases below m_max*fs are summed exactly (direct m*fs+nu and mirrored m*fs-nu, the latter
    conjugated); above that the alias comb is replaced by its integral (2/fs) * int S h h^H df,
    which is independent of nu.  Returns CAA, CBB (real) and CAB = E[A B*] (complex)."""
    nu = np.asarray(nu, float)
    m_max = max(1, int(math.ceil(split_hz / fs)))
    m_dir = np.arange(0, m_max)
    m_mir = np.arange(1, m_max + 1)
    f_dir = (m_dir[None, :] * fs + nu[:, None]).ravel()
    f_mir = (m_mir[None, :] * fs - nu[:, None]).ravel()
    out = []
    for fv, mirror in ((f_dir, False), (f_mir, True)):
        fv = np.maximum(fv, 0.05)
        HA, HB = tr.H(fv, dut.z(fv))
        S = densities(tr, fv, dut.z(fv), o)
        caa = (S * np.abs(HA) ** 2).sum(0)
        cbb = (S * np.abs(HB) ** 2).sum(0)
        cab = (S * HA * np.conj(HB)).sum(0)
        if mirror:
            cab = np.conj(cab)
        out.append((caa.reshape(nu.size, -1).sum(1), cbb.reshape(nu.size, -1).sum(1),
                    cab.reshape(nu.size, -1).sum(1)))
    caa = out[0][0] + out[1][0]
    cbb = out[0][1] + out[1][1]
    cab = out[0][2] + out[1][2]
    # far band
    f0 = m_max * fs
    if f0 < FMAX:
        fg = np.concatenate([[f0], tr.freq[(tr.freq > f0) & (tr.freq < FMAX)], [FMAX]])
        HA, HB = tr.H(fg, dut.z(fg))
        S = densities(tr, fg, dut.z(fg), o)
        ia = np.trapezoid((S * np.abs(HA) ** 2).sum(0), fg)
        ib = np.trapezoid((S * np.abs(HB) ** 2).sum(0), fg)
        iab = np.trapezoid((S * np.real(HA * np.conj(HB))).sum(0), fg)
        caa = caa + 2 / fs * ia
        cbb = cbb + 2 / fs * ib
        cab = cab + 2 / fs * iab
    return caa, cbb, cab


def per_sample_noise(tr, dut, o: NoiseOpts, by_source=False):
    """Analog noise per conversion (all bandwidth folds): sigma_A, sigma_B, rho (V)."""
    fg = np.concatenate([np.geomspace(0.1, 1.0, 20)[:-1], tr.freq])
    HA, HB = tr.H(fg, dut.z(fg))
    S = densities(tr, fg, dut.z(fg), o)
    va = np.trapezoid(S * np.abs(HA) ** 2, fg, axis=1)
    vb = np.trapezoid(S * np.abs(HB) ** 2, fg, axis=1)
    cab = np.trapezoid(S * np.real(HA * np.conj(HB)), fg, axis=1)
    if by_source:
        return dict(zip(tr.names, zip(va, vb, cab)))
    return math.sqrt(va.sum()), math.sqrt(vb.sum()), cab.sum() / math.sqrt(va.sum() * vb.sum())


# ---------------------------------------------------------------- board instance (digital side)
@dataclass(frozen=True)
class Instance:
    """Per-board draws that are not in the SPICE netlist."""
    transfer_tag: str = "base"     # signal transfer (instance SPICE draw, e.g. base_inst3)
    noise_tag: str = "base"        # noise transfers (nominal)
    aperture_mismatch_s: float = 0.0   # ADS9224R tA mismatch, typ 40 ps
    gain_a: float = 0.0                # ADC cumulative gain error, typ +/-0.01 %FSR
    gain_b: float = 0.0
    offset_a_lsb: float = 0.0          # typ +/-1 LSB
    offset_b_lsb: float = 0.0
    inl_a: tuple = (0.0, 0.0)          # INL bow: (quadratic, cubic) peak LSB, typ +/-1 LSB
    inl_b: tuple = (0.0, 0.0)


def draw_instance(k: int, config="base") -> Instance:
    if k == 0:
        return Instance(transfer_tag=config, noise_tag=config)
    rng = np.random.default_rng(20_000 + k)
    return Instance(
        transfer_tag=f"{config}_inst{k}" if (DATA / f"transfer_{config}_inst{k}.npz").exists() else config,
        noise_tag=config,
        aperture_mismatch_s=float(rng.normal(0, 40e-12)),
        gain_a=float(rng.normal(0, 1e-4)), gain_b=float(rng.normal(0, 1e-4)),
        offset_a_lsb=float(rng.normal(0, 1.0)), offset_b_lsb=float(rng.normal(0, 1.0)),
        inl_a=tuple(float(x) for x in rng.uniform(-0.7, 0.7, 2)),
        inl_b=tuple(float(x) for x in rng.uniform(-0.7, 0.7, 2)),
    )


# ---------------------------------------------------------------- synthesis
@dataclass
class NoisePlan:
    """Precomputed folded noise for one (instance, DUT, frequency, decimation)."""
    fs: float
    n: int
    caa: np.ndarray
    cbb: np.ndarray
    cab: np.ndarray


_PLAN_CACHE: dict = {}


def noise_plan(noise_tag, dut, fs, n, o: NoiseOpts, n_grid=1025):
    # keyed by DUT name: draws of a standard's value or contact resistance change the folded
    # noise spectrum negligibly, and recomputing it per draw would dominate run time
    key = (noise_tag, dut.name, fs, n, o)
    if key in _PLAN_CACHE:
        return _PLAN_CACHE[key]
    tr = transfer(noise_tag)
    # start at the first non-DC bin: the 1/f densities diverge at 0 Hz and DC is not synthesized
    nu_g = np.linspace(fs / n, fs / 2, n_grid)
    caa, cbb, cab = folded_csd(tr, dut, fs, nu_g, o)
    nu = np.arange(n // 2 + 1) * fs / n
    plan = NoisePlan(fs, n, np.interp(nu, nu_g, caa), np.interp(nu, nu_g, cbb),
                     np.interp(nu, nu_g, cab.real) + 1j * np.interp(nu, nu_g, cab.imag))
    _PLAN_CACHE[key] = plan
    return plan


def gaussian_pair(plan: NoisePlan, rng):
    n = plan.n
    scale = plan.fs * n / 2
    caa = plan.caa * scale
    cbb = plan.cbb * scale
    cab = plan.cab * scale
    a = np.sqrt(np.maximum(caa, 0))
    b = np.where(a > 0, np.conj(cab) / np.where(a > 0, a, 1), 0)
    c = np.sqrt(np.maximum(cbb - np.abs(b) ** 2, 0))
    k = n // 2 + 1
    w1 = (rng.standard_normal(k) + 1j * rng.standard_normal(k)) / math.sqrt(2)
    w2 = (rng.standard_normal(k) + 1j * rng.standard_normal(k)) / math.sqrt(2)
    XA = a * w1
    XB = b * w1 + c * w2
    XA[0] = XB[0] = 0.0                      # DC belongs to the offsets
    XA[-1] = XA[-1].real * math.sqrt(2)      # Nyquist bin is real
    XB[-1] = XB[-1].real * math.sqrt(2)
    return np.fft.irfft(XA, n), np.fft.irfft(XB, n)


@dataclass(frozen=True)
class Acq:
    """Acquisition mode.  decimation=0: current firmware (convert at 1 MSPS/divider).
    decimation='auto': convert at 1 MSPS and boxcar-average `divider` conversions per sample."""
    count: int = DEFAULT_COUNT
    boxcar: bool = False
    amp_scale: float = 1.0       # what-if: excitation amplitude multiplier


def synth_channels(dut, hz_req, inst: Instance, o: NoiseOpts, acq: Acq, rng):
    """Return (word, divider, a_codes, b_codes) where codes are float (boxcar) or int16."""
    o = replace(o, src_scale=acq.amp_scale)
    word = frequency_word(hz_req)
    f0 = frequency_hz(word)
    div = divider_for(hz_req)
    zt = dut.z(f0)
    tr_sig = transfer(inst.transfer_tag)
    HA, HB = tr_sig.H([f0], [zt], names=["dds"])
    amp = o.dds_amp_v * acq.amp_scale
    pa, pb = amp * HA[0, 0], amp * HB[0, 0]
    conv_rate = SAMPLE_BASE_HZ if acq.boxcar else SAMPLE_BASE_HZ / div
    per = div if acq.boxcar else 1
    n = acq.count * per
    plan = noise_plan(inst.noise_tag, dut, conv_rate, n, o)
    na, nb = gaussian_pair(plan, rng)
    t = np.arange(n) / conv_rate
    phi0 = rng.uniform(0, 2 * np.pi)
    jit = rng.normal(0, o.clock_jitter_s, n)
    ta = t + jit + rng.normal(0, o.aperture_jitter_s, n)
    tb = t + jit + inst.aperture_mismatch_s + rng.normal(0, o.aperture_jitter_s, n)
    w = 2 * np.pi * f0
    va = np.real(pa * np.exp(1j * (w * ta + phi0))) + na
    vb = np.real(pb * np.exp(1j * (w * tb + phi0))) + nb
    gref = 1 + rng.normal(0, o.ref_common_ppm * 1e-6, n)
    va = va / (gref * (1 + rng.normal(0, o.ref_indep_ppm * 1e-6, n))) * (1 + inst.gain_a)
    vb = vb / (gref * (1 + rng.normal(0, o.ref_indep_ppm * 1e-6, n))) * (1 + inst.gain_b)
    out = []
    for v, off, inl in ((va, inst.offset_a_lsb, inst.inl_a), (vb, inst.offset_b_lsb, inst.inl_b)):
        x = v / 4.096
        code = v / LSB_V + off + inl[0] * (1 - 2 * x * x) + inl[1] * (x - x ** 3) * 2.598
        code = code + rng.normal(0, o.adc_lsb_rms, n)
        code = np.clip(np.floor(code + 0.5), -32768, 32767)
        if per > 1:
            code = code.reshape(-1, per).mean(1)   # firmware int32 sums / N, no re-rounding
        out.append(code)
    return word, div, out[0], out[1]


def pack(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Interleave B15,A15,...,B0,A0 into u32 words (inverse of host decode_word)."""
    ua = a.astype(np.int64).astype(np.uint16).astype(np.uint32)
    ub = b.astype(np.int64).astype(np.uint16).astype(np.uint32)
    w = np.zeros(a.size, np.uint32)
    for bit in range(16):
        w |= ((ua >> bit) & 1) << (2 * bit)
        w |= ((ub >> bit) & 1) << (2 * bit + 1)
    return w


def decode(words: np.ndarray):
    a = np.zeros(words.size, np.uint32)
    b = np.zeros(words.size, np.uint32)
    for bit in range(16):
        a |= ((words >> (2 * bit)) & 1) << bit
        b |= ((words >> (2 * bit + 1)) & 1) << bit
    return a.astype(np.uint16).astype(np.int16), b.astype(np.uint16).astype(np.int16)


def record_json(word, div, a, b):
    w = pack(a, b)
    crc = zlib.crc32(w.astype("<u4").tobytes()) & 0xFFFFFFFF
    return dict(source_enabled=True, tuning_word=int(word), sample_divider=int(div),
                packed_samples=w.tolist(), transport_crc32=int(crc))


def setup_json(range_ohm=100, unit="virtual-1", fixture="vfix-1"):
    return dict(revision=HARDWARE_REVISION, unit_id=unit, fixture=fixture, range_ohm=int(range_ohm),
                system_clock_hz=120_000_000, dds_clock_hz=24_000_000)


# ---------------------------------------------------------------- host-equivalent pipeline
def fit_phasor(x, hz, rate):
    """Least-squares DC + cos + sin, phasor c - j s (host fit())."""
    i = np.arange(x.size)
    ang = 2 * np.pi * hz * i / rate
    M = np.stack([np.ones_like(ang), np.cos(ang), np.sin(ang)], 1)
    (dc, c, s), *_ = np.linalg.lstsq(M, x.astype(float), rcond=None)
    resid = x - M @ np.array([dc, c, s])
    return complex(c, -s), float(np.sqrt(np.mean(resid ** 2)))


def raw_z(a, b, word, rate, range_ohm):
    hz = frequency_hz(word)
    pa, _ = fit_phasor(a, hz, rate)
    pb, _ = fit_phasor(b, hz, rate)
    return feedback(range_ohm, hz) * pa / pb, pa, pb


def cal_coeffs(short, m1, z1, m2, z2):
    c = ((m1 - short) / z1 - (m2 - short) / z2) / (m2 - m1)
    a = (m1 * (c * z1 + 1) - short) / z1
    return a, short, c


def correct(m, abc):
    a, b, c = abc
    return (m - b) / (a - m * c)
