<!-- provenance: worktree /home/bennet/Desktop/temper-plane-real, branch feat/4layer-power-planes-real, HEAD=c4956df6646b98355f12f00527370b20325e8a70 (clean, unmodified). kicad-cli 10.0.5 (matches CI pin), obtained via the official KiCad AppImage (kicad-downloads.s3.cern.ch/appimage/stable/kicad-10.0.5-x86_64.AppImage.tar) since the userspace .deb extraction from a prior session had been cleared by a VM reboot and system apt/docker-pigz were both unavailable in this sandbox. All numbers below came from commands run in this session; none are invented or carried over unverified from the prior agent's commit message. -->

# Root cause of the 1109 -> 1415 DRC jump attributed to the `signal` -> `power` layer-type edit: it is not the token

**Date:** 2026-08-08

**Task:** Explain the DRC violation-count jump commit `c4956df6` (`fix(pcb):
declare In1.Cu/In2.Cu as power-plane layers, not signal`) reported between
its two-token edit's before/after state, isolate the mechanism, and answer
whether the new violations are real defects or measurement artifacts.

**Headline: the layer-type token (`signal` vs `power` vs `mixed`) is
provably inert to kicad-cli 10.0.5's DRC violation count on this board.**
The jump the prior agent measured is real, but its cause is a *measurement
artifact* unrelated to the token: whichever harness produced the "before"
(1109) number evaluated the board **without a resolvable `.kicad_pro`
project file alongside it**. Without a project, kicad-cli silently drops
every violation that depends on the project's custom
`pcb/temper.kicad_dru` rules (`track_width`, `creepage`) or on the
project's `rule_severities` overrides (`missing_courtyard`,
`annular_width`, plus part of `clearance`) — categories that have no
relationship to layer 1/2's declared type, which is exactly the
"part that makes no sense" the prior agent flagged. Once project context
is held constant, `signal`, `mixed`, and `power` produce **byte-identical
violation category breakdowns** across repeated runs. The underlying
violations themselves (undersized HV trace, missing courtyards, HV/LV
creepage) are real, independently-verified, pre-existing defects that
were being silently under-measured — not created by this commit.

---

## 1. Reproducing kicad-cli 10.0.5

`kicad-cli` was not on `PATH` and `/tmp` had been cleared (as flagged in
the task). apt has no cached `.deb` and `docker pull` of
`ghcr.io/bennetleff/temper-ci:latest` failed locally
(`unpigz: abort: zlib version less than 1.2.3` — a broken system `pigz`
this sandbox has no root to fix). Instead, fetched KiCad's official
stable AppImage, which happens to pin the exact same point release as CI:

```
curl -sSL -o kicad-10.0.5.AppImage.tar \
  https://kicad-downloads.s3.cern.ch/appimage/stable/kicad-10.0.5-x86_64.AppImage.tar
tar xf kicad-10.0.5.AppImage.tar
./kicad-10.0.5-x86_64.AppImage --appimage-extract   # no FUSE/root needed
squashfs-root/bin/kicad-cli --version   # -> 10.0.5
```

A tiny wrapper script puts `kicad-cli` on `PATH` while setting
`LD_LIBRARY_PATH` only for that one binary (setting it globally crashed
unrelated host tools linked against a different glibc — `tail`, and even
`python3`/`uv` segfaulted when launched with the AppImage's
`LD_LIBRARY_PATH` in their own environment):

```bash
cat > kicad-cli <<'EOF'
#!/bin/bash
KICAD_BIN=.../squashfs-root
exec env LD_LIBRARY_PATH="$KICAD_BIN/usr/lib:$KICAD_BIN/shared/lib" "$KICAD_BIN/bin/kicad-cli" "$@"
EOF
```

`get_kicad_cli_version()` (via the real
`temper_placer.validation._drc_api` wrapper, run through `uv run`) confirms
**10.0.5**, matching the `drc_ceiling.json` provenance's recorded tool
version and CI's pin.

