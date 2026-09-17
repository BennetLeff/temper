# Native identity check — 2026-09-17

Maintained inputs:

- `power-entry/shunt-repair/candidate/section.kicad_pcb`
- `power-entry/shunt-repair/candidate/section.kicad_sch`
- board SHA-256: `34e6fba9e6d323d795bba5bfe7ddfbcb5d158630cd2eb8cf95253b8e0263b2b9`
- source manifest SHA-256: `136c94c36af498285c731e6cd43877eb5cc2e2b2289de21fbd8d531bc7d18ef2`

With KiCad 10.0.4 `kicad-cli`:

```sh
kicad-cli sch erc -o erc.txt power-entry/shunt-repair/candidate/section.kicad_sch
kicad-cli pcb drc --exit-code-violations -o drc.txt power-entry/shunt-repair/candidate/section.kicad_pcb
```

Results: ERC **0 errors / 0 warnings** and DRC **0 violations / 0 unconnected
pads / 0 footprint errors**. No geometry or routing was changed for the MPN
correction.
