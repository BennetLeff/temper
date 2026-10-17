# Fixture comparison

Timing tolerance:±0.2ns propagation/DIS,±0.5ns DT; loaded-edge/current tolerance:±20% of typical. These are model comparison tolerances, not TI production guarantees.

| Fixture | Measured | Target | Outcome |
|---|---|---|---|
|fixture-prop-c-1-cl0 channelA rise/fall|26.007 /26.007ns|26ns|PASS|
|fixture-prop-c-1-cl0 channelB rise/fall|26.007 /26.007ns|26ns|PASS|
|fixture-prop-c-1-cl1.8 loaded rise/fall|3.849 /3.928ns|8 /8ns typical|FAIL|
|fixture-prop-c0-cl0 channelA rise/fall|33.007 /33.007ns|33ns|PASS|
|fixture-prop-c0-cl0 channelB rise/fall|33.007 /33.007ns|33ns|PASS|
|fixture-prop-c0-cl1.8 loaded rise/fall|3.849 /3.928ns|8 /8ns typical|FAIL|
|fixture-prop-c1-cl0 channelA rise/fall|45.007 /45.007ns|45ns|PASS|
|fixture-prop-c1-cl0 channelB rise/fall|45.007 /45.007ns|45ns|PASS|
|fixture-prop-c1-cl1.8 loaded rise/fall|3.849 /3.928ns|8 /8ns typical|FAIL|
|fixture-dt-c-1-r20000-gap0|167.100ns|167ns|PASS|
|fixture-dt-c-1-r20000-gap200|199.900ns|200ns|PASS|
|fixture-dt-c-1-r20000-gap600|599.900ns|600ns|PASS|
|fixture-dt-c-1-r50000-gap0|399.100ns|399ns|PASS|
|fixture-dt-c-1-r50000-gap200|399.000ns|399ns|PASS|
|fixture-dt-c-1-r50000-gap600|599.900ns|600ns|PASS|
|fixture-dt-c0-r20000-gap0|185.100ns|185ns|PASS|
|fixture-dt-c0-r20000-gap200|199.900ns|200ns|PASS|
|fixture-dt-c0-r20000-gap600|599.900ns|600ns|PASS|
|fixture-dt-c0-r50000-gap0|443.100ns|443ns|PASS|
|fixture-dt-c0-r50000-gap200|443.000ns|443ns|PASS|
|fixture-dt-c0-r50000-gap600|599.900ns|600ns|PASS|
|fixture-dt-c1-r20000-gap0|203.100ns|203ns|PASS|
|fixture-dt-c1-r20000-gap200|203.000ns|203ns|PASS|
|fixture-dt-c1-r20000-gap600|599.900ns|600ns|PASS|
|fixture-dt-c1-r50000-gap0|487.100ns|487ns|PASS|
|fixture-dt-c1-r50000-gap200|487.000ns|487ns|PASS|
|fixture-dt-c1-r50000-gap600|599.900ns|600ns|PASS|
|fixture-pulse-3 (threshold width4.091ns)|rejected|12ns typical filter|characterization|
|fixture-pulse-6 (threshold width7.091ns)|rejected|12ns typical filter|characterization|
|fixture-pulse-11 (threshold width12.091ns)|passed|12ns typical filter|characterization|
|fixture-pulse-13 (threshold width14.091ns)|passed|12ns typical filter|characterization|
|fixture-pulse-31 (threshold width32.091ns)|passed|12ns typical filter|characterization|
|extra-dis--1 off/on response|27.007 /27.008ns|27 /27ns|PASS|
|extra-vcc--1 off/on response|500.009 /18000.019ns|500 /18000ns|PASS|
|extra-vdd--1 off/on response|100.004 /10000.002ns|100 /10000ns|PASS|
|extra-overlap--1 off/on response|26.008 /425.016ns|both-high: B remains low; A falls|PASS|
|extra-dis-0 off/on response|48.007 /48.008ns|48 /48ns|PASS|
|extra-vcc-0 off/on response|1200.009 /42000.019ns|1200 /42000ns|PASS|
|extra-vdd-0 off/on response|500.004 /10000.002ns|500 /10000ns|PASS|
|extra-overlap-0 off/on response|33.008 /476.016ns|both-high: B remains low; A falls|PASS|
|extra-dis-1 off/on response|80.007 /80.008ns|80 /80ns|PASS|
|extra-vcc-1 off/on response|7000.009 /80000.019ns|7000 /80000ns|PASS|
|extra-vdd-1 off/on response|2000.004 /10000.002ns|2000 /10000ns|PASS|
|extra-overlap-1 off/on response|45.008 /532.016ns|both-high: B remains low; A falls|PASS|
|DC source/sink R|5.000 /0.550Ω|5 /0.55Ω typical|PASS|
|0.22µF peak source/sink current|10.453 /13.222A|4 /6A typical|FAIL|

VDD-UVLO off/on crossings use output divided by the contemporaneous supply, preventing a falling supply itself from masquerading as UVLO shutdown. Threshold/pull-resistance corners, rail-unpowered active pull-down and nonlinear output current are not independently qualified. The output-stage fixture failures block using this surrogate as a physical gate-timing bound.