The DRC invocation used throughout is the project's own, verbatim
(`_drc_api.run_drc`): `kicad-cli pcb drc --all-track-errors --format json
--output <path> <board>`, run inside `_single_threaded_kicad_env()`'s
pinned `MaximumThreads=1` `KICAD_CONFIG_HOME` (the documented determinism
fix for `clearance`/`shorting_items`; see
`docs/evidence/2026-08-04-drc-measurement-determinism.md` referenced in
that module). `pcb/temper.kicad_dru` was regenerated via
`scripts/generate_kicad_dru.py`, exactly as `ci_check_drc.py` does before
every kicad-cli-backend run. `pcb/temper.kicad_pcb` itself was **never
modified** — all variants were built as scratch copies outside the repo
(`/tmp/.../scratchpad/proj-*`, `variants/*`).

## 2. First reproduction attempt reproduced a *different*, larger jump — then explained it

An initial before/after run (baseline = `git show HEAD~1:pcb/temper.kicad_pcb`
copied to a scratch dir with a symlinked `libs/` and a copied
`temper.kicad_dru`, vs. the committed `power` board run **in place** in
the real `pcb/` directory) gave:

| | total | errors | warnings |
|---|---|---|---|
| signal (scratch copy) | 1314 | — | — |
| power (real repo path) | 1737–1738 | 1248–1249 | 489 |

A **+424** delta — even larger than the prior agent's reported +306 — with
exactly the same qualitative signature described in the task: entirely
new categories `track_width` (0→199), `creepage` (0→186/187),
`missing_courtyard` (0→5), `annular_width` (0→4), plus `clearance`
(339→368), and every other category unchanged. This matched the "part
that makes no sense" complaint precisely — `missing_courtyard` correlates
with the layer-type edit but has no mechanism that should let it.

**The scratch signal copy was missing `pcb/temper.kicad_pro` and
`pcb/temper.kicad_prl`.** The real repo path always has them. That
turned out to be the entire effect, not the token:

- `variants/pro_only` (committed board content, `.kicad_dru` +
  `.kicad_pro` present, no `.kicad_prl`): **1738**
- `variants/prl_only` (same board, `.kicad_dru` + `.kicad_prl` present,
  no `.kicad_pro`): **1314**

`.kicad_pro` (not `.kicad_prl`) is what unlocks the extra categories.
`pcb/temper.kicad_pro`'s `board.design_settings.rule_severities` sets
`"missing_courtyard": "warning"`, `"annular_width": "error"`,
`"track_width": "error"`, etc. explicitly; without a resolvable project,
kicad-cli evidently never loads the project's own severities (or, for
`track_width`/`creepage` specifically — which here are produced purely by
custom rules in `pcb/temper.kicad_dru`, e.g. the `"HighVoltage trace
width"` rule at `min 3.0mm` and the `"HV to LV"` creepage rule at `min
8.0mm` — never loads `temper.kicad_dru` at all, despite the file
physically sitting right next to the board with the matching stem). This
is a KiCad project-resolution behavior, not anything to do with layer 1/2.

## 3. Controlled A/B: the token, held everything else constant

