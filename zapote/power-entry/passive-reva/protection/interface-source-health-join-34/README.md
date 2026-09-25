# Compiled SELV source-health join, fixture 34

This fixture compiles the source permit latch from fixture 30 together with the
buffered TPS3431 heartbeat producer from fixture 32. It makes one electrical
connection that was previously only an interface contract:

`TPS3431 WDO + ENOUT -> SOURCE_WATCHDOG_GOOD -> source-health AND -> /CLR1`

`TPS3431 WDO` and `ENOUT` remain the two allowed open-drain outputs on one
10 kOhm pull-up. The standalone fixture-30 pulldown on that same watchdog-good
net is omitted here: in the joined circuit it would divide the 10 kOhm pull-up
to about half of SELV3V3 when both open-drain outputs release. The reset-good
and interlock external inputs keep their fixture-30 10 kOhm pulldowns. The
producer's 100 kOhm heartbeat and WDI pulldowns remain. No push-pull output is
connected to the open-drain watchdog net, and there is only one pull-up on it.
Fixture 32 also had a 10 kOhm reset-good pulldown; the join deliberately keeps
one 10 kOhm pulldown rather than placing both in parallel. This reduces the
candidate GPIO's static high load from about 0.66 mA to 0.33 mA at 3.3 V.
Loaded GPIO VOH for the exact ESP module remains unverified, so that signal is
not electrically signed off.

The watchdog timing capacitor, supply connections, Schmitt heartbeat input,
WDI buffer, source latch, rail supervisor, and ISO7741F permit channel keep the
fixture-30/32 pin-level behavior. `SOURCE_VALIDATED_HEARTBEAT` must receive
software-generated edges only after a validated frame in a deliberately
re-armed session. There is no free-running heartbeat timer. Fixture 32's
`SOURCE_RESET_GOOD` GPIO producer and the true reset detection logic remain
external; the source-side reset input is still passively biased low.
The ISO7741F B permit channel is checked end to end. A/C/D are intentionally
held inactive, so this join does not validate command, relay, or response
channel allocation.

## Fault and re-arm contract

- A missing WDI edge makes the TPS3431 assert the watchdog-good net low; the
  AND chain asynchronously clears the source permit latch.
- Recovery of WDO, watchdog service, reset-good, peer traffic, or rail health
  does not set the latch. Only a new low-to-high `SOURCE_REARM_PULSE` after
  health and rail qualification sets it.
- CPU-only ESP32-S3 reset is a known counterexample: if the GPIO pad is retained
  high and software resumes accepted-frame heartbeat service before the
  watchdog expires, the source latch sees no fault and permit can remain set.
  The watchdog timeout case is captured; CPU-only reset detection is not
  physically joined or proved by this circuit.
- Re-arm is a clock input to SN74HCS74. The producer must provide a valid
  low-to-high edge with the datasheet's required VIH, pulse width, and setup
  conditions at the actual SELV rail. A pulse while asynchronous clear is
  asserted must be ignored and must not turn into a new edge when clear lifts.
- Watchdog timeout and downstream asynchronous clear must meet the latch's
  minimum clear pulse width. The firmware contract withholds WDI until manual
  re-arm after a watchdog event, so the intended timeout fault stays asserted
  during recovery. Arbitrarily narrow external health glitches are not captured
  by this discrete model.
- TPS3431 timeout estimate for 1 nF is 132.4 ms typical and 119.82–144.98 ms
  with an ideal capacitor. These are not qualified board limits; C tolerance,
  leakage, temperature, propagation and output conditions are excluded. No
  end-to-end current-cessation maximum is established.

## Verification

Offline Atopile 0.2.69 build emits `build/default.net`. `audit.rs` verifies
critical compiled pin membership and that the joined watchdog-good net has
exactly one pull-up and no fixture-only pulldown. `fault_model.rs` checks the
watchdog-timeout latch behavior, explicit fresh re-arm, and the CPU-only reset
counterexample. These are compiled connectivity and discrete contract checks,
not analog simulation, silicon reset characterization, or bench evidence.

The watchdog DRB0008A, source supervisor DSE0006A, and LVC1G17 SOT-23-5
footprint keys remain `TBD_REVIEW_ONLY`; no production footprint is bound for
those parts. The LVC1G17 uses a distinct review-only footprint key because
Atopile 0.2.69 otherwise aliases MPN metadata for the LVC1G08 and LVC1G17,
which share the generic `Package_TO_SOT_SMD:SOT-23-5` key. This separates
export metadata; it does not define or approve a different land pattern. The
LVC1G17 remains a standard SOT-23-5 package and must be bound and verified
before layout.

Reproduce from this directory:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/source_health_join.ato:SourceHealthJoin
rustc --edition=2021 audit.rs -o /tmp/source-health-join-34-audit
/tmp/source-health-join-34-audit
rustc --edition=2021 fault_model.rs -o /tmp/source-health-join-34-model
/tmp/source-health-join-34-model
```

## Primary references

- [TI TPS3431 datasheet](https://www.ti.com/lit/ds/symlink/tps3431.pdf)
- [TI SN74LVC1G17 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf)
- [TI SN74LVC1G08 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf)
- [TI SN74HCS74 datasheet](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf)
- [TI TPS3890 datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf)
- [TI ISO7741 datasheet](https://www.ti.com/lit/ds/symlink/iso7741.pdf)
