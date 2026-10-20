"""Compensated HV divider for the stage-53 differential probe: values, strays, trim, CMRR.

Ladder: input -> n segments (R_seg || C_seg) -> tap -> (R_bot || C_bot) -> ground.
Each internal node (between segments, and the tap) has a stray C_g to the grounded shield.
Solved by nodal analysis at each frequency.
"""
import numpy as np

N_RATIO = 2000.0          # per-input attenuation
N_SEG = 5
R_SEG = 2.0e6
C_SEG = 33e-12
C_BUF = 1.5e-12           # buffer + clamp + pad capacitance at the tap


def transfer(f, r_seg, c_seg, r_bot, c_bot, c_g):
    """V_tap / V_in. r_seg, c_seg, c_g: arrays of length N_SEG (c_g[k] is stray at node below segment k)."""
    n = len(r_seg)
    w = 2 * np.pi * f
    y_seg = 1 / np.asarray(r_seg) + 1j * w * np.asarray(c_seg)
    y_bot = 1 / r_bot + 1j * w * (c_bot + C_BUF)
    # unknown nodes 1..n (node n is the tap); node 0 is the input, driven at 1 V
    Y = np.zeros((n, n), complex)
    I = np.zeros(n, complex)
    for k in range(n):                       # node k+1, between segment k (above) and k+1 (below)
        Y[k, k] += y_seg[k] + 1j * w * c_g[k]
        if k == 0:
            I[k] += y_seg[k] * 1.0
        else:
            Y[k, k - 1] -= y_seg[k]
            Y[k - 1, k] -= y_seg[k]
            Y[k - 1, k - 1] += y_seg[k]
    Y[n - 1, n - 1] += y_bot
    return np.linalg.solve(Y, I)[-1]


def design():
    r_top = N_SEG * R_SEG
    r_bot = r_top / (N_RATIO - 1)
    c_top = C_SEG / N_SEG
    c_bot = c_top * (N_RATIO - 1) - C_BUF
    return r_top, r_bot, c_top, c_bot


def trim_cbot(r_seg, c_seg, r_bot, c_g, f_trim=60e3):
    """C_bot that makes |H(f_trim)| equal H(DC): bisection on the HF ratio."""
    h_dc = transfer(0.01, r_seg, c_seg, r_bot, 1e-9, c_g).real
    lo, hi = 1e-9, 20e-9
    for _ in range(80):
        mid = (lo + hi) / 2
        if abs(transfer(f_trim, r_seg, c_seg, r_bot, mid, c_g)) > h_dc:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2, h_dc


def main():
    r_top, r_bot, c_top, c_bot = design()
    print(f"R_top {r_top/1e6:.3f} MOhm ({N_SEG} x {R_SEG/1e6:.2f} MOhm), R_bot {r_bot:.1f} Ohm")
    print(f"C_top {c_top*1e12:.2f} pF ({N_SEG} x {C_SEG*1e12:.0f} pF), C_bot {c_bot*1e9:.3f} nF (+{C_BUF*1e12:.1f} pF buffer)")
    print(f"tau {R_SEG*C_SEG*1e6:.1f} us; resistive/capacitive crossover {1/(2*np.pi*r_top*c_top)/1e3:.2f} kHz")
    for v_rms, label in ((500, "500 V rms"), (3000 / np.sqrt(2), "3 kV peak sine")):
        print(f"  {label}: divider {v_rms**2/r_top*1e3:.1f} mW total, {v_rms**2/r_top/N_SEG*1e3:.1f} mW/segment, "
              f"top-cap current at 60 kHz {v_rms*2*np.pi*60e3*c_top*1e3:.2f} mA rms")
    print(f"  per segment at 3 kV: {3000/N_SEG:.0f} V; tap at 1.5 kV in: {1500/N_RATIO*1e3:.0f} mV, at 3 kV: {3000/N_RATIO:.2f} V")

    freqs = np.array([10, 100, 1e3, 5e3, 20e3, 35e3, 60e3, 100e3, 1e6, 5e6])
    rs, cs = np.full(N_SEG, R_SEG), np.full(N_SEG, C_SEG)
    for cg_pf in (0.0, 0.1, 0.2, 0.4):
        cg = np.full(N_SEG, cg_pf * 1e-12)
        cb, h_dc = trim_cbot(rs, cs, r_bot, cg)
        hs = np.array([transfer(f, rs, cs, r_bot, cb, cg) for f in freqs])
        err = (np.abs(hs) / h_dc - 1) * 100
        ph = np.degrees(np.angle(hs))
        print(f"\nstray {cg_pf:.1f} pF/node: trimmed C_bot {cb*1e9:.3f} nF ({(cb/c_bot-1)*100:+.1f} % from nominal)")
        print("   f        " + " ".join(f"{f:>8.0f}" for f in freqs))
        print("   gain err%" + " ".join(f"{e:>8.3f}" for e in err))
        print("   phase deg" + " ".join(f"{p:>8.3f}" for p in ph))

    # CMRR: two dividers, each trimmed (DC on R_bot, HF on C_bot) at build time; then the stray on one
    # input shifts (lead routing, hand, coil proximity). CMRR = 20 log |H1 - H2| / |H_avg|.
    print("\nCMRR (positive dB) after trim, when input B's strays shift by dCg per node after trimming:")
    cg0 = np.full(N_SEG, 0.2e-12)
    cb, _ = trim_cbot(rs, cs, r_bot, cg0)
    for dcg in (0.005, 0.02, 0.05, 0.1):
        row = []
        for f in (1e3, 60e3, 100e3, 1e6, 5e6):
            ha = transfer(f, rs, cs, r_bot, cb, cg0)
            hb = transfer(f, rs, cs, r_bot, cb, cg0 + dcg * 1e-12)
            row.append(-20 * np.log10(abs(ha - hb) / abs(ha)))
        print(f"  dCg {dcg:5.3f} pF: " + "  ".join(f"{f/1e3:>6.0f} kHz {c:6.1f} dB" for f, c in zip((1e3, 60e3, 100e3, 1e6, 5e6), row)))

    # Untrimmed spread from part tolerances, to size the trim ranges.
    for r_tol in (1e-3, 1e-2):
        untrimmed_spread(r_tol, r_bot, c_bot)


def untrimmed_spread(r_tol, r_bot, c_bot):
    rng = np.random.default_rng(53)
    dc, hf = [], []
    for _ in range(2000):
        r = R_SEG * (1 + rng.uniform(-r_tol, r_tol, N_SEG))
        c = C_SEG * (1 + rng.uniform(-0.05, 0.05, N_SEG))      # C0G +/-5 % (J)
        cg = rng.uniform(0.1e-12, 0.3e-12, N_SEG)
        rb = r_bot * (1 + rng.uniform(-r_tol, r_tol))
        cbn = c_bot * (1 + rng.uniform(-0.05, 0.05))
        h0 = transfer(0.01, r, c, rb, cbn, cg).real
        h60 = abs(transfer(60e3, r, c, rb, cbn, cg))
        dc.append(h0 * N_RATIO - 1)
        hf.append(h60 / h0 - 1)
    dc, hf = np.array(dc) * 100, np.array(hf) * 100
    print(f"\nresistors +/-{r_tol*100:g} %: untrimmed DC ratio error: 1st-99th pct {np.percentile(dc,1):+.3f} .. {np.percentile(dc,99):+.3f} %")
    print(f"  untrimmed 60 kHz vs DC mismatch: 1st-99th pct {np.percentile(hf,1):+.2f} .. {np.percentile(hf,99):+.2f} %")


if __name__ == "__main__":
    main()
