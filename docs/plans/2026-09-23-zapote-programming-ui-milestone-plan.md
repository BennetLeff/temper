---
title: Zapote programming and UI service interface screen
date: 2026-09-23
status: implementation-ready
---

# Programming and UI service interface screen

## Decision

Record the competing MCU pin/domain claims and provide an executable gate for a
possible SELV UART0 service interface. The result is a wiring and access
**screen**, not an accepted MCU assembly, product UI, or safe service port.
Rev38 remains a separate moving source. The gate binds only committed source
bytes and must fail on drift.

## Work

1. Bind the legacy electrical MCU symbol/module, firmware pin declarations,
   and unadopted Rev38 pin-fit inventory by file hash. Record each conflicting
   GPIO, UART0 direction, EN/IO0 boot behavior, rail and return, and the
   unbuilt I²C isolation claim in a machine-readable ledger.
2. Implement a Rust gate that checks those source identities, reports the
   current conflicts, and screens hypothetical service cases. Reject pin
   swaps or duplicate allocation, missing 3V3/return, held-low EN/IO0,
   powered-off backfeed, and an isolation claim without a real barrier.
3. Treat programmer-triggered reset as a power-stage event. Service access
   remains indeterminate unless independently evidenced isolation/discharge
   before access **or** measured reset-to-PFC-and-inverter-stop with no
   automatic rearm. A retained expander command must not be credited as stop.
4. Do not draw a native connector from the available fan/RTD connectors.
   Service connector pin count, ESD, mechanical access, off-state I/O
   protection and owner are unselected. Record this as a construction blocker.

## Verification

Run the Rust unit/mutation tests, source hash check and deterministic case
matrix. Negative controls must fail individually. No Atopile fixture/netlist
claim is made while the physical connector and MCU pin contract remain open.
