# Power-entry HOT receiver and retained shutdown design

Status: architecture specification for review, 2026-09-23. This does not authorize a mains build, claim a completed schematic, or select an MCU part.

## Decision and boundary

Develop one integrated power-entry authorization candidate with a small HOT-side receiver MCU. Keep fault detection, retained fault inhibit, and gate disable in HOT hardware. The MCU owns command identity and sequencing; it cannot make a stopped power stage run by an ordinary START command after a captured fault. The SELV ESP32-S3 owns the user interface and creates a fresh start intent only after observing a released button followed by a new press in the new session.

This work attaches to the 54-component passive-rectifier baseline identified in `zapote/power-entry/passive-reva/protection/ARCHITECTURE-REDUCTION.md`. It covers PFC gate authorization and the related stop/restart path. F1/F2 interruption, capacitor energy, cooling, inverter safety, insulation, and the rest of the appliance retain their own acceptance work. The design follows the reduction decision: local hardware shutdown and fresh arm belong in a separate protection function; precharge, startup deadline, and downstream load sequencing belong to system control with explicit interfaces.

### Alternatives considered

| Approach | Benefit | Decisive unresolved cost |
| --- | --- | --- |
| HOT receiver MCU plus hardware fault memory (selected development path) | Explicit session and single-use START semantics; restart sequencing stays legible | MCU firmware, persistent session identity, isolation channels, reset behavior, and physical qualification are still needed |
| ESP-only source plus hardware memory | Removes a HOT processor | Requires an implemented, bounded GPIO/queue/reset contract and a hardware handshake that rejects delayed old revalidation and ARM edges; Rev37 does not prove either |
| Entirely discrete handshake | Avoids receiver firmware | Requires more stateful logic and a proof that old edges cannot clear a fault or create a new session; no such circuit exists |

This selection is for the next design experiment, not proof that the other approaches are impossible. Rev35 and Rev37 are different-scope connectivity fixtures; their component counts are not a reliability comparison. The ATmega328P in Rev35 is not the selected production part. Microchip currently marks it not recommended for new designs.

## Safety invariants

1. A qualified latched trip removes PFC gate permission through hardware, independently of ESP scheduling and HOT receiver firmware. Recovery of the detector output does not restore permission.
2. A start message can set RUN only in the currently prepared session. START cannot load or repair the retained HOT fault memory. A delayed, duplicate, or prior-session message cannot start the PFC.
3. Physical HOT PERMIT low directly clears RUN. Once PERMIT has been observed high in a session, its subsequent loss also invalidates that session. Reconnection alone cannot restore either state. The source must observe physical disarm before it may seek a new session.
4. A new session requires a physical PERMIT-low observation *after* the invalidating event, healthy HOT inputs, RUN held low, and one controlled revalidation operation. A new user press after that session is published is required for START.
5. Loss of a required rail, broken isolator path, missing required execution, or unpowered logic leaves the gate path off within a separately specified response bound. A valid logic level in an unpowered or partly powered device is not assumed.
6. A fault arriving during revalidation or immediately before START wins. Once a session is published, neither receiver firmware nor an old command may reload the HOT fault memory inside that session.

These invariants assume the source does not invent user presses and the local command link is protected against accidental corruption, not an active adversary. A HOT MCU cannot independently witness a UI button connected only to the ESP. An arbitrary failure of the receiver firmware or output pin is a separate fault to contain with the hardware watchdog and latch; neither is currently qualified.

## Circuit partition and signal ownership

```text
SELV ESP/UI -- command + maintained PERMIT --> isolation --> HOT receiver MCU
             <-- response ------------------- isolation <-- HOT receiver MCU
             <-- physical PERMIT readback --- isolation <-- HOT PERMIT node
             <-- retained HOT validity ------ isolation <-- HOT fault memory

HOT detector/rail/permit/watchdog trips --> retained HOT_SESSION_OK clear
HOT_SESSION_OK + HOT_RUN + physical PERMIT + rail/driver-valid
    --> local default-off gate-driver permission --> UCC27624 ENA --> STW gate
```

`HOT_SESSION_OK` is the canonical memory of a captured, session-invalidating HOT event. The proposed implementation class is an HCS74-style D flip-flop with D tied high, asynchronous `/CLR` driven by the qualified trip/POR network, `/PRE` held inactive, and a single controlled revalidation clock. Its Q is low after a trip. This is a topology candidate, not a pin-complete electrical design: clear pulse width, POR, recovery/removal, logic fan-in, and rail-ramp behavior must be proven against the selected devices. Do not assert asynchronous preset and clear together as a substitute for reset dominance.

