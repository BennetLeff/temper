# Supervisor construction attempt — rejected and archived

2026-09-19: The 133-component construction was rejected after the user
challenged its complexity. It is preserved in [rejected-133](rejected-133/README.md).
The canonical source and candidate have been restored byte-for-byte to the
54-component baseline at `5dde29ab3e2f1223c2d33c129ced2cf647238307`.

The next direction and exact component audit are in
[ARCHITECTURE-REDUCTION.md](ARCHITECTURE-REDUCTION.md). A smaller isolated
[sensing block](f2-open-01/README.md) is now compiled and screened; a complete
replacement protection system is not implemented yet. Existing source-build-07/native-05, construction receipt,
native evidence and logical tests describe the rejected experiment. They must
not be presented as evidence for the restored candidate or a future design.

The rejected build added a 70-part supervisor, including 12 ICs, and nine
driver, connector, bypass and discharge components. Its PCB retained unaffected
copper, with changed nets and the supervisor unrouted. No completed ERC/DRC/parity
review or acceptance is claimed for it.

Compiled-graph Boolean tests and conditional energy screens do not establish
detector latency, controller startup/retry, fuse clearing, capacitor ripple
heating, or hardware fault containment. The combined screen remains
INDETERMINATE. The passive protection/cooling milestone remains NOT MET.
