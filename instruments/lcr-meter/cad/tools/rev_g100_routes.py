# Rev G100 copper, executed inside cad/tools/rev_g100.py after the west and east bodies moved 10 mm north (names:
# parts, routing, P, T, T45, V, DROP, WIDEN, KO, prune).  Hand routing by coordinates; no autorouter, no path search.

# ============================================================== 0. what the new outline and the moved parts leave behind
# copper south of the new edge (the old flash fan-out, BOOTSEL, RUN, MON12 / MON_N12 tails, the old 5 V trunk)
_t = CLEAR(below=144.55)
# the old flash fan-out and the parts placed again (QSPI, BOOTSEL, RUN network, TP20 / TP21, J5)
_t |= CLEAR({'QSPI_CS', 'QSPI0', 'QSPI1', 'QSPI2', 'QSPI3', 'QSPI_CLK_FLASH', 'BOOTSEL'}, box=(57, 137.5, 82, 145))
_t |= CLEAR(box=(57.5, 137.6, 67.6, 145.0))          # under the flash's new place
print('prune:', prune(_t | {'GND', '3V3', 'RUN', '5V', 'USB_VBUS', 'HEARTBEAT', 'FAULT', 'LED_HB', 'LED_FLT'}))
