# KiCad native DRC qualification

Date: 2026-09-10

This scratch evidence retains the original DRC semantics and all required
flags. No production source, fixture, or installed application was changed.

## Reproduction on installed KiCad 10.0.4

Command, for each board:

```text
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --format json --all-track-errors --severity-all --output drc.json candidate.kicad_pcb
```

The `missing-terminal` mutant exits 133, emits no report, and reproduces the
native crash. This remains true with no `KICAD_CONFIG_HOME`, with `LC_ALL=C
LANG=C`, and with the seeded config below. The `witness-1` board exits 0 and
produces a 1087-byte report. The `wrong-net` control exits 0 and produces a
1087-byte report.

The targeted Swift crash report is `kicad-cli-swift-NSArray.ips`. Its triggered
backtrace is:

```text
_assertionFailure -> __SwiftNativeNSArrayWithContiguousStorage._objectAt
-> wxFromNSPoint -> wxGetMousePosition -> TOOL_MANAGER::doRunAction
-> BOARD_COMMIT::Push -> PCBNEW_JOBS_HANDLER::JobExportDrc
```

This identifies a KiCad 10.0.4 native crash while exporting DRC on the
disconnected mutant, rather than a shell or sandbox denial. Separate
`RegisterApplication` abort reports from launch attempts are retained as
`kicad-cli-registerApplication.ips` and are environmental startup failures.

## Isolated official KiCad 10.0.6

The official universal DMG was downloaded from KiCad's macOS download page's
GitHub release link and mounted read-only at `/Volumes/KiCad`; the installed
10.0.4 app was untouched. DMG SHA-256:

```text
ef4dcd4278c46d3efcd28c8db273d5957d68efda028f6bf79b4811fc5302dc68
```

Binary:

```text
/Volumes/KiCad/KiCad/KiCad.app/Contents/MacOS/kicad-cli --version
10.0.6
```

Using the same full flags and the same boards, 10.0.6 exits 0 for all three:

| board | report | unconnected items | violations |
|---|---:|---:|---:|
| missing-terminal | 6531 bytes | 7 | 0 |
| witness-1 | 1087 bytes | 0 | 0 |
| wrong-net | 1087 bytes | 0 | 0 |

The 10.0.6 report therefore preserves the defect control: the missing-route
mutant is detected as seven unconnected items while the valid witness remains
clean. The reports and per-board hashes are retained beside this file.

KiCad official release source: https://www.kicad.org/download/macos/
