---
date: 2026-06-21
topic: firmware-ssot-codegen
---

# Firmware SSOT: Config Codegen + X-Macro State Enum

## Summary

A firmware-only initiative that collapses the Temper induction cooker's three-way configuration duplication into a single generated header, and replaces the hand-maintained state-name switch with an X-macro list. Today the values `SAFE_IDLE_TEMP`, `MAX_TEMP`, `MIN_TEMP`, `PAN_DETECT_TIMEOUT_MS`, `NO_PAN_TIMEOUT_MS`, `PAN_DEBOUNCE_COUNT`, `PAN_CONFIDENCE_REQUIRED`, `MAX_PREHEAT_TIME_MS`, and `MESSAGE_DISPLAY_TIME_MS` live as bare `#define`s in `firmware/main/state_machine.c:39-47`, *and* again as `TEMP_LIMITS_DEFAULT` / `TIMEOUTS_DEFAULT` / `THRESHOLDS_DEFAULT` aggregates in `firmware/config.h`, *and* again as the values loaded by `config_init()` in `firmware/config.c`. The header comment in `config.h:16-18` admits this is intentional ("legacy #defines continue to work"), which means the duplication is a feature that has to be laboriously preserved on every edit. The 8-state `system_state_t` enum is mirrored a third time by the literal-string `switch` in `state_machine_get_state_string` (`state_machine.c:309-321`) and a fourth time by the `fault_code_t` enum and its own `state_machine_get_fault_string` switch.

This work makes the SSOT claim true by construction: a single YAML manifest is rendered through a Jinja2 template into `firmware/config.h` (containing both the legacy `#define` surface *and* the `g_config` struct/init defaults), and `state_machine.h` is rewritten with an X-macro list that expands to the enum, the count sentinel, the string table, and the fault enum in one source location. Adding a tunable or a state becomes one line in the manifest.

---

## Problem Frame

The duplication is not theoretical. `state_machine.c` uses the bare `#define`s directly (e.g. `if (current_temp < SAFE_IDLE_TEMP)` at `state_machine.c:852`, `sm_ctx.countdown_timer_ms = PAN_DETECT_TIMEOUT_MS` at `:483`); `config.h` defines the same numeric values inside `TEMP_LIMITS_DEFAULT` / `TIMEOUTS_DEFAULT` / `THRESHOLDS_DEFAULT`; and `config_init()` (`config.c:27-36`) just copies those `#define`-derived defaults into `g_config`. The two representations never reference each other; a developer editing one has to remember to edit the other two. The `firmware/README.md` table at lines 154-159 documents a fourth copy, which disagrees with `state_machine.c` (`README` says `MIN_TEMP=50°C`, the code says `30°C`) — the exact silent drift this initiative exists to prevent.

The state enum has the same shape at smaller scale: `system_state_t` (`state_machine.h:26-35`) lists 8 states; `state_machine_get_state_string` (`state_machine.c:309-321`) repeats them as string literals; `firmware/main/state_machine.c:5-14` repeats them in the file header comment; the `transition_to` log line (`state_machine.c:948-949`) depends on the string function being exhaustive; and `fault_code_t` (`state_machine.h:40-52`) plus its own string switch (`state_machine.c:295-307`) repeat the pattern. Adding a state today requires four coordinated edits across two files; forgetting one produces either a missing string (silent "UNKNOWN" in logs) or an unhandled case (caught only by `-Wswitch` if enabled, otherwise silent).

---

## Actors

- A1. **Firmware developer** — adds or tunes a state-machine tunable (temperature limit, timeout, debounce count) or adds a new state. The primary person who today performs the same edit in three places.
- A2. **Host test build** — `firmware/test/CMakeLists.txt` builds a Unity-based `test_runner` and many per-component targets host-side, with `-DHOST_BUILD`. The enforcement surface for codegen regressions (a generated header that disagrees with the manifest, or a state added to the enum but missing from the string table).
- A3. **ESP-IDF build** — `firmware/CMakeLists.txt` includes `$ENV{IDF_PATH}/tools/cmake/project.cmake`; `firmware/main/CMakeLists.txt` registers the main component with `SRCS main.c state_machine.c`. The build that must invoke codegen before compiling `state_machine.c` and any file that includes `config.h`.

