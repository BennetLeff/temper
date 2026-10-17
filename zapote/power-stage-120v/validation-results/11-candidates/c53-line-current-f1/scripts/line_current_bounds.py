"""Desk estimates (not committed evidence) for provision A.
1. Line current reachable with the firmware limits defeated, capped only by the tank-CT hardware trip.
2. Pan resistance above which the 15 A inlet hold (not the tank ceiling) binds at the shipping ceiling.
Model: series-resonant tank, fixed frequency, tank current envelope proportional to |v_line| (unsmoothed bus),
sinusoidal tank current within a switching period; P_pan = I_tank,rms^2 * R_eq; P_in = P_pan / eta.
Repo inputs: CT trip band 64.55-76.09 A peak (DECISIONS 551 / 851); eta_min 0.93 (input_limits.c);
aux 0.26-0.887 A (blower_aux.h); hold 13.5 A inlet bound, e_est 10 % (input_limits.h);
shipping tank ceiling 17.5 A (TANK_CEILING_DEFAULT_A); pan R_eq examples from the nameplate study
(931 W at 22 A -> 1.92 ohm; 1239 W at 28 A -> 1.58 ohm, input_limits/tank_freq comments)."""
import math
V, eta = 120.0, 0.93
def line_a(i_tank_line_rms, r):
    return i_tank_line_rms ** 2 * r / eta / V
print("1. firmware defeated, tank peak held just below the CT trip low corner")
for pk in (64.55, 70.18):
    i_sw_rms_crest = pk / math.sqrt(2)          # switching-period RMS at the line crest
    i_line_rms = i_sw_rms_crest / math.sqrt(2)  # line-cycle RMS of a |sin| envelope
    for r in (1.58, 1.92, 2.5, 3.0):
        print("   CT peak %.2f A  tank line-RMS %.1f A  R_eq %.2f ohm -> line %.1f A" % (pk, i_line_rms, r, line_a(i_line_rms, r)))
print("2. shipping ceiling 17.5 A: inlet hold binds only above R_eq")
for aux in (0.26, 0.887):
    i_ps_hold = (13.5 - aux) / 1.10
    p_pan = i_ps_hold * V * eta
    print("   aux %.3f A: I_ps hold %.2f A, P_pan %.0f W, binds for R_eq > %.2f ohm" % (aux, i_ps_hold, p_pan, p_pan / 17.5 ** 2))
print("3. hardware trip window on the power-stage share (R5 sees the bridge only; PS2/PS3 tap ahead of BR1)")
for aux in (0.26, 0.887):
    print("   aux %.3f A: highest regulated true I_ps if e_est holds = %.2f A; I_ps for 15.0 A total = %.2f A" % (aux, 13.5 - aux, 15.0 - aux))
print("   mean-detector reading for a sinusoidal envelope = 2*sqrt(2)/pi = %.4f x RMS" % (2 * math.sqrt(2) / math.pi))
