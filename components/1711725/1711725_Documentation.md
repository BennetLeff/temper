# Phoenix Contact 1711725 — mains L/N terminal

**Selected part:** Phoenix Contact MKDS 3/2-5,08, a two-position, 5.08 mm-pitch PCB terminal. J1 pin 1 takes mains L and pin 2 takes mains N on the 120 V power stage. Protective earth is a separate chassis bond and PCB branch at J6.

The Atopile source uses `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal`, with pad 1 = L and pad 2 = N. The 5.08 mm pitch matches the selected order code; the earlier 1711026/1711039 candidates are 5.00 mm-pitch parts and are not substitutes. The source lists a 24 A IEC rating. Applicable UL use-group limits differ (15 A group B, 10 A group D); confirm the relevant wiring, conductor, enclosure temperature and approval basis before assigning a completed-assembly current rating. No terminal heating test has run.

The terminal is not the PE path. Cord PE bonds directly to the chassis/heatsink stud; only a separate branch wire lands on J6. Check line/neutral clearance, cord strain relief and polarity handling in the final enclosure.

Sources: [Phoenix product page](https://www.phoenixcontact.com/en-de/products/pcb-terminal-block-mkds-3-2-508-1711725), [power-stage source](../../zapote/power-stage-120v/elec/src/parts.ato), [assembly connections](../../zapote/power-stage-120v/ASSEMBLY.md).
