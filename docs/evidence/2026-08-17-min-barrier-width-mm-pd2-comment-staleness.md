# `MIN_BARRIER_WIDTH_MM` "still PD2-pinned" — investigated: stale comment, NOT a live permissive figure

2026-08-17. Board sha256 `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
(unchanged — verified before and after). Main at session start: `775a7a40e`.

## The claim under investigation

`pcb/temper.kicad_dru` is generated (gitignored, not committed) by
`scripts/generate_kicad_dru.py`. Its emitted header carried the text: "The
keepout gate's own `MIN_BARRIER_WIDTH_MM` is still PD2-pinned and is a
separate follow-up" (source: `scripts/generate_kicad_dru.py`, formerly
lines 767-769). Task: determine whether this is a live permissive figure
on a mains-voltage board (report loudly, do not fix) or a documented
deliberate exception.

## Investigation

**Verdict: neither. It is a STALE COMMENT describing an already-resolved
situation — not a live permissive figure, not a deliberate exception.**

1. **The actual enforced value**, read directly from
   `packages/temper-placer/src/temper_placer/core/isolation_constants.py`:

   ```python
   MIN_BARRIER_WIDTH_MM = 12.6
   ```

   12.6mm is the PD3 (reinforced creepage) figure, not PD2 (8.0mm).

2. **When it was fixed**: `git log` on the file shows
   `MIN_BARRIER_WIDTH_MM` moved 8.0 → 12.6 in `fe41fb78a` (PR #1229,
   2026-08-15, "enforce PD3 creepage (12.6mm reinforced / 10.0mm tank) +
   make Gate 4 blocking") — the SAME commit that flipped
   `generate_kicad_dru.py`'s own `HV_CREEPAGE_ENFORCED_MM` to PD3. The
   commit message states explicitly: "isolation_constants.MIN_BARRIER_WIDTH_MM:
   8.0 -> 12.6 (keepout gate)."

3. **Where the stale text came from**: the comment being investigated was
   written one commit earlier, `77945b1ea` (PR #1220, "wire safety
   constants to Rust SafetyValue pyo3 lookups; enforce PD3") — at that
   point in history `MIN_BARRIER_WIDTH_MM` genuinely WAS still 8.0/PD2, and
   the comment correctly said so ("`check_isolation_keepout.py`
   `MIN_BARRIER_WIDTH_MM` (8.0mm/PD2) alignment is that gate's own
   follow-up"). PR #1229 fixed the constant later the same day but never
   updated this specific comment block — even though the SAME PR rewrote
   the adjacent, *correct* comment at `HV_CREEPAGE_ENFORCED_MM`'s own
   definition (currently lines 143-151) to say "must remain aligned with
   `check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM`. Both enforcement
   points therefore emit/enforce 12.6mm" — an internally inconsistent
   pair of comments within the same file, one correct and one stale.

4. **Cross-checked every other reference to `MIN_BARRIER_WIDTH_MM` in the
   tree** (`grep -rn "MIN_BARRIER_WIDTH_MM"` across `*.py`/`*.rs`/`*.yaml`/
   `*.ato`) for a second, still-8.0 definition that might make the comment
   correct after all:
   - `scripts/check_isolation_keepout.py`'s own module docstring already
     states "`MIN_BARRIER_WIDTH_MM` is therefore **12.6mm** for the
     enforced PD3 classification" — current, correct.
   - `scripts/tests/test_generate_kicad_dru.py:44` already asserts
     "`MIN_BARRIER_WIDTH_MM` (also 12.6mm/PD3)" — current, correct.
   - Two genuinely-historical narrative comments reference "8.0mm" as a
     past state (`elec/src/modules.ato:1000`, part of a dated
     "FOOTPRINT/MPN CORRECTED AGAIN 2026-08-13" decision trail — history,
     not a live claim) and one intentionally-named PD2-comparison Rust
     helper (`safety_value.rs::reinforced_creepage_400v_pd2()`, called only
     from its own module's test, "PD2 stays queryable for comparison" per
     `net_types.rs`'s doc comment) — neither is the live enforcement path,
     neither claims otherwise.
   - No other site claims `MIN_BARRIER_WIDTH_MM` is presently 8.0/PD2.

5. **Confirmed no test pins the stale comment's literal text**
   (`grep -rln "still PD2-pinned"` → only the one file, before the fix).

## Conclusion

`MIN_BARRIER_WIDTH_MM` is NOT a live permissive figure on this
mains-voltage board — it has been correctly enforced at 12.6mm/PD3 since
2026-08-15 (PR #1229), the same day the rest of the PD2→PD3 flip landed.
The only thing "still PD2" was a comment describing a `.kicad_dru` file
that gets regenerated fresh from source on every run — the stale text
never represented an actual gap in enforcement, only a documentation
lag of about a day within the same PR sequence.

## Action taken

This is a docs-only correction (no clearance, creepage, copper-weight, or
DRU threshold was touched — `HV_CREEPAGE_PD2_MM`/`HV_CREEPAGE_PD3_MM`/
`HV_CREEPAGE_ENFORCED_MM`/`isolation_constants.MIN_BARRIER_WIDTH_MM` are
all unmodified), so it does not fall under the hard rule reserved for
live/permissive findings ("do not change it unilaterally — report the
precise decision needed"). Corrected the stale comment block in
`scripts/generate_kicad_dru.py` to state the current, accurate fact (both
enforcement points at 12.6mm/PD3) and recorded why the old text existed,
rather than leaving a misleading "separate follow-up" TODO sitting in
every future regeneration of the safety-critical DRU file's own header.

Verified: `pytest scripts/tests/test_generate_kicad_dru.py` — 35/35 pass
(no test pinned the stale text). `pcb/temper.kicad_pcb` sha256 unchanged
(`33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`); this
change touches only the DRU generator's Python source, never the
gitignored, regenerated `.kicad_dru` output nor the board file.
