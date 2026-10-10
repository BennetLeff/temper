# PCB rubric source context

Captured 2026-10-10. Current guidance is anchored to `origin/main` at `ba575413f5a39401eed1c20417ab7565fa28b509`. These records identify documentation and design input bytes, not physical measurements, hardware qualification or a selected fabrication release.

## Current design scope

The current README describes a 120 V full bridge and five maintained standalone units. The legacy integrated board was removed on 2026-10-08; the former Rev38 line is historical. The unit registry covers RTD, current sensor, gate driver, thermal cutoff and interlock. The complete power-stage board has separate source exports and native candidates and is outside that five-unit runner. The check catalog states which geometry, current and fabrication models run and what they cannot establish.

A resolved BOM identifies parts for that exact snapshot. It does not establish fitted hardware, a selected native candidate or completion of qualification. For example, the current power-stage fault interface uses the non-F, default-high ISO7710; older default-low ISO7710F advice cannot be transferred without checking the circuit contract.

## Current input identities

### README.md

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `b66032da6b95d45d87a20563e213fb33a17d91514656730c104443abc552b108`

### zapote/CHECKS.md

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `d98d3b78cfc88d2ccf6a90a0b49f9ef12d7809b8c8652137011a881bf4a7cb12`

### zapote/validation/units.json

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `c414a251e26d6a5e38f93a1d7e83891335389377eefcc985d8db0d6af606d10d`

### zapote/power-stage-120v/README.md

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `17d005137ac0e13e55e632500f5276853b8281a6caa89ea2c2cdf304b69ca094`

### zapote/power-stage-120v/frozen/default.csv

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `33892419df26d475157037dcdc6a401b6cd9ef5881e7c2fedd4772dadd946bb8`

### zapote/power-stage-120v/native-20/frozen/default.csv

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `228e0d1467cfcccbd234d5f1e784fafca72af5590b529fe92c53c682879a9e58`

### docs/hardware/TRACE_WIDTH_CALCULATIONS.md

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `1870546280091251da82bb1716076edbacddb81d88bb025401463a9b27aaa0bd`

### docs/hardware/power-section-120v/POWER-SECTION.md

- Repository revision: `ba575413f5a39401eed1c20417ab7565fa28b509`
- Input SHA256: `a41b4ec8cdea4a202089dcf41f387f04fa6b416cb6b8ce9a29354ee0ce687535`

## Separate research and historical snapshots

The IC appendix also reviews a controller candidate, supervisor prototypes and retired devices found in separate research snapshots. These are explicitly separated from the current unit inventories. Historical front-end briefs describe a UCC28180 PFC bank and proposal-era full-bridge work; they do not define today's selected architecture. The records below preserve the initial inputs so that history is not silently presented as current.

Retrieve committed historical artifacts through the [legacy archive](https://github.com/BennetLeff/temper/tree/archive/temper-legacy-2026-10-08) or the recorded revision when available. A checkout HEAD does not guarantee that the inspected bytes were committed; verify the full content hash.

### docs/adr/2026-09-25-front-end-architecture-brief.md

- Inspected source location: `/Users/bennet/Desktop/temper/docs/adr/2026-09-25-front-end-architecture-brief.md`
- Checkout HEAD at inspection: `84c5e5b61000d45eec09834cb23e6bba8fa51169`
- Input SHA256: `232cda75bf17aeb96a22ec43c0193c5851f7a796919cfcc0f785ddf8cd63ec13`

### docs/hardware/power-section-120v/POWER-SECTION.md

- Inspected source location: `/Users/bennet/Desktop/temper/docs/hardware/power-section-120v/POWER-SECTION.md`
- Checkout HEAD at inspection: `84c5e5b61000d45eec09834cb23e6bba8fa51169`
- Input SHA256: `c0ae50a0ae71f638d64ee758b2cce6db3e0c874ac030172c2af6dbad77885e5b`

### docs/handoffs/power-entry-protection-next-revision.md

- Inspected source location: `/Users/bennet/Desktop/temper/docs/handoffs/power-entry-protection-next-revision.md`
- Checkout HEAD at inspection: `84c5e5b61000d45eec09834cb23e6bba8fa51169`
- Input SHA256: `e5b1f3be2393509d522531546ae3c28e3e549b4e59b74fc05e4fea405f771b1e`

### docs/adr/2026-09-25-front-end-architecture-brief.md

- Inspected source location: `/Users/bennet/Desktop/temper/worktrees/ps-integrate/docs/adr/2026-09-25-front-end-architecture-brief.md`
- Checkout HEAD at inspection: `5191b326310d8bbb4eec9c6bbd14916d797170ac`
- Input SHA256: `702754afe60f6169f440a1b6fdfe777d16efe862992b095282ee2ee0a8947089`

### docs/hardware/power-section-120v/POWER-SECTION.md

- Inspected source location: `/Users/bennet/Desktop/temper/worktrees/ps-integrate/docs/hardware/power-section-120v/POWER-SECTION.md`
- Checkout HEAD at inspection: `5191b326310d8bbb4eec9c6bbd14916d797170ac`
- Input SHA256: `a41b4ec8cdea4a202089dcf41f387f04fa6b416cb6b8ce9a29354ee0ce687535`

### zapote/controller/frozen/default.csv

- Inspected source location: `/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/controller/frozen/default.csv`
- Checkout HEAD at inspection: `5191b326310d8bbb4eec9c6bbd14916d797170ac`
- Input SHA256: `c9a675a6ecb0b4ffb042fae90ee3e873d0808059fa871e529ef88eaa3d24dd70`

### zapote/power-stage-120v/elec/src/power_stage_120v.ato

- Inspected source location: `/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/elec/src/power_stage_120v.ato`
- Checkout HEAD at inspection: `5191b326310d8bbb4eec9c6bbd14916d797170ac`
- Input SHA256: `5e17c4aa00ce629b78695d741e852235b50c312860d6d3de27e486457c4054da`

### docs/adr/2026-09-25-front-end-architecture-brief.md

- Inspected source location: `/Users/bennet/.codex/worktrees/ps-r17-d35/temper/docs/adr/2026-09-25-front-end-architecture-brief.md`
- Checkout HEAD at inspection: `69144e87e65852a92b51d368586e00c03911cb3e`
- Input SHA256: `702754afe60f6169f440a1b6fdfe777d16efe862992b095282ee2ee0a8947089`

### docs/hardware/power-section-120v/POWER-SECTION.md

- Inspected source location: `/Users/bennet/.codex/worktrees/ps-r17-d35/temper/docs/hardware/power-section-120v/POWER-SECTION.md`
- Checkout HEAD at inspection: `69144e87e65852a92b51d368586e00c03911cb3e`
- Input SHA256: `a41b4ec8cdea4a202089dcf41f387f04fa6b416cb6b8ce9a29354ee0ce687535`

### zapote/power-stage-120v/elec/src/power_stage_120v.ato

- Inspected source location: `/Users/bennet/.codex/worktrees/ps-r17-d35/temper/zapote/power-stage-120v/elec/src/power_stage_120v.ato`
- Checkout HEAD at inspection: `69144e87e65852a92b51d368586e00c03911cb3e`
- Input SHA256: `b08c436d1c11c4e034400f83b718dfab3b194202f68aac5213dc59699db2c3aa`

## Reusing the evidence

Re-inventory the selected release export before assigning pass/fail results. Keep schematic, BOM, board, stackup and assembly process under one release identity. The datasheet appendix records official source links, reviewed revisions where available and section locators. Save exact PDF bytes and hashes with a fabrication release when accepting device-specific requirements.