`HOT_RUN` is separate retained state. Its clear path includes `HOT_SESSION_OK` low, physical PERMIT low, and faults that demand immediate gate inhibition. A retained `PERMIT_SEEN_IN_SESSION` bit is set by the first qualified physical PERMIT high after preparation. Only `(PERMIT_SEEN_IN_SESSION AND NOT physical PERMIT)` is a PERMIT-loss trip to `HOT_SESSION_OK`. Keep the seen bit asserted through that trip until the controlled next preparation, or its feedback could release the clear condition prematurely. Normal PERMIT low before the first high must not hold session memory in clear, since that would deadlock preparation. A fast direct inhibit may parallel the latch output, but every condition classified as requiring a new user session must also be captured in retained memory. Intentionally recoverable switching-cycle limits must be classified separately; they must not accidentally masquerade as session-invalidating trips.

The revalidation clock is gated by a retained `DISARM_SEEN_AFTER_TRIP` condition derived from the *physical* HOT PERMIT node, plus fault-free rails and RUN-low observation. `DISARM_SEEN_AFTER_TRIP` must be cleared by a new trip and set only after PERMIT is seen low following that trip. A wire break can satisfy the physical-low condition; it does not by itself authorize revalidation. The MCU must also complete a new protocol session and the source must acknowledge its own physical disarm. The exact flop/gate realization and simultaneous trip/revalidation behavior are electrical design tasks, not assumed properties of this block diagram.

The reverse path needs three distinct meanings: receiver protocol response, physical HOT PERMIT readback, and retained HOT validity. A raw rail-health bit cannot replace retained validity, and a PERMIT-dependent health bit causes startup deadlock if required before PERMIT can rise. Rev35's single reverse ISO7741F channel is therefore insufficient for these independent functions as currently allocated; the next joined schematic must allocate and audit the added isolated channels. No direct conductive connection crosses the SELV/HOT boundary.

At UCC27624, ENA receives an actively driven permission with a local default-low network sized from worst-case input threshold, internal pull-up, output leakage, and rail sequence. A floating ENA is enabled by the part's internal pull-up. Driver supply present while logic supply is absent must leave ENA low and the loaded STW gate off. Driver disable propagation is only one term in the detector-to-current-cessation budget. The direct-drive baseline, Rev35 control candidate, and proposed driver must be joined into one source/native schematic before claiming the path exists.

## Session transaction

1. **Trip or stop.** Hardware clears `HOT_SESSION_OK`, RUN and gate permission. Receiver invalidates its current session and stops producing a RUN-set output. Source clears its permit latch on retained HOT invalid feedback, physical PERMIT readback loss, or source-health loss. A fault returning healthy does not undo these states.
2. **Prove disarm.** The source requests PERMIT low and observes both its local latch output and the physical HOT-side PERMIT readback low. HOT hardware records physical PERMIT low after the trip. A missing readback, partial power, or timeout stays locked out.
3. **Prepare without starting.** With RUN low and all classified trip inputs healthy, the receiver durably allocates a session identifier that cannot repeat after receiver reset or power loss. While `HOT_SESSION_OK` remains low, it sends PREPARE_CHALLENGE(session). The source replies DISARM_ACK(session) only after both physical-low observations in step 2. The receiver accepts that acknowledgement only for its pending identifier and while physical HOT PERMIT is still low. In the controlled preparation phase, hardware clears `PERMIT_SEEN_IN_SESSION` while Q/RUN remain low; it must not clear that bit at the original fault edge. After verifying that the fault-clear condition has been removed, the receiver executes one controlled hardware revalidation, checks retained validity feedback, and publishes READY(session). Revalidation cannot set RUN. A delayed PREPARE_CHALLENGE or DISARM_ACK from another session is rejected.
4. **Create fresh intent.** After receiving that new session, the ESP observes button release and a later press. It sets its source PERMIT latch, waits for both local and physical HOT PERMIT-high readbacks, then sends REQUEST(session, intent). The receiver replies ACK(session, intent). A held press, prior queued request, or old intent is rejected. Loss of either readback aborts this transaction.
5. **Start once.** The ESP sends START for the matching outstanding session and intent. The receiver consumes it once. RUN may set only while the independent hardware conditions are still true. Further START frames do not create another RUN transition.

