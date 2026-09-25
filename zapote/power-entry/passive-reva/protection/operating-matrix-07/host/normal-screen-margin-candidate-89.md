# Minimum observed model-screen margins

These margins are arithmetic from the accepted receipts and `host/operating-envelope-checkpoint-53.json`, using frozen predicates in `numerical-repair/event-aware-normal-metrics/metrics.rs` (lines 294–307); `host/campaign-report-87.md` is secondary. Lower margin is `observed - lower`; upper margin is `upper - observed`; max-screen margin is `limit - observed`; drift margin is `0.005 - observed`.

| Screen | Observed field/value; minimum margin | Limiting case | Source |
|---|---|---|---|
| Input RMS voltage lower (107.999 V) | `acceptance.line_v_rms=108.000 V`; 0.001000 V | LL01/LL02/LL03 | checkpoint53 JSON |
| Input RMS voltage upper (132.001 V) | `acceptance.line_v_rms=132.000 V`; 0.001000 V | LL07/LL08/LL09 | checkpoint53 JSON |
| Settled bus lower (370.134250 V) | `acceptance.metrics.vb_min_v=375.857870 V`; 5.723620 V | LL03 | LL03 acceptance |
| Settled bus upper (409.095750 V) | `acceptance.metrics.vb_max_v=387.716140 V`; 21.379610 V | LL01 | LL01 acceptance |
| Input RMS current (15 A max) | `acceptance.metrics.irms_a=13.412054 A`; 1.587946 A | LL03 | LL03 acceptance |
| Three-cycle drift (0.005 max) | `acceptance.metrics.cycle_drift_fraction=0.004155816805`; 0.000844183195 | LL03 | LL03 acceptance |
| VD peak (500 V max) | `acceptance.metrics.vd_peak_v=387.776829 V`; 112.223171 V | LL01 | LL01 acceptance |
| VB peak (450 V max) | `acceptance.metrics.vb_peak_v=387.716140 V`; 62.283860 V | LL01 | LL01 acceptance |
| \|VDS\| peak (650 V max) | `acceptance.metrics.vds_peak_v=389.022540 V`; 260.977460 V | LL01 | LL01 acceptance |
| \|VGS\| peak (25 V max) | `acceptance.metrics.vgs_abs_peak_v=14.982226 V`; 10.017774 V | LL07 | LL07 acceptance |

The accepted 120 VAC / 190 ohm baseline at `accepted-baseline-11/acceptance.json` reports Irms 7.321738 A, bus 381.305435–385.386372 V, and drift 0.002730860843. Derived margins are 7.678262 A, 11.171185 V, 23.709378 V, and 0.002269139157. Its bound small output `numerical-repair/event-aware-normal-metrics/full-650ms-metrics.txt` reports whole-prefix peaks VD 385.496772 V, VB 385.386372 V, VDS 386.793850 V, VGS 14.982214 V, giving margins 114.503228 V, 64.613628 V, 263.206150 V, and 10.017786 V.

The 107.999–132.001 V source bounds are input-grid tolerance screens, not physical headroom or component ratings. All figures are authored model-screen margins, not device, thermal, SOA, fuse, or hardware qualification.
