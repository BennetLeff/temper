---
title: 120 V power stage — native schematic and PCB (plan index)
date: 2026-09-25
status: ready for execution
audience: an implementing agent with no prior context on this project
source_unit: zapote/power-stage-120v
---

# 120 V power stage board: plan index

This folder turns the audited Atopile source in `zapote/power-stage-120v/` into
a native KiCad schematic and PCB. It is split into six parts, meant to be done
**in order** by one agent at a time. Each part is self-contained: it lists its
inputs, the exact commands, the checks that must pass, and when to stop and ask.

| Part | File | Produces | Blocks |
| --- | --- | --- | --- |
| 1 | `01-TOOLCHAIN.md` | Native-bridge tooling on this branch (harness-lab modules, Rust bridge functions, unit wrapper scripts) | 3 |
| 2 | `02-FOOTPRINTS.md` | Six missing footprints plus two copied ones, in the unit's local library | 3 |
| 3 | `03-NATIVE-GENERATION.md` | First native `section.kicad_sch` / `section.kicad_pcb` (parts on a shelf, unrouted) | 4 |
| 4 | `04-PLACEMENT.md` | Reviewed placement, stackup, outline and design rules. **Stops for owner review** | 5 |
| 5 | `05-ROUTING.md` | Routed board through scripted route replay | 6 |
| 6 | `06-VERIFICATION.md` | ERC/DRC/parity/gates, frozen receipt, acceptance record | — |

Parts 1 and 2 are independent and may run in parallel **only** in separate
worktrees. Never let two agents write the same worktree.

## Read these first (in this order)

1. `zapote/power-stage-120v/README.md`: what the board is, header pinout, safety chain, open items.
2. `docs/hardware/power-section-120v/POWER-SECTION.md`: the schematic map and justified BOM.
3. `zapote/power-stage-120v/elec/src/power_stage_120v.ato` and `parts.ato`: the source of truth.
4. `zapote/power-stage-120v/audit.rs`: the safety invariants that must keep passing.
5. `AGENTS.md` (repo root) and `zapote/AGENTS.md`: repo rules.

## Environment facts (verified 2026-09-25 on the owner's Mac)

| Thing | Value |
| --- | --- |
| Shell | **zsh**. See the gotchas below |
| Atopile | `uv tool run --offline --from "atopile==0.2.69" ato ...` (pinned; no network needed) |
| KiCad | 10.0.4; `kicad-cli` on PATH |
| KiCad's Python (has `pcbnew`) | `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3` |
| KiCad stock footprints | `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/` |
| Rust | `rustc 1.92.0`; the zapote workspace is `zapote/Cargo.toml` |
| Archive tags (read-only sources for salvage) | `archive/rev38-power-entry-2026-09-25`, `archive/zapote-coil-intake-2026-09-25` |

## Global rules: every part

1. **One writer per worktree.** Create your own worktree
   (`git worktree add worktrees/<name> -b <branch> <base>`) and work only there.
2. **Never use `git stash`.** A hook blocks it, and the stack is shared across
   worktrees. To set work aside, make a WIP commit.
3. **Never edit `pcb/temper.kicad_pcb` or `elec/`.** They are the old doubler
   design and carry their own DRC-ceiling rules. This project doesn't touch them.
4. **Source first.** Any electrical change goes into
   `zapote/power-stage-120v/elec/src/*.ato`. Then rebuild, re-export, re-audit
   and re-freeze. Never hand-edit a net in KiCad to "fix" connectivity; the
   native board must stay a projection of the source.
5. **Part identity comes from `resolved-components.json` or the CSV BOM, never
   from `default.net`.** Atopile 0.2.69 writes a footprint-aliased part number
   into the netlist's `libsource` field. For example, every 0603 resistor shows as
   `RC0603FR-071KL` and the LM4040 shows as `AO3400A`.
6. **Keep the audit green.** After any source change:
   ```sh
   cd zapote/power-stage-120v
   rustc --edition=2021 -O audit.rs -o /tmp/ps_audit
   /tmp/ps_audit build/default.net build/default.csv build/resolved-components.json
   rustc --edition=2021 --test audit.rs -o /tmp/ps_audit_t && /tmp/ps_audit_t
   ```
   Any `FAIL` line, or any failing test, means stop and fix the source. Never
   loosen the audit to make it pass. If you believe the audit itself is wrong,
   stop and ask.
7. **Evidence honesty.** Digital checks are connectivity, geometry and rule
   evidence only. Write "NOT RUN" for anything physical: powered test, EMI,
   insulation test, thermal measurement. Never record a fabrication or safety
   PASS.
8. **Commits** end with:
   `Co-Authored-By: <your model name> <noreply@anthropic.com>`.
   Pull-request descriptions end with the Claude Code line used elsewhere in the
   repo. Open a PR only when the part's checklist is fully green.

## zsh gotchas that have already bitten this project

- `git show $T:path` breaks, because zsh reads `$T:h` as a path modifier. Always write
  `git show "${T}:path"`.
- An unquoted `$var` holding several paths is **not** word-split. Loop in
  Python, or use `for x in ${(f)var}`.
- `timeout` is not installed. Use the tool-call timeout, or Python's
  `subprocess.run(timeout=...)`.
- `--include=*.rs` fails as an unmatched glob. Quote it: `--include='*.rs'`.

## Owner decisions still open (Part 4 needs them)

| ID | Question | Default if the owner says "use your judgment" |
| --- | --- | --- |
| D1 | Maximum board size inside the enclosure | 220 × 160 mm |
| D2 | Heatsink concept | One extruded heatsink along one long board edge; the 4 × TO-247 MOSFETs and the GBJ2510 bridge stand vertically along it, each electrically insulated with a thermal pad; the heatsink is bonded to PE |
| D3 | Layer count / copper | 2 layers, 1.6 mm FR-4, 70 µm (2 oz) both sides |
| D4 | Stop after placement for review? | **Yes.** Part 4 ends with an owner review |

Ask the owner for D1–D3 at the start of Part 4 if they aren't recorded in
`zapote/power-stage-120v/DECISIONS.md` by then.
