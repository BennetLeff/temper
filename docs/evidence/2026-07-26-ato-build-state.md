# `ato build` state — investigation result

**Provenance: commit=ca9281d15923d6d89e1eb37e3f23ce1bb34395a2 dirty=UNKNOWN** -- backfilled: this document's own prose self-declares "HEAD verified: `ca9281d1`" (confirmed tip of `docs/methodology-loop-discipline` at measurement time); resolved to the full SHA via `git rev-parse ca9281d1`. dirty state was not recorded at measurement time and is not reconstructable, so it is UNKNOWN rather than guessed.

**Date:** 2026-07-26
**Worktree:** `/Users/bennet/Desktop/temper/.claude/worktrees/agent-ac7ed8a3e94bc878c`
**HEAD verified:** `ca9281d1` — confirmed tip of `docs/methodology-loop-discipline` by
`git log --oneline -1 docs/methodology-loop-discipline` matching HEAD, after a clean
fast-forward rebase (`git rebase docs/methodology-loop-discipline`, no commits to
replay — this worktree's branch was a strict ancestor of the target).

## Summary — the headline

**The project's actual build (`make netlist` / `ato build src/main.ato:Top`) is NOT
broken.** It reproduces cleanly: exit 0, all 69 assertions PASSED, zero FAILED,
"Build complete!". This is the fourth stale-base/false-alarm result today.

**A real, narrower bug does exist, but it is a CLI-invocation footgun, not a
toolchain break:** a *bare* `ato build` (or `ato --non-interactive build`, no
explicit entry argument) crashes with `atopile.address.AddressError`, because
`elec/ato.yaml`'s `builds.default.entry` was `src/main.ato` — missing the `:Top`
root-instance suffix the CLI needs when it has no override. This has been true
since the file was created; it is **pre-existing**, not caused by today's `.ato`
edits, and not version drift. It is very plausibly the actual source of today's
"toolchain break" report, since the task's own suggested repro command
(`ato build > /tmp/atobuild.txt`) is exactly the bare form that crashes, while the
Makefile always supplies the entry explicitly.

**Fixed** with a one-line change to `elec/ato.yaml` (not `main.ato`/`modules.ato`):
`entry: src/main.ato` → `entry: src/main.ato:Top`. Verified to have zero effect on
the actual build output (byte-identical netlist before/after, see below) — it only
unblocks the previously-crashing bare invocation.

**The committed-netlist staleness question, reframed:** `elec/build/` has never
been tracked by git (`.gitignore:7:build/`; zero commits ever added anything under
`elec/build/`) — there is no git-committed netlist to diff against. The
practically-relevant comparison is against the build artifact sitting in the
primary (non-worktree) checkout, which several agents read today and which the
BOM-source-audit agent flagged as "stale... only 40 libpart entries... missing
TLV3201, TPS3823, SN74HC00, ES1J, and the entire SafetyInterlock/RTDSensing
subtree." **That artifact was NOT stale** — a from-scratch rebuild in this
worktree from current source produced a byte-identical netlist (diffed after
normalizing the two worktrees' absolute-path strings; 0 differences). All of
today's `.ato` work is present in both. The BOM auditor's "stale" conclusion was
wrong, but for an interesting reason: a **separate, independently-confirmed
atopile netlist-export bug** (below) makes the `.net` file's own `libparts`
section genuinely undercount and mislabel components — which looks exactly like
staleness if you read only that section, even on a maximally fresh build.

## Falsifier (stated before running the real build)

> The project's build is broken if `cd elec && uv tool run --from
> 'atopile>=0.2,<0.3' ato --non-interactive build src/main.ato:Top` (the exact
> command `make netlist` runs) exits nonzero, or the assertions-report contains
> any FAILED row. It is not broken if it exits 0 with "Build complete!" and zero
> FAILED assertions.

**Result: the falsifier did not fire.**

```
$ cd elec && uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive build src/main.ato:Top > /tmp/atobuild.txt 2>&1; echo "exit=$?"
exit=0
```

`/tmp/atobuild.txt` (791 lines, read in full, not piped): 69/69 assertions
`PASSED`, zero `FAILED`, ending in:

```
INFO     Successfully built 'assertions-report, bom, layout-module-map,
         clone-footprints, netlist, copy-3dmodels, designator-map,
         copy-footprints, variable-report' for 'default' config
INFO     Build complete!
```

## The exact original error (reproduced, root-caused)

I do not have the original BOM agent's transcript, so I cannot confirm their
literal command. What I *can* confirm: the only way I could get `ato build` to
fail anywhere in this project, on this HEAD, was to omit the explicit entry
argument:

```
$ cd elec && ato --non-interactive build > /tmp/atobuild_bare.txt 2>&1; echo "exit=$?"
exit=1
```

Tail of the traceback:
```
File ".../atopile/front_end.py", line 1240, in handle_new_assignment
    new_addr = address.add_instance(...)
File ".../atopile/address.py", line 132, in add_instance
    raise AddressError("Cannot add instance to something without an entry section.")
atopile.address.AddressError: Cannot add instance to something without an entry section.
```

Reproduced identically three ways, ruling out both the `uv tool run` wrapper and
atopile version drift as the cause:

| Invocation | Entry given | atopile version | Result |
|---|---|---|---|
| `ato --non-interactive build` (local binary) | none (falls back to `ato.yaml`) | 0.2.69 | **crash** |
| `uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive build` | none | 0.2.69 (resolved) | **crash** |
| `uv tool run --from 'atopile==0.2.68' ato --non-interactive build` | none | 0.2.68 (`ato.yaml`'s pinned version) | **crash**, identical trace |
| `ato --non-interactive build src/main.ato:Top` (local binary) | explicit | 0.2.69 | exit 0 |
| `uv tool run --from 'atopile>=0.2,<0.3' ato --non-interactive build src/main.ato:Top` (= `make netlist`) | explicit | 0.2.69 | exit 0 |

**UNVERIFIED:** whether the original BOM agent actually ran the bare form. I am
reporting only what I could directly reproduce: bare `ato build` is the one and
only failure mode found on this HEAD, and it fails identically regardless of
atopile 0.2.68 vs 0.2.69, which rules out version drift as an explanation.

## Establishing pre-existing, not caused by today's edits

Checked two independent ways:

1. **`elec/ato.yaml`'s entry field has never had `:Top`.** `git log -p --follow --
   elec/ato.yaml` shows every historical revision of the file, back to the commit
   that introduced it (`f77fbebf`), with `entry: src/main.ato` — the `:Top`
   suffix was never present. This is not something today's `.ato` edits touched
   or regressed.
2. **The crash reproduces on atopile 0.2.68** (the exact version `ato.yaml`
   itself pins via `ato-version: 0.2.68`), not just on the currently-installed
   0.2.69 — so this isn't atopile-version drift interacting with the project;
   it's inherent to how this atopile version series resolves a config-only entry
   lacking `:Top`.

No older-commit rebuild was needed to establish "pre-existing" here, since the
mechanism (CLI entry-resolution behavior in the installed atopile package,
against a config field that has been constant for the project's entire history)
does not depend on which day's `elec/src` content is being built.

## The fix

```diff
--- a/elec/ato.yaml
+++ b/elec/ato.yaml
@@ -1,4 +1,4 @@
 ato-version: 0.2.68
 builds:
   default:
-    entry: src/main.ato
+    entry: src/main.ato:Top
```

Only file touched. Not `main.ato`, not `modules.ato`.

Verified:
```
$ cd elec && ato --non-interactive build > /tmp/atobuild_after_fix.txt 2>&1; echo "exit=$?"
exit=0
```
(`grep -n "FAILED\|Build complete" /tmp/atobuild_after_fix.txt` → only "Build
complete!", zero FAILED.)

And verified the fix changes *only* CLI entry-resolution, not the design: the
netlist produced by the bare invocation after the fix is byte-identical (diffed
after normalizing the two absolute worktree-path strings embedded in
`sheetpath` fields) to the netlist produced by the always-worked explicit-entry
invocation. `diff` exit 0, zero lines of output.

## Measured proof the netlist regenerates

- Before any build ran in this worktree, `elec/build/` did not exist at all
  (`ls elec/build/` → "No such file or directory"). This was a from-scratch
  build, not an incremental no-op.
- After the build: `elec/build/default.net` exists, 1981 lines, 156 `(comp (ref
  ...))` entries (matches the 155 `elec/src` components + generated test
  points), `elec/build/default.csv` exists with 85 BOM data rows (86 lines minus
  header), `elec/build/manifest.json` and `default.layouts.json` also written.
- mtime is fresh (created at build time, matching the run), and content is
  non-empty and structurally complete (BOM table, designator-map, and
  variable-report all printed during the build with no gaps).

## Committed-vs-regenerated netlist comparison

**There is no git-committed netlist to diff against.** Confirmed:
```
$ git check-ignore -v elec/build/default.net
.gitignore:7:build/    elec/build/default.net

$ git log --all --diff-filter=A --name-only -- 'elec/build/*'
(zero output — no commit, ever, added anything under elec/build/)
```
`elec/build/default.net` is a pure build artifact, always gitignored, in every
commit in this repository's history. "Is the committed netlist stale" is not a
question with a git-level answer here.

**What is answerable:** the primary (non-worktree) checkout at
`/Users/bennet/Desktop/temper/elec/build/default.net` (mtime 2026-07-26 11:35)
is the artifact `docs/evidence/2026-07-25-bom-source-audit.md` and
`docs/evidence/2026-07-26-bom-availability-sweep.md` both read and cross-checked
against today. The source audit explicitly called it stale: "only 40 `libpart`
entries and is missing `TLV3201`, `TPS3823`, `SN74HC00`, `ES1J`, and the entire
`SafetyInterlock`/`RTDSensing` subtree."

I diffed that file against the netlist freshly regenerated in this worktree from
current HEAD (`ca9281d1`), after normalizing the two worktrees' different
absolute path prefixes (each build embeds its own absolute path in `sheetpath`
strings) with `sed`:

```
$ diff main_norm.net mine_norm.net
$ echo $?
0
```

**Zero differences. The two netlists are byte-for-byte identical** modulo the
expected worktree-path substitution. All of today's `.ato` work — THM-02,
OCP-02's component definitions, the hysteresis fixes, CST3015, OVP-01, the BOM
part replacements, and the entire `SafetyInterlock`/`RTDSensing` subtree — **is
present in both.** The main checkout's netlist was current, not stale, at the
time it was built.

## Why the BOM auditor was wrong, and what's actually going on (the real finding)

The auditor's raw observation (40 libparts, specific MPNs "missing") is
**correct as a literal reading of the file** — it's the inference ("therefore
stale") that's wrong. I found the real cause: **a reproducible atopile
netlist-export defect**, present in a maximally-fresh, from-scratch, current-HEAD
build, not something that crept in over time.

`elec/build/default.csv` has 85 distinct BOM line items (one per distinct MPN,
each possibly covering multiple designators). `elec/build/default.net`'s
`libparts` section has only 40 entries. The other 45 distinct parts are not
missing from the design — they're present as `(comp ...)` entries with correct
`ref`, correct `footprint`, and correct `sheetpath` — but atopile's netlist
backend has mislabeled their `(libsource (part "..."))` field with the identity
of a *different* component that happens to share the same KiCad footprint.

Concretely, every SOT-23-5 (5-pin) IC in the design shares one mislabeled
identity:

```
(comp (ref "U9")   ... (libsource (part "REF2025AIDDCR") ...))   <- correct (this IS the REF2025)
(comp (ref "U10")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, this is rtd_pan.low_window (TLV3201)
(comp (ref "U11")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, rtd_pan.high_window (TLV3201)
(comp (ref "U12")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, rtd_pan.window_and (SN74LVC1G08)
(comp (ref "U14")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, rtd_pan.fault_nand (SN74LVC1G38)
(comp (ref "U15")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, safety.ocp.comp (TLV3201)
(comp (ref "U16")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, safety.ovp.comp (TLV3201)
(comp (ref "U17")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, safety.thermal.comp (TLV3201)
(comp (ref "U18")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, safety.coil_thermal.comp (TLV3201)
(comp (ref "U19")  ... (libsource (part "REF2025AIDDCR") ...))   <- WRONG, safety.wdt.wdt (TPS3823-33DBVR)
```

9 of these 10 SOT-23-5 components are mislabeled with U9's part identity — the
first one atopile resolved for that footprint shape. The same pattern recurs for
the SOIC-14 logic ICs (U20/U21 genuinely `SN74HC4075DR`; U22, actually
`SN74HC00DR`, is also labeled `SN74HC4075DR`) and the SMA diodes (D1/D3/D4
genuinely `SS14`; U7, actually `ES1J`, is also labeled `SS14`). This accounts
precisely for the auditor's "missing TLV3201, TPS3823, SN74HC00, ES1J" — those
parts are real, present, correctly specified in source and in the BOM/CSV; they
just don't appear as their own `libpart` in the `.net` file because the exporter
aliased them away.

**Scope of the actual risk — checked, not assumed:** the `(nets ...)` section,
which is what a net-topology check (SELV ground/power-return separation, a
domain-partition check) actually reads, references components purely by
`(ref, pin)`:
```
(node (ref "U19") (pin "1") (pintype "stereo"))
(node (ref "U19") (pin "3") (pintype "stereo"))
...
```
This does **not** depend on the mislabeled `libsource` field. So the two agents
depending on net-level connectivity (SELV isolation, domain-partition) are **not
directly compromised** by this defect, provided their check keys off
`ref`/`pin`/net-name and not off `libsource`/MPN identity. Any check or reading
that instead trusts `default.net`'s own `libparts`/`libsource`/`description`
fields as "what part is this" will get wrong answers for every footprint-sharing
component group — use `default.csv` (which is correct) or the designator-map for
part identity instead.

I did not attempt to fix the atopile netlist-export defect itself — it lives
inside the `atopile` package (`.../atopile/front_end.py` /
`.../atopile/instance_methods.py` netlist backend), not in this project's
source, and is out of scope for "is `ato build` broken." It is reported here
because it is the actual explanation for the "stale netlist" alarm, and because
it's a real, previously-undocumented data-quality hazard for anyone reading
`default.net`'s part-identity fields directly.

## What remains UNVERIFIED

- Whether the original BOM agent's "toolchain break" report was literally caused
  by running a bare `ato build`. I could not obtain their transcript; I can only
  report that bare `ato build` is the sole failure mode I could find, on this
  HEAD, and that it plausibly matches their report.
- Whether the atopile netlist-export footprint-aliasing bug is a known upstream
  issue with a tracked fix, or specific to atopile 0.2.68/0.2.69. Not
  investigated (out of scope — it's an upstream package defect, not a project
  bug).
- `make build`'s later stages (`footprints`, `schematics`, `route`, `drc`) were
  not re-verified in this pass — only `netlist` (the stage this task's falsifier
  and the two dependent agents' needs are about) was exercised.

## Commit

`elec/ato.yaml` (one line) is the only source change, committed in this
worktree. Not pushed.
