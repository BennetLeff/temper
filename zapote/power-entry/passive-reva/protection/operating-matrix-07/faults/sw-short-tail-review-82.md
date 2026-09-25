# SW-SHORT endpoint-tail review

The extracted tail contains 256 rows and 42 columns; every numeric value is finite. Time spans `0.6544014666667` to `0.6544026486296868 s` (1.181963 us). There are two repeated-time groups: `0.6544026486296867 s` appears five times and `0.6544026486296868 s` appears three times. The source receipt and both file hashes are preserved in `sw-short-tail-review-82.json`.

The logic is mostly steady at the endpoint: `q=5 V`, `en=5 V`, `fault=0 V`, `pcl_hold=0 V`, and `gate` stays near `0.77 uV`. `pwm` rises through the window to `2.42956 V`. `xdriver.driver_req` is near zero until the final repeated-time group, where it changes from near zero to `15 V`; this is temporally coincident with the final repeated rows, but gate and the other saved controller states do not change. That observation does not prove causality.

Electrical quantities are near-DC and smooth over this tiny window: `i(Lboost)` and `i(Vchannel)` move together from about `181.316` to `181.994 A`; `v(vd)` and `v(vb)` remain near `384.17 V`; `v(sw)` is about `0.181–0.182 V`; both diode-sense currents remain sub-microampere. The endpoint branch report therefore cannot distinguish a late driver bridge event from stiffness in the high-current path with ideal zero-volt probes.

Two state-grounded hypotheses remain:

1. The late `xdriver.driver_req` transition triggers a hidden mixed-signal algebraic event despite unchanged gate/q/en/fault/pcl states. Holding only that request at its pre-transition value from the same saved state would disprove this if collapse timing were unchanged.
2. The near-DC 182 A channel path and 384 V reservoir nodes are numerically stiff around ideal zero-volt sense probes; adding controlled small finite probe impedance from the same saved state would disprove this if collapse timing were unchanged.

This tail is diagnostic only. It is not evidence of whole-run maxima, fault-response completion, or acceptance. No solver, FIFO, raw trace, or source file was touched.
