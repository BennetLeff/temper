# BOTH-SHORT post-capture interpretation

This review covers the complete 0.662 s capture and does not accept the fault,
change checker criteria, or make a hardware claim.

The transport completed: 32,036,953 rows were produced and host, compression,
adapter, decoder, and decompressor stages exited zero. The validator exited
one with `REJECTED: all-row node screen Lboost: 435.79078242060086 > 100`.
This is a completed capture with a screen failure, not an incomplete
transport. The all-row node screen has precedence, so the frozen checker does
not assign the formal `ProtectionGap` category that a failed-short case could
reach only after earlier screens pass.

The adapter reports an injection at 0.6541666661706754 s, detector rise at
0.6541667817225999 s, and sampled latch-off at 0.6541675414086254 s, all
within the declared 2 ms event window. Those timestamps are source-bound
adapter observations only; they do not override the failed Lboost screen or
establish protection acceptance. The own normal-prefix and phase analyses are
still pending, so this capture cannot yet be described as beginning from an
accepted operating condition.

Reported post-injection peaks are model diagnostics: channel 192.3 kA,
post-detector 28.8 kA, post-latch 22.1 kA, Lboost 435.8 A, F2 branch 22.5 kA,
Dboost1 sense 333.8 kA, and Dboost2 sense 5.80 kA. These idealized currents
must not be called physical MOS, diode-die, package, thermal, SOA, or hardware
currents. In BOTH-SHORT, `Sswfail sw channel_source` is a gate-independent
1 mOhm parallel branch, so `i(Vchannel)` includes that failed branch; the
diode-side short and its zero-volt sense sources add further ideal-network
current paths.

The rejected result should remain retained evidence. Once the pending
prefix/phase review is complete, the existing coincident-stress observability
diagnostic can be reused on this immutable archive if a same-row current and
control summary is needed. No new diagnostic framework is warranted. Any
future disposition must keep the node-screen failure, formal checker category,
prefix validity, and model-current interpretation separate.

Source bindings: case SHA-256
`c35139cff49f8f43db43a4dca9cff13c06c0289150b09dab12ba5aff29ffcb51`,
`protection.inc` SHA-256
`61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8`, and
manifest SHA-256
`92345035c765b9132540e067b1ffe3ce06e4845095671328700386502dc0479b`.