---

## Key Flows

- F1. **Developer tunes a timeout**
  - **Trigger:** A1 changes `pan_detect` timeout from 5000ms to 4000ms.
  - **Actors:** A1, A2, A3
  - **Steps:** (1) A1 edits the single YAML entry. (2) The pre-build codegen step regenerates `firmware/config.h` (the `_DEFAULT` aggregate, the legacy `#define`, and the env-var documentation comment all emit from the one input). (3) A3 compiles; the new value flows into both `state_machine.c`'s direct `#define` use and `g_config` via `config_init`, automatically consistent. (4) A2's host test build runs `test_state_machine.c`; a test asserting `PAN_DETECT_TIMEOUT_MS == 5000` fails visibly if A1 forgot to update the test's expected value alongside the manifest.
  - **Outcome:** A tunable change that propagates to every consumer from one edit; any test that hardcoded the old value fails with a named assertion, not a silent behavior change.
  - **Covered by:** R1, R2, R6

- F2. **Developer adds a state**
  - **Trigger:** A1 adds `STATE_BOIL_HOLD` between `HEATING` and `NO_PAN`.
  - **Actors:** A1, A3
  - **Steps:** (1) A1 adds one `STATE(BoilHold, "BOIL_HOLD")` line to the X-macro list in `state_machine.h`. (2) The enum, the count sentinel (`STATE_COUNT`), the string table, and (where referenced) any per-state dispatch table all expand from the macro. (3) A3 compiles; `-Wswitch` reports any `switch` on `system_state_t` that fails to handle the new state. (4) Logs printed via `transition_to` print `"BOIL_HOLD"` — never the silent `"UNKNOWN"` fallback.
  - **Outcome:** A new state is visible in every consumer after one edit; an unhandled `switch` case is a compile error, not a runtime surprise.
  - **Covered by:** R3, R4, R5

- F3. **CI regenerates and diff-checks the header**
  - **Trigger:** Push to the firmware tree.
  - **Actors:** A2, A3
  - **Steps:** (1) CI runs the codegen script against the committed manifest. (2) CI `git diff --exit-code firmware/config.h` against the committed generated header. (3) A drift — someone edited `config.h` directly, or edited the manifest but didn't regenerate — fails the step with the diff attached. (4) The host test build then compiles the regenerated header and runs the full `test_runner`.
  - **Outcome:** A generated header that disagrees with its manifest is a CI failure with a named diff, never a silently stale artifact shipped to a device.
  - **Covered by:** R6, R7

---

## Requirements

**Phase 1 — X-macro state enum (low-risk, no codegen)**

- R1. `system_state_t` in `firmware/main/state_machine.h` is rewritten as an X-macro expansion: a `STATE(Idle, "IDLE")`-style list expands to the enum, a trailing `STATE_COUNT` sentinel, and a `state_name_table[]` array of `{ system_state_t value; const char *name; }`. The current enum and the `state_machine_get_state_string` switch at `state_machine.c:309-321` are both removed in favor of the macro-generated table lookup. Adding a state becomes one line; the string table cannot drift from the enum by construction.
- R2. `fault_code_t` and `state_machine_get_fault_string` (`state_machine.c:295-307`) receive the same X-macro treatment as a single additional list — `FAULT(None, "NONE")` etc. — so the fault string switch is also generated. The fault and state lists are independent macros; they are not merged.
- R3. Every `switch` statement on `system_state_t` or `fault_code_t` in `firmware/main/state_machine.c` (notably `transition_to`) gains a `default:` that calls a fault handler or `abort()` — the X-macro list is the only place a new state is added, and an unhandled case must not silently fall through to "do nothing."

