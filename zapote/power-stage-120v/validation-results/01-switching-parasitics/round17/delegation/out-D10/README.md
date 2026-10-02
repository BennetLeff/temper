**FAIL for integration: native-17 J4 agrees with its source/netlist and retains the CT burden, but the controller/harness counterpart is incomplete and 280 V exceeds the AMC1311B linear range.**

Full D-10 / task-06 report: [controller interface](../../../../06-controller-interface/README.md).
It preserves the previous CT record and covers all 16 pins, all five standalone
counterparts plus the read-only root controller, default states, levels,
current budgets, timing and the missing-harness requirements.

Method: read-only source/netlist/native extraction and explicitly conditional
DC arithmetic at base `f9b13b483d6d4ed52439d4da419c7670bab6966c`.
[Scripts and committed outputs](../../../../06-controller-interface/scripts/)
make the numeric and structural findings rerunnable. The full report cites
vendor revisions/pages and [D-5](https://github.com/BennetLeff/temper/pull/1629).

Limits: no physical qualification, no full supply/harness current bound, no
actual ADC code for an absent receiver, and no verified gate dead-time floor.
Owner decisions: full-bridge controller and harness, bus range/receiver,
PERMIT/BUS_FAULT guarantees, CT consumers and supply/return allocation.
No design source, board, firmware or existing round-17 result was edited.
