# Diode-short same-row stress review

The completed diagnostic preserves every original55 observation. Its three pipeline stages and wrapper exited zero; the source identities and report hash match. The completed wrapper recorded the full raw hash unchanged before and after analysis.

At **661.689081 ms**, the recorded inductor current is **78.515762 A** while q and enable are off, the gate is **46.23 microvolts**, and MOS channel current is approximately **0.132 nA**. This is a direct sampled witness of passive-path current despite gate-off, not a continuous-time assertion.

At **657.284009 ms**, F2 current is **-229.126676 A**, MOS channel current **+231.156290 A**, and inductor current approximately **-81.45 microamps**. F2 positive direction is VD toward VB. Source connectivity and these simultaneous signs support modeled bank discharge through the shorted diode terminal and conducting MOS path.

The **-326.5 kA** diode1-sense extreme includes the modeled terminal-short branch; it is not a physical diode die-current prediction. Its causal mechanism remains unproven. The model omits material physical impedances and survival behavior.

The case remains **FAIL** because detection exceeds the unchanged 2 ms window. This diagnostic changes no acceptance criteria and establishes no hardware, thermal, SOA or interruption qualification. Exact witnesses and evidence hashes are in parent-result-review-103.json.
