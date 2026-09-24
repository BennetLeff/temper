---
title: Zapote SELV programming coupon candidate
date: 2026-09-23
status: in-progress candidate
---

# SELV programming coupon candidate

## Brief and alternatives

The existing ESP32-S3 source exposes UART0 TXD0/RXD0, EN and IO0, but has no
programming connector. Its GPIO19/20 USB ownership conflicts with firmware;
its IO16/17 claims also conflict. A connector cannot settle these MCU mappings
or prove that an ESP reset stops PFC and inverter hardware.

| Approach | Advantage | Blocker |
| --- | --- | --- |
| Six-wire UART0 coupon (chosen for this construction experiment) | Uses the agreed GPIO43/44, EN and IO0 candidate plus 3V3 reference and SELV return; no reassignment of disputed pins. | Still needs service-access, backfeed and reset-to-stop qualification before appliance integration. |
| Native USB service | Fewer serial adapter wires and built-in ROM download. | GPIO19/20 have competing electrical and firmware owners; USB connector, ESD and VBUS policy are unselected. |
| Hybrid UART and USB | Redundant recovery paths. | Consumes both disputed interfaces and increases access, ESD and enclosure complexity before either path is accepted. |

The chosen coupon is a **mains-disconnected MCU lab fixture**, not a cooker
service port. It has a Tag-Connect six-pad programmer interface and a six-pin
target header. Pin order is fixed in the source. GPIO43 TXD0 is the target
output, GPIO44 RXD0 the target input, EN and IO0 are active-low requests;
3V3 is intended as a *voltage reference only*, never a source feed, but the
pass-through conductor cannot enforce that rule. The coupon connects
only SELV return. The target assembly already owns EN/IO0 pull-ups and
buttons; no duplicate pull-up is added. Four shunt ESD diodes are placed at
the programmer connector. A 499-ohm series resistor is placed in TXD0 per
Espressif's UART0 guidance. The remaining lines are straight-through to keep
the coupon's continuity auditable. This does not give powered-off I/O
isolation. The coupon must not be mated to a powered programmer while the
target is unpowered; product integration remains blocked on a hardware
backfeed solution and access rule.

## Source and construction gates

1. Build native Atopile source and export its KiCad schematic, PCB and netlist.
2. Audit pin-by-pin continuity and absence of any 3V3 source or HV net.
3. If routable, place/route a board candidate and run KiCad ERC and DRC.
4. Keep the existing programming gate blocked until GPIO ownership,
   programmer off-state behavior, connector access and measured reset-to-both-
   stage-stop/no-rearm are resolved on the actual integrated article.

No physical qualification, BOM selection for appliance production, or product
UI choice is conferred by this coupon. UI functionality should be specified
and built after the MCU pin contract and power-stage stop path are accepted.

## Manufacturer anchors

- [Espressif S3 schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html): UART0 GPIO43/44, 499-ohm TX suggestion, GPIO0 strap.
- [Tag-Connect TC2030-IDC-NL drawing](https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/2019/12/TC2030-IDC-NL-Datasheet-Rev-B.pdf): six-pad no-legs footprint and pin numbering.
- [TI TPD1E05U06 datasheet](https://www.ti.com/lit/ds/symlink/tpd1e05u06.pdf): SOT-5X3/DYA one-channel 5.5 V ESD shunt; pin 1 I/O, pin 2 GND.
- [Samtec TSW-106-07-G-S](https://www.samtec.com/products/tsw-106-07-g-s): six-pin, 2.54 mm through-hole target header candidate.