**Phase 2 — Config manifest + codegen**

- R4. A new firmware-local manifest (YAML) is added under `firmware/` and is the **single** declaration of every tunable currently present in `state_machine.c:39-47`, `config.h:52-112` (`TEMP_LIMITS_DEFAULT`, `TIMEOUTS_DEFAULT`, `THRESHOLDS_DEFAULT`), and the `config_load_from_env` env-var names. Each entry declares: C symbol name, value, C type, units, the env-var name A1 can override at runtime, and a doc string. The manifest is the SSOT; no other file independently states these numeric values.
- R5. A Jinja2 template renders the manifest to `firmware/config.h`. The generated header preserves: (a) the legacy `#define` surface (e.g. `#define SAFE_IDLE_TEMP 50.0f`) so existing call sites in `state_machine.c` and `state_machine.h` continue to compile without edits; (b) the `temperature_limits_t` / `timeouts_t` / `thresholds_t` structs and their `*_DEFAULT` initializer macros; (c) the `config_t` aggregate and `g_config` extern. The header file comment is regenerated to say the file is generated and to point at the manifest, replacing the current "ADDITIVE, non-breaking … continue to work" note with a statement that is now true by construction.
- R6. The codegen script is idempotent: running it twice produces byte-identical output. It is wired into the ESP-IDF build as a CMake pre-build custom target that regenerates `config.h` before `state_machine.c` and `config.c` compile (via `add_custom_command` with the header in `MAIN_DEPENDENCY` and `BYPRODUCTS`), and is also runnable standalone (`python3 firmware/tools/gen_config.py`) for developers not invoking the full IDF build. The host test build (`firmware/test/CMakeLists.txt`) invokes the same script before any test target compiles, so `test_state_machine.c` and friends pick up the generated header automatically.
- R7. `firmware/config.h` is committed to version control (not gitignored) and treated as a versioned derived artifact. A CI step regenerates it and `git diff --exit-code`s against the committed copy; any drift fails the step. The "regenerate and commit" command is documented in `AGENTS.md` next to the other one-liners.

**Phase 3 — Migration and enforcement**

- R8. The bare `#define`s in `firmware/main/state_machine.c:39-47` are deleted. Their call sites (e.g. `:239`, `:279`, `:444-445`, `:452-453`, `:483`, `:505`, `:570`, `:706`, `:722-723`, `:729-730`, `:761`, `:852`) `#include "config.h"` and continue to use the same names — the names are now emitted by the generated header, so no call-site rewrite is required. The `MESSAGE_DISPLAY_TIME_MS` define (line 47) migrates with the others.
- R9. A host test asserts the generated header's values match the manifest for at least: every temperature limit, every timeout, every pan-detection threshold. The test is built into the existing `test_runner` target and fails CI if the committed `config.h` was not regenerated after a manifest change. This is the regression net for "edited the manifest but forgot to rerun codegen."
- R10. A host test asserts that `state_machine_get_state_string` returns a non-`"UNKNOWN"` name for every `system_state_t` value in `[0, STATE_COUNT)` and every `fault_code_t` value in the equivalent range, exercising the X-macro-generated tables. A state added to the enum but missing from the string list (the historical drift failure mode) fails this test.

---

## Acceptance Examples

