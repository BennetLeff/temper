# instruments

Bench instruments built alongside Temper, and the code they share.  Each instrument lives on its own branch
until it lands; shared code lives here so every instrument branch picks it up from main.

| path | what |
|---|---|
| [boardkit](boardkit/) | `temper-boardkit`: PCB craft passes, pre-DRC, Gerber/JLC DFM checks, pcbnew helpers (Python 3.9+) for the hand-routed instrument boards |