The receiver's session identity must be committed durably before a challenge is published. The implemented storage scheme must survive interrupted writes, reject ambiguous/corrupt state, and fail closed at counter exhaustion. CRC/framing checks detect accidental message corruption; they do not provide freshness. The receiver must reject prior identifiers after its own reset. The source must discard pending intents on its reset and must not attach an old intent to a newly published session. Rev13's model is a logical starting point, not a wire decoder or persistence implementation.

The receiver watchdog feed must depend on execution of the decoder and safety state machine, not a free-running peripheral. Its timeout clears or inhibits the hardware permission path. The ESP-side watchdog feed likewise depends on completed local control/safety work and accepted session traffic. Neither watchdog may be disabled merely to make its output appear healthy; TPS3431 WDO can be high while its watchdog is disabled.

## Reset and timing contract

The ESP32-S3 can perform a CPU-only reset without resetting most peripherals. Therefore an ESP boot routine setting GPIO low is insufficient evidence that the pins were low throughout reset. On every boot, source policy discards pending intent, stops software-owned WDI edges, requests outputs low, and waits for physical source-latch and HOT PERMIT-low readbacks before any new session. GPIO pulse generation must have one software owner, no DMA/timer pulse source, no surviving deferred write queue, and an explicit maximum sample-to-pin-write interval.

An MCU receiver cannot instantly observe an ESP CPU reset that leaves external signals unchanged. A START already in flight could arrive before the source watchdog expires. The system must choose and prove one of these contracts during implementation: an independent reset indication reaches the HOT hardware before START can be accepted, or a product-approved bounded interval permits continued authorization until watchdog detection and forbids claiming immediate reset shutdown. If the product requires no start after the instant of any CPU-only reset, the latter contract is insufficient. No present Rev35/37 evidence resolves this choice.

Each session-invalidating fault class needs a named electrical producer, polarity, guaranteed pulse/level at the receiving latch, and response-time limit. A fault shorter than a detector's or latch's guaranteed capture time is outside its claim. Rev37's TPS3890 MR requires at least 1 µs low to guarantee RESET; it must not be used as the only memory for shorter qualified faults. Rail collapse must default invalid when logic returns. The acceptable maximum time from fault to STW current cessation must be set from the power-stage hazard and measured through detector, latch, EN, loaded gate, and commutation; no value is assigned by this architecture spec.

## Implementation and verification boundary

The next implementation should be one joined Atopile candidate with exact source/receiver, physical readbacks, retained fault memory, actual F2/PFC detector outputs, AUX/logic rail supervisors, and UCC27624/STW path. It needs an exact-pin netlist audit with deliberate miswire mutations, a source-to-native KiCad parity review, and a complete component/isolator channel census. Rev35's 226 instances and Rev37's 30 instances must not be added or compared as whole-system totals. Keep the 54-part canonical baseline unchanged until the joined candidate is independently accepted.

Implement the receiver decoder, durable session identity, watchdog feed ownership, and actual ESP GPIO driver before treating protocol model tests as acceptance. Tests must inject: short qualified fault followed by delayed old frames; PERMIT break/reconnect; trip during revalidation and START; receiver reset and interrupted counter write; ESP CPU-only reset with retained outputs; stalled MCU; logic-rail loss with driver supply present; isolator partial-power states; and all defined fault classes. The key negative tests must show the gate path stays disabled, not merely that software reports a fault.

The first physical campaign is low-voltage fault injection on an assembled prototype with captures of detector output, retained latch, PERMIT, driver EN, loaded gate and switch current. The existing `interface-integration-24/bench-capture.md` is a protocol starting point. A mains build decision additionally requires reviewed schematic, BOM, native board, insulation/creepage, ERC/DRC, thermal and fuse/interconnect qualification. The passive milestone remains NOT MET until its separate requirements close.

## Source basis

- Project state: `zapote/power-entry/passive-reva/protection/ARCHITECTURE-REDUCTION.md`, `interface-integration-35/README.md`, `interface-hardware-only-37/README.md`, and `interface-handshake-13/command/design.md`.
- TI [SN74HCS74](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf), [TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf), [TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf), and [UCC27624](https://www.ti.com/lit/ds/symlink/ucc27624.pdf) data sheets.
- Espressif [ESP32-S3 reset behavior](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/misc_system_api.html); Microchip [ATmega328P lifecycle status](https://www.microchip.com/en-us/product/atmega328p).