- AE1. **Covers R1, R2.** Given a developer adds `STATE(BoilHold, "BOIL_HOLD")` to the X-macro list, when `idf.py build` runs, the generated enum contains `STATE_BOIL_HOLD`, `STATE_COUNT` increments by one, and `state_machine_get_state_string(STATE_BOIL_HOLD)` returns `"BOIL_HOLD"` — all from the one-line edit. No switch statement is hand-edited.
- AE2. **Covers R3.** Given a `switch (sm_ctx.current_state)` block in `state_machine.c` lacks a `case STATE_BOIL_HOLD:` after the new state is added, when `idf.py build` runs with `-Wswitch` (or the X-macro `default:` path), the build fails naming the unhandled state. The new state is not silently run through the old code path.
- AE3. **Covers R5.** Given the manifest declares `safe_idle_temp: 50.0`, when `python3 firmware/tools/gen_config.py` runs, the regenerated `config.h` emits both `#define SAFE_IDLE_TEMP 50.0f` *and* `.safe_idle_temp = 50.0f` inside `TEMP_LIMITS_DEFAULT`. The two never disagree because they are emitted from the same manifest field in the same template pass.
- AE4. **Covers R6, R7.** Given a developer hand-edits `firmware/config.h` to change `MAX_TEMP` to `260.0f` without touching the manifest, when CI runs, the regenerate-and-diff step fails with a diff showing the two lines changed, and the build does not proceed.
- AE5. **Covers R9.** Given the manifest is edited to set `pan_detect_timeout_ms: 4000` but `config.h` is not regenerated, when CI runs the test_runner, the "config matches manifest" test fails with `"PAN_DETECT_TIMEOUT_MS: header=5000, manifest=4000"`.
- AE6. **Covers R10.** Given a state is added to the X-macro list but the string-name field is left blank, when `test_state_machine_only` runs, the state-name table walk fails at `STATE_BOIL_HOLD` returning `""` or `"UNKNOWN"`, naming the offending entry.

---

## Success Criteria

- A firmware developer who tunes a temperature limit edits exactly one file (the manifest) and the change is reflected in both `state_machine.c`'s direct constants and `g_config` — verified by the R9 test, not by human review.
- A firmware developer who adds a state edits exactly one line (the X-macro list) and the enum, the count, the string table, and `-Wswitch` coverage all update — verified by the R10 test, not by remembering four locations.
- `firmware/README.md`'s tunable table and the committed `config.h` cannot disagree, because the same codegen pass that emits `config.h` is the source for the README values (or the README table is removed in favor of a generated appendix — see Open Questions).
- The historical `MIN_TEMP` drift (`README` says 50°C, `state_machine.c` says 30°C) is unresolvable by future edits: there is only one place to state the value.
- The host test build (`firmware/test/`) is the regression net: a generation-regression PR fails CI before merge, not in the field.

---

## Out of Scope

- **Generating `g_config` runtime overrides from the manifest env-var names.** `config_load_from_env` (`config.c:49-149`) keeps its existing hand-written env-var plumbing; only the `*_DEFAULT` macros and the legacy `#define`s are generated. Generating the env-var plumbing is a reasonable follow-up but doubles the template's surface area for marginal benefit.
- **Merging the manifest into `design_rules.py`.** The PCB placer's `temper_placer/core/design_rules.py` concerns trace widths, clearances, and via templates — physical routing constraints, not firmware behavior. Firmware limits like `SAFE_IDLE_TEMP` do not belong in the PCB design-rules model. The manifest is firmware-local.
- **Generating `system_state_t` *and* the state-handler dispatch table.** The state-handler forward declarations and the implicit `state_<x>_entry/_update` dispatch in `state_machine.c` stay hand-written; the X-macro covers only the enum, the count, and the string tables. A dispatch-table generator is a bigger refactor and not required to fix the duplication this initiative targets.
- **NVS-backed config persistence.** `config_load_from_env` and `nvs_flash` (a `REQUIRES` of the main component) suggest runtime-loaded config is plausible, but implementing NVS persistence of `g_config` is a separate feature, not a SSOT fix.
- **Atopile / KiCad cross-layer SSOT.** The VoltageMap / DRU codegen work lives in the source-of-truth-validation initiative; this initiative is firmware-only.

---

## Assumptions

