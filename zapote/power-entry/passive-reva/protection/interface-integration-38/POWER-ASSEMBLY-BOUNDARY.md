# Rev38 to cooker power assembly boundary

**Status: follow-on product power path, outside the Rev38 section-board U7 gate.**
The two frozen Atopile sources prove a
16-contact SELV control interface. They do not yet describe one cooker power
assembly. This is a source-topology finding, independent of footprint
availability or PCB placement. The current source identities are
`source-build-03` (Rev38 receipt `9433de53a1dd1c8dba86d2df6a47d96fc54e413702979518997c43f5591af911`)
and `cooker-source-02` (cooker receipt `21d303f769dccaaaf25049e87cd948d55de8ab19be478c9aab277f535d45baa4`).

| Boundary | Rev38 source | Existing cooker `Top` in mate derivative |
| --- | --- | --- |
| Inlet and protection | `AcInput38` receives already fused L, N and PE on `1714984`; F1 is the proposed off-board `LP-CC-20` assembly. | `PowerInput` retains its own `0034.3129` 5×20 F1, MOV, CMC, NTC and bypass relay. The fuse link/holder remains unqualified under the Rev38 F1 screen. |
| DC power | `PfcPower38` has its own rectifier, boost switch, F2 and bank nodes `VD_LOCAL`/`VB_BANK`; `PFC-POWER.md` uses 400 V nominal for the local reservoir. | `Top.power_in` makes a separate AC doubler and `dc_bus_plus`/`dc_bus_minus`; `Top.hb` and tank use that bus. `Top.v_bus_max` is 340 V. |
| Controller rail | Rev38 takes SELV 3.3 V through the 16-contact header. | `Top.aux_supply` derives isolated 15 V from its existing half bus, and `Top.power_mgmt` derives the ESP 3.3 V rail. |
| Between boards | The 16 contacts carry 3.3 V, return, GPIO, UART, I²C, reset-good and interlock. | The mate has the matching 16 contacts. There are no AC, DC bank, power-return or inverter bus contacts in this contract. |

Evidence is in the frozen source copies:
[`power_entry_integrated_38.ato`](elec/src/power_entry_integrated_38.ato),
[`ac_input.ato`](elec/src/ac_input.ato),
[`cooker_mate.ato`](cooker-mate/elec/src/cooker_mate.ato),
[`main.ato`](cooker-source-02/elec/src/main.ato), and
[`modules.ato`](cooker-source-02/elec/src/modules.ato). The two-source Rust
audit checks the **control header** only. Its PASS does not connect either
power stage to the other, remove the old inlet path, or power the cooker
inverter from the Rev38 bank.

## Follow-on product integration gate

The intended later product candidate has **one evaluated power-entry path**: Rev38
replaces the cooker's older fused input and front end while retaining the
existing ESP and its qualified SELV 3.3 V rail. Implementing that intent
requires a new source composition. The current `Top` import cannot be treated
as that composition just because it gives access to the ESP and interlock.
The engineering work must specify:

1. Which old `Top.power_in`, AC doubler, F1, and auxiliary-source instances
   are removed or made electrically absent, and how the existing SELV 15 V
   and 3.3 V rail will be supplied after that removal. A source connection
   must prove the rail input, return, isolation, startup and PE reference.
2. Whether the existing half bridge and tank are fed from the Rev38 bank.
   If so, define their exact positive/negative/return nodes, operating
   voltage and fault-current envelope, isolation boundary, conductor or
   connector, and retained discharge/measurement path. The old half-bus
   assumptions cannot silently be reused at the Rev38 bank voltage. In
   particular, the current 340 V `Top.v_bus_max` and 400 V nominal Rev38
   bank cannot be declared compatible by connecting names or conductors.
3. How the cooker fault latch, relay and inverter inhibit paths interact
   with the Rev38 receiver's retained HOT shutdown. A GPIO connection alone
   cannot replace the physical gate-clear path.
4. A new frozen source export and audit that checks the **power** joins and
   rejects duplicate inlet/front-end paths, open bus/return, unintended
   HOT-to-SELV joins and power sources surviving only in an obsolete branch.
   Only then make a reviewed native **product assembly** and its power harness.

The two missing cooker footprints in
[`native-readiness-02.json`](cooker-mate/evidence/native-readiness-02.json)
belong to the old F1/NTC branch. Assigning plausible library footprints to
those references would make the static probe greener but would not close the
assembly boundary. Whether those parts remain at all depends on the new
composition. Keep native-product acceptance **OPEN** until the power
interface is explicit and checked. This product gate does not delay the Rev38
source-to-PFC `native/section.kicad_pcb` deliverable; that section retains
its own F2 footprint, SELV-port, parts, pose, outline and source/native
checks. No mains or assembled fault test has run.

## Direct-bank join audit (2026-09-24)

The legacy cooker's 340 V designation is a **differential** voltage across a
split doubler, not the voltage of its positive rail to its power return.
`Top.dc_bus_plus` is about +170 V relative to the doubler midpoint
`Top.power_return`, while `Top.dc_bus_minus` is about −170 V. The tank-return
CT feeds that midpoint. In `elec/src/main.ato`, `Top` also joins the active
discharge's `mid` to `power_return`, gives its OVP comparator the positive
half-bus, and powers `AuxSupply` from that positive half-bus to the midpoint.
Those are circuit connections, not just comments or a stale net name.

Rev38 `VB_BANK` and HOT0 form one approximately 400 V PFC output; its source
does not export the legacy doubler midpoint. A wire from `VB_BANK` to
`Top.dc_bus_plus` and HOT0 to `Top.dc_bus_minus` therefore leaves
`Top.power_return` without its specified midpoint. Tying that return to
either end of the Rev38 bank instead changes the tank-current path,
half-bus discharge, OVP reference, and auxiliary-source input. Lowering the
PFC setpoint alone would not create the missing midpoint.

| Legacy `Top` dependency | Exact current join | Requirement for one-front-end composition |
| --- | --- | --- |
| Half bridge and tank | `hb.dc_bus.hv_plus` to `dc_bus_plus`; low side through `safety.ocp2_bus_in/out` to `dc_bus_minus`; `tank.out` through `ct_sense` to `power_return` | Specify one complete inverter current loop against the selected Rev38 bank, including CT placement, device stress and tank operating point. |
| Active discharge | `discharge.hv_plus/mid/hv_minus` to positive half, midpoint and negative half | Replace or re-evaluate both half-bus discharge branches against the single bank and its stored energy. |
| OVP and sensing | `safety.dc_bus.line` to the positive half-bus; OVP trip is declared around 390 V differential | Recalculate the sensing/reference and trip before using a 400 V nominal PFC bank; the old OVP does not measure the new full bank as wired. |
| SELV power | `AuxSupply` input from positive half-bus to midpoint; output 15 V into `PowerManagement` 3.3 V regulator | Re-source the 15 V input from a qualified isolated supply without a HOT-to-SELV short, then qualify the retained 3.3 V regulator and total load. |
| Precharge and relay | `PowerInput` owns the doubler, NTC and bypass; MCU relay control drives that bypass | Remove the duplicate input and map the cooker control function to Rev38's precharge/relay ownership only after a physical interlock review. |

The next source revision needs separate controller/SELV and inverter-power
interfaces, a selected bank-to-inverter topology and voltage envelope, then
an audit that proves both the supply/return joins and absence of the old
`PowerInput`/`AuxSupply` path. The current `cooker-mate` fixture deliberately
retains `Top` for ESP pin-contract checking; it must not be promoted to the
one-front-end product source or native board.
