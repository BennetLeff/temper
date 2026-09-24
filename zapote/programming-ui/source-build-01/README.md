# UART0 SELV lab coupon

This is a **mains-disconnected MCU programming evaluation coupon**, not an
appliance service port or an accepted MCU assembly. The input is Atopile
`elec/src/service_coupon.ato`; the compiled netlist, native KiCad schematic,
routed board, checks and receipts are in `../evidence/service-board-01/`.

| Pin on J1 Tag-Connect pads and J2 target header | Target signal | Meaning |
| --- | --- | --- |
| 1 | GPIO43 / TXD0 | ESP output, through 499 R to programmer RX. |
| 2 | GPIO44 / RXD0 | ESP input from programmer TX. |
| 3 | EN | Active-low reset request; target owns pull-up/RC/button. |
| 4 | IO0 | Download strap request; target owns pull-up/button. |
| 5 | 3V3 | Intended target-voltage reference. Direct pass-through; do not feed power through it. |
| 6 | SELV return | Target logic return; no HOT0 or HV connection. |

The four TI ESD diodes shunt pins 1–4 to SELV return. They do not prevent a
powered programmer from backfeeding an unpowered ESP input, and pin 5 does
not enforce the reference-only rule. The programmer must be 3.3 V logic and
is not supplied by this coupon. J1 is a Tag-Connect
PCB contact pattern, not a populated part; the Atopile BOM lists it because
the compiler has no DNL marker here. J2 is an unkeyed Samtec lab header, so
its mechanical polarity is not yet appropriate for product service.

Build with Atopile 0.2.69 in this directory, then use the commands in the
[evidence README](../evidence/service-board-01/README.md) to regenerate and
review native artifacts. Service integration still needs one reconciled MCU
pin contract, a keyed/access-controlled product connector, powered-off I/O
protection, and measured reset-to-PFC-and-inverter-stop with no automatic
rearm. The product UI remains unselected.