- **A1. Jinja2 is acceptable as a new firmware-tree Python dependency.** It is not currently used in the firmware tree (the only `jinja` references in the repo are inside `temper-placer/.venv` site-packages). Adding it to a firmware-local `requirements.txt` is a one-time cost; the alternative (string templating in stdlib Python) is materially more error-prone for a header this size. **Risk if wrong:** firmware contributors must `pip install jinja2` to regenerate the header — mitigated by the CI regenerate step, which means a contributor who skips it still gets a failing CI, not a broken device.
- **A2. ESP-IDF's CMake support for `add_custom_command`/`BYPRODUCTS` is sufficient to make `config.h` a generated-byproduct that compiles cleanly.** ESP-IDF wraps the standard CMake machinery; the standard pattern is supported but unverified for this exact use case. **Risk if wrong:** the pre-build step runs as a separate `idf.py` invocation instead of in-build; the host test build is unaffected (plain CMake).
- **A3. The Unity-based host test build is the correct regression surface.** `firmware/test/CMakeLists.txt` already builds `test_state_machine_only` against the real `state_machine.c` with stubs; the R9/R10 tests slot into this existing target. **Risk if wrong:** the codegen-regression tests must run in CTest, not in IDF's device-side harness; confirm during planning.
- **A4. The `#define`-to-`g_config` migration in R8 is safe because the names are byte-for-byte preserved by the generator.** If the manifest emits a different symbol name (e.g. uppercase-vs-camelCase), `state_machine.c` call sites break at compile time — a loud, not silent, failure. **Risk if wrong:** a planned, not incremental, cutover; ensure call-site rewrite PR is one atomic commit.
- **A5. YAML is the right manifest format over TOML or JSON.** Firmware tunables are flat key-value with comments; YAML supports inline comments and is already the format used by `temper-placer` YAML configs (`design_rules.py` imports `yaml`). **Risk if wrong:** trivial — the manifest is small enough to migrate in one pass.
- **A6. The `firmware/README.md` tunable table at lines 154-159 will be regenerated from the manifest or deleted in favor of "see the manifest."** Today it is a fourth copy and has already drifted (`MIN_TEMP = 50°C` per README vs `30°C` in code). **Risk if wrong:** the README table continues to drift and the SSOT claim is undermined; resolve during Phase 2.

---

## Open Questions

### Resolve Before Planning

- **[Affects R6][Build]** Does ESP-IDF's CMake wrapper allow `add_custom_command(... BYPRODUCTS firmware/config.h)` inside `firmware/main/CMakeLists.txt` such that `state_machine.c` and `config.c` recompile when the manifest changes? Or does ESP-IDF require the custom command to live at the project level (`firmware/CMakeLists.txt`)? This determines where the codegen hook attaches.
- **[Affects R8][Migration]** Are there consumers of the bare `#define`s outside `firmware/main/state_machine.c` — e.g. test files under `firmware/test/` that reference `SAFE_IDLE_TEMP` or `MAX_TEMP` directly? `test_state_machine.c:230,354` reference `PAN_CONFIDENCE_REQUIRED` and `PAN_DEBOUNCE_COUNT` by name in comments; confirm whether any test asserts a numeric value that the migration would silently change.
- **[Affects R5][Format]** Does the generated `config.h` need to keep *exactly* the legacy `#define` names (uppercase, current identifiers) so downstream symbols and `config_load_from_env` env-var strings (`TEMP_SAFE_IDLE_C`, etc.) remain stable? Or is this the moment to rename to a single convention? Default assumption: keep legacy names verbatim; rename is a follow-up.

### Deferred to Planning

- **[Affects R7][CI]** Where does the regenerate-and-diff step live — in the existing firmware CI, the broader `bd`/beads pipeline, or both? The comparable golden-file diff in the source-of-truth-validation initiative lives in CI; this should mirror it.
- **[Affects R9][Testing]** Should the "header matches manifest" test be a Python script run in CI (easier to introspect failures) or a C test inside `test_runner` (runs in the same harness as everything else)? Default assumption: Python script — it can parse both YAML and the generated C in one pass without a C harness.
- **[Affects README][Documentation]** Delete the `firmware/README.md:154-159` tunable table outright, or regenerate it from the manifest as an appendix? Deleting is simpler; regenerating keeps the user-facing doc but adds a second template.