# Rev38 source authority fixture

`elec/src/source_authority.ato` is the SELV source-side candidate joined to
`receiver_isolation.ato` by `power_entry_integrated_38.ato`. The joined
Atopile build connects five physical source/receiver paths: source PERMIT
and health forward, STOP forward, and physical HOT PERMIT plus retained HOT
SESSION feedback reverse. The protocol and relay-request channels remain
assigned in the receiver fixture but have no ESP GPIO/driver producer yet.
The source circuit is partial; this is not a U4 or protected-operation PASS.

`TPS3431SDRBR` is continuously enabled. Its open-drain WDO and ENOUT pins
share a 10 kΩ SELV pull-up. `SN74LVC1G17DBVR` buffers one software-owned
heartbeat to WDI. The installed candidate CWD is Murata
`GRM1885C1H102JA01D`, 1 nF C0G ±5% at 50 V. The source-health AND also
requires the SELV rail supervisor, reset-good, and interlock high. The
reset-good and interlock signals remain external inputs with local low
defaults. This is a bounded missing-edge detector, not proof that arbitrary
wrong code will stop feeding it. ESP CPU-only reset may retain GPIO state;
source firmware must withhold WDI through boot and physical disarm. No
accepted reset-to-off bound follows from the component timeout.

Physical HOT PERMIT feedback high asynchronously presets the SELV
`SOURCE_PERMIT_SEEN_Q` memory. Its later low level drives
`SOURCE_PERMIT_LOSS_OK` low through an HCS00 NAND. Source PERMIT Q is an
HCS74 memory with raw set clock, D and asynchronous CLR_N driven by the
AND of source health, STOP_N, retained HOT SESSION feedback, and the
readback-loss condition. A held set request cannot acquire a new clock when
the clear recovers. The seen memory's separate SN74LV221A-Q1 reset clock
loads zero only while source Q and physical feedback are low, set request
is inactive, source health is high, and firmware asserts challenge-active.
The receiver protocol must still verify the matching challenge before it
issues DISARM_ACK. The raw reset clock and physical preset are distinct;
coincident-event, pulse-width, and rail-ramp behavior remain unqualified.

The source pull resistors are provisional. The assembled circuit must
calculate loaded ESP GPIO high levels, isolator input loading, supervisor
threshold and delay, one-shot width at 3.3 V, readback pulse capture,
partial-power leakage, and fault-to-clear timing. Several parts use
`TBD_REVIEW_ONLY` footprint keys solely to prevent Atopile 0.2.69 from
merging unlike MPN metadata; no land pattern or BOM sourcing is approved.

Build each target separately; passing an entry path without `-b` invokes
every configured target in this version of Atopile:

```sh
uvx --from atopile==0.2.69 ato --non-interactive build -b isolation
uvx --from atopile==0.2.69 ato --non-interactive build -b source
uvx --from atopile==0.2.69 ato --non-interactive build -b integrated
rustc --edition=2021 --test audit.rs -o /tmp/temper-rev38-isolation-audit
/tmp/temper-rev38-isolation-audit
rustc --edition=2021 audit.rs -o /tmp/temper-rev38-isolation-check
/tmp/temper-rev38-isolation-check
```

The Rust audit checks exact source and joined pin membership, MPN identity,
the WDO-to-health-to-source-clear path, physical-readback history,
independent raw set/reset clocks, and SELV/HOT domain separation. Mutation
tests remove WDO, HOT feedback, and readback-loss inputs, swap feedback,
and bridge the isolation boundary. Connectivity does not establish logic
thresholds, capture minima, or power-stage shutdown.

Manufacturer inputs: [TI TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf),
[TI SN74HCS74](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf),
[TI SN74LV221A-Q1](https://www.ti.com/lit/ds/symlink/sn74lv221a-q1.pdf), and
[Murata GRM1885C1H102JA01D](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GRM1885C1H102JA01-01A.pdf).
