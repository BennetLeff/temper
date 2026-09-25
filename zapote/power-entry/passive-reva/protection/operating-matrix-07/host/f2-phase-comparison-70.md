# What the two settled F2-opening cases establish

Both accepted cases use the same baseline six-file circuit closure at 120 VAC
and a 190 ohm load. Each has its own accepted cold-start/normal prefix and a
complete source-bound waveform, plus a sampled source-phase check. They model
a scripted ideal opening between VD and the bulk-capacitor bus VB.

| Injected opening phase | Opening to detector | Detector to retained gate-off | Channel already below 0.1 A before detector | Peak passive current after detector | Full-trace peak VD |
|---|---:|---:|---:|---:|---:|
| Mains crest | 61.228 µs | 106.628 ns | 2.819 µs | 8.879 A | 399.724 V |
| Mains zero crossing | 1267.940 µs | 106.768 ns | 0.788 µs | 3.715 A | 397.361 V |

The zero-crossing case takes 20.71 times as long to reach the detector edge
as the crest case. These are two measured modeled points, not a worst-case
phase sweep or an upper bound over the mains cycle. A fast gate-off response
after detection does not make the whole fault response that fast: the delay
before detection must remain a separate reported quantity.

In both cases channel current was already below 0.1 A before detection. The
waveforms therefore support retained gate-off under these conditions, but do
not show the protection causing interruption of an appreciable flowing channel
current. Neither case eliminates passive current after detection.

The modeled F2 opening separates the bulk bank from VD. It does not open the
mains path or remove the local VD capacitor and inductor energy. Consequently,
these results alone cannot justify a complete energy-interruption strategy.
The schematic retained for this campaign does not yet implement the proposed
F2/VD/VB split; no schematic change is made by this analysis.

The next cases address a different failure mechanism. SW-SHORT inserts a path
from sw to channel_source independent of the gate, with F2 held closed. Its
reported i(Vchannel) includes that failed branch. DIODE-SHORT and BOTH-SHORT
also retain F2 closed and represent failures between shared diode terminals,
not separate physical die currents. BYPASS-NEG opens F2 with the detector
bypassed; its early frozen-checker rejection alone says nothing about the
waveform, so it needs the separate detector-independent observation tool.

A defensible protection decision must therefore account separately for:

- Detection delay and retained gate-off in a controllable switch.
- Current paths that remain after the switch fails short.
- Mains-fed current and stored energy on each side of any proposed disconnect.
- Physical interrupting capability, fuse clearing and device stress, which
  these ideal-switch/generic-device simulations do not establish.

The existing manufacturer/model gaps remain in force: no selected-clamp
low-current VF guarantee over temperature/lot has been obtained; the MOSFET,
boost-diode and passive stress calculations are not thermal or SOA validation.
This comparison adds no hardware qualification and closes no untested fault.

Evidence: [crest acceptance](../faults/settled-reanalysis-40/F2-CREST38/acceptance.json),
[zero acceptance](../faults/settled-recovery-63/full-F2-ZERO/acceptance.json),
[terminal graph review](../faults/terminal-branch-gate-55.md),
[prototype implications](simulation-to-prototype-decisions.md).