Built two scratch project directories, each a full copy of
`temper.kicad_pro`, `temper.kicad_prl`, `fp-lib-table`, a `libs/` symlink,
and a freshly regenerated `temper.kicad_dru` — differing **only** in
`temper.kicad_pcb`'s two layer-type tokens (`proj-power` = the committed
`c4956df6` content, byte-identical to `pcb/temper.kicad_pcb`, confirmed
via `md5sum`; `proj-signal` = `git show HEAD~1:pcb/temper.kicad_pcb`).
Also built `proj-mixed` (the prior agent's control value) the same way.
3 pinned-thread runs each, plus a run through the real
`temper_placer.validation._drc_api.run_drc()` wrapper:

| variant | run1 | run2 | run3 | run_drc() |
|---|---|---|---|---|
| `proj-signal` | 1737 | 1738 | 1738 | 1738 (1249 err / 489 warn) |
| `proj-power`  | 1738 | 1738 | 1737 | 1738 (1249 err / 489 warn) |
| `proj-mixed`  | 1738 | 1737 | 1738 | — |

Category-by-category (`scripts/compare_drc_reports.py`, `proj-signal` run1
vs `proj-power` run1):

```
Violation Type          Before  After   Δ
tracks_crossing              1      1  +0
annular_width                4      4  +0
hole_clearance              105    105  +0
silk_over_copper            172    172  +0
lib_footprint_mismatch       23     23  +0
missing_courtyard             5      5  +0
via_diameter                  4      4  +0
via_dangling                  32    32  +0
copper_edge_clearance         10    10  +0
hole_to_hole                   3      3  +0
silk_edge_clearance            1      1  +0
courtyards_overlap            11     11  +0
solder_mask_bridge           154    154  +0
lib_footprint_issues           11    11  +0
track_width                  199    199  +0
pth_inside_courtyard            1      1  +0
drill_out_of_range              4      4  +0
track_dangling                  45     45  +0
shorting_items                 199    199  +0
silk_overlap                   199    199  +0
clearance                      368    368  +0
creepage                       186    187  +1   <- known pointer-address-keyed dedup noise (see below)
TOTAL                         1737   1738  +1
```

Every category is flat except `creepage`, which moves by exactly 1 — the
documented (`_drc_api.py`'s own comments) residual nondeterminism from
KiCad's dedup keyed on raw `BOARD_ITEM` pointer values (upstream KiCad
issue #20048), present identically regardless of the layer token. This is
noise, not signal.

**Conclusion: the `signal`→`power` edit produces zero DRC delta once
project-file resolution is controlled for.** `mixed` behaves identically
too. This directly contradicts the "control edit to `mixed` reproduced
1109 exactly, `power` reproduced 1415" claim in the commit message — that
isolation almost certainly shared the same project-file-resolution
confound documented in §2 (the real git states — this commit and its
parent — always carry `pcb/temper.kicad_pro` alongside the board when
checked out in a worktree, but ad hoc synthetic control edits like
"`mixed`" or "whitespace-only" are not real commits and would need to be
constructed as one-off scratch files, which is exactly the step that is
easy to do without carrying the sibling project file along, as this
investigation's own first attempt (§2) demonstrates first-hand).

Reassuringly, this artifact **cannot affect the real CI/ratchet gate**:
`DrcRatchet._check_board` and `ci_check_drc.py` always call `run_drc()`
directly on `repo_root / entry.path` (`pcb/temper.kicad_pcb`) in the
checked-out repository, which always has `pcb/temper.kicad_pro` sitting
next to it as a tracked file. The confound is specific to ad hoc
scratch-file comparison harnesses, not to the project's real measurement
path.

## 4. Are the extra violations real? Verified independently of kicad-cli, three ways

### `missing_courtyard` (F1, L2, R30, RT1, U27)

Parsed `pcb/temper.kicad_pcb` directly (not via DRC) for each footprint's
graphic layers:

```
F1  (Fuse:Fuse_Holder_5x20mm)        -> no F.CrtYd/B.CrtYd graphic
L2  (Inductor_SMD:L_Bourns_SRP1265A) -> no F.CrtYd/B.CrtYd graphic
R30 (lib:LitzPad_15A)                -> no F.CrtYd/B.CrtYd graphic
RT1 (Resistor_THT:R_Disc_D15.0mm...) -> no F.CrtYd/B.CrtYd graphic
U27 (lib:ESP32-S3-WROOM-1)           -> no F.CrtYd/B.CrtYd graphic
```

All five genuinely lack a courtyard graphic. Real, pre-existing.

### `track_width` (net `w1_2`, and 198 others)

`packages/temper-placer/.../core/design_rules.py` classes net `w1_2` as
`HighVoltage` (`trace_width=3.0`, `voltage_v=400.0`,
`required_layer="B.Cu"`). Grepping the board file's raw `segment` records
for net 159 (`w1_2`) directly:

```
(segment (start 159.145 172.825) (end 159.15 172.85) (width 0.25) (layer "F.Cu") (net 159)
```

A 400V-rated `HighVoltage` net is physically routed at **0.25mm** where
the design rule requires **3.0mm**, and on **F.Cu** where its
`required_layer` is `B.Cu`. Real, severe, pre-existing, and entirely
unrelated to In1/In2.

### `creepage` (HV/LV spacing, as low as 0.175mm vs 8.0mm required)

Sample violations pair nets/pads independently confirmed HV-classed in
`design_rules.py` (`GATE_HS` -> `GateDriveHV`, `+15V_LS` -> `HighVoltage`)
at pad-to-pad spacings the DRC computed down to 0.175mm against the DRU's
`8.0mm` "HV to LV" rule. Consistent with genuinely tight HV/LV routing on
F.Cu, not a DRC-engine artifact.

**None of these three categories reference In1.Cu or In2.Cu in any
violation item** — every sampled item is on `F.Cu` or is a bare footprint
reference. The layers whose type token changed are completely absent
from the actual defect content; they were never geometrically involved.

## 5. Answering the decisive question (task item 4)

**The +306-to-+424-ish violations (depending on which flawed comparison
is read) are real, pre-existing defects that were always present on the
board — not new defects and not artifacts of the `power` token.** They
were hidden by a measurement-methodology gap (missing project-file
resolution in whatever ad hoc harness produced the smaller number), which
is orthogonal to this commit. The `power` vs `signal` edit itself is
measurement-neutral: it changes nothing kicad-cli reports, up or down,
once measured correctly. This is a "the baseline was under-reporting"
finding as the task's item 4 anticipated, but its trigger is a harness
artifact, not the `power` token specifically — that distinction matters
because it means this commit is not "revealing hidden defects it should
get credit for," nor is it "introducing risk that should block it." It is
inert with respect to DRC.

## 6. Token recommendation

**`power` is correct and should be kept**, on design-intent grounds
(unaffected by this investigation, since DRC is neutral either way):
REQ-ELEC-05 designs In1.Cu as a dedicated GND reference plane and In2.Cu
as a dedicated PWR plane, with no signal-routing role for either — that
is exactly KiCad's own definition of the `power` layer type, as opposed
to `mixed` (pours *and* routed signal on the same layer) or `signal`
(routed signal, no pour role). `mixed` would be the wrong signal to send
about design intent even though, per §3, it is DRC-identical today. This
investigation only tested kicad-cli's DRC engine; it did not check
whether `power` vs `mixed` changes other KiCad behaviors (e.g. zone-fill
priority defaults, teardrop generation, or GUI plane-fill hints) — out of
scope here, flagged for anyone relying on those features later.

## 7. Ceiling-contract interaction (informational only — file not modified)

`power_pcb_dataset/drc_ceiling.json` pins `error_ceiling=1267`,
`warning_ceiling=472` at `measured_at_commit=3410ee4e1fe8c3a5cce13b9262585016a06fce8d`
with input sha256 `51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af`
for `pcb/temper.kicad_pcb`. Confirmed independently in this session:

```
sha256(pcb/temper.kicad_pcb @ HEAD c4956df6)   = 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
sha256(pcb/temper.kicad_pcb @ HEAD~1, signal)  = 1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6
```

Neither matches the pin — the ceiling was already stale before this
commit, exactly as previously reported. Since the token itself is
DRC-neutral (§3), this commit does not change *why* the ceiling is stale
or make the staleness worse — the pre-existing staleness (and this
environment's measured 1249 errors / 489 warnings against the stale
1267/472 ceiling — errors under, warnings over, on numbers that already
don't correspond to either commit's real board content, and likely also
undercount relative to a from-scratch environment with the full upstream
`kicad-footprints` library fetched via `tools/setup_kicad_env.py`, which
this sandbox never ran) is unchanged by this investigation. No edit was
made to `drc_ceiling.json` and no `Ceiling-Approval:` trailer was added,
per the hard constraints; re-pinning remains a separate, human-gated R27
action.

## 8. What was and wasn't verified

Verified in this session, all commands run live (no invented figures):
kicad-cli 10.0.5 reproduction; the original (confounded) +424 delta;
the project-file-resolution mechanism (`pro_only` vs `prl_only` isolating
`.kicad_pro` specifically); the controlled signal/power/mixed A/B (both
raw CLI and the real `run_drc()` wrapper); independent, DRC-engine-free
verification of `missing_courtyard`, `track_width`, and `creepage` sample
violations against the raw board file and `design_rules.py`; ceiling sha256
mismatch.

Not verified / out of scope: the exact KiCad C++ code path that skips
`.kicad_dru`/`rule_severities` loading without a resolvable project (no
KiCad source was consulted — this document describes the externally
observed behavior, not the internal implementation); whether `power` vs
`mixed` affects non-DRC KiCad behaviors; whether this sandbox's missing
`kicad-footprints` submodule (`tools/setup_kicad_env.py` was never run
here) shifts the *absolute* violation counts relative to CI's real
numbers — it should not shift the *token delta*, since both compared
variants share the identical `libs/` symlink, but it does mean the
1738-ish totals in this document are not expected to match a from-scratch
CI run's totals one-for-one.
