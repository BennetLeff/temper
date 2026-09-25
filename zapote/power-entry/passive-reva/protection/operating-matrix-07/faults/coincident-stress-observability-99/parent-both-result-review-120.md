# BOTH-SHORT: gate-off with continuing current

The completed same-row diagnostic confirms modeled current remains after the control signals turn off. At the final 662 ms sample, latch q=0, enable is approximately zero and gate voltage is about 88 nV, while Lboost carries **435.791 A** and the channel-sense branch carries **435.636 A**. That branch includes the gate-independent failed-switch path.

At the first sampled simultaneous off state, 654.167541 ms, the idealized model reports 22.147 kA in that branch and -22.114 kA through F2 (positive reference VD to VB), consistent with discharge toward VD from the bank. These values are model observations, not credible physical peak-current or device-survival predictions. The entire 1,400,451-row off subset has both inductor and channel-path currents above 0.1 A; sample counts do not establish continuous-time retention or duration.

The complete archive retained its before/after digest, all three diagnostic stages exited zero, and every original frozen55 field was independently compared and unchanged. The **FAIL** disposition in campaign-verdict-118.json remains: the unchanged all-row 100 A inductor screen failed before the formal fault checker category was reached. No protection pass, hardware qualification, or causal explanation of the largest numerical transients is claimed.

The companion JSON binds exact samples, raw identity, source and diagnostic hashes.
