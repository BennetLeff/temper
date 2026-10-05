# Qualification and rejecting controls

The exact two-port fixture has analytic matrix
`[[3.141592654, 1.884955592], [1.884955592, 1.884955592]]` nH.
One-rank and four-rank runs, including the explicit GMRES restart 200 setting,
agree at the recorded precision. The floating-conductor fixture is nonuniform:
it checks elemental-field output and field/energy consistency, not an analytic
closed-form inductance for that particular mesh.

The actual two-port paired excitation passes the independent energy check.
A separate actually solved reversed-current case is rejected for excitation
identity, mutual error and sign. Other controls reject an unconverged field,
leg-A fields offered for leg-B geometry, degenerate tetrahedra, and a high-RAM
profile offered to this 32 GiB host. Timeout and RSS controls terminate owned
test processes.

The first `negative-convergence-resource.json` records successful process
execution only; its solver result is unconverged and rejected. The repeated
`negative-convergence-v2` uses the updated receipt that explicitly reports
`SOLVER_REJECTED` despite a zero runner exit code.

`negative-synthetic-swapout.json` is a **software controller test with an
injected counter**, not observed system paging. No real paging was induced.
`swap-counter-monitor-smoke.json` exercises the real kernel-counter reader on
an owned tiny process. Neither is a hardware or PCB qualification result.
