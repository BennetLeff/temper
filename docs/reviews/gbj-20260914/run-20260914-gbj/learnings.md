## Institutional Learnings Search Results

### Search Context
- **Feature/Task**: Review the current uncommitted GBJ2510-F thermal/FEM and Rust harness scope against base `84f84fe656db56fd337f73764b98c846748b3512`; assess native-source binding, independent Gmsh/Elmer evidence, four-diode/case coupling, cooling assumptions, and explicit `INDETERMINATE` paths.
- **Keywords Used**: GBJ2510-F, thermal, FEM, Gmsh, Elmer, native source, UUID, harness, package network, diode, cooling, airflow, AC2, current distribution, indeterminate, evidence binding, replay, gate scope.
- **Files Scanned**: 216 markdown files under `docs/solutions/` (frontmatter/content prefilter, then full reads of the strong and moderate matches).
- **Relevant Matches**: 9 files.

### Relevant Learnings

#### 1. FEM power balance needs independently checked domains and ports
- **File**: `docs/solutions/best-practices/fem-balance-needs-independent-domains-and-ports.md`
- **Module**: `zapote`
- **Problem Type**: `best_practice`
- **Relevance**: This is the direct precedent for the GBJ joint extension: local conductor FEM domains are coupled to one uncertain package and must prove their own geometry, ports, and balances before temperatures are interpreted.
- **Key Insight**: A converged solver can solve the wrong geometry. Independently derive material volumes and count shared faces; require reservoir ports to be real exterior faces with the expected material and area. Keep electrical balance (`I` times measured port potential) separate from thermal balance (Joule source versus summed boundary reactions), allocate shared package loss once, and close both per-contact and global residuals. Exact trace UUIDs are required because graph split ordinals are not stable. A package node is not a resolved die junction, and numerical validity does not qualify lead, solder, wetting, or cooling applicability.
- **Severity**: high

#### 2. External FEM is a validity proxy, not a soundness or hardware certificate
- **File**: `docs/solutions/best-practices/external-fem-corroboration-validity-proxy-2026-07-09.md`
- **Module**: `temper_placer`
- **Problem Type**: `best_practice`
- **Relevance**: The GBJ work promotes retained Gmsh/Elmer output through the production harness and compares a three-dimensional joint model with package/network assumptions.
- **Key Insight**: Keep correctness, soundness, and validity claims separate. MMS or solver checks establish implementation correctness; conservation/monotonicity bounds establish model-logic soundness; a genuinely different FEM model supplies only a validity proxy. If the external instrument is unavailable, the gate must be `UNMEASURED`/fail-closed rather than a silent pass. Even agreement across model families leaves shared assumptions and hardware measurement as open obligations.
- **Severity**: high

#### 3. Solver independence is not model independence
- **File**: `docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md`
- **Module**: `temper_placer`
- **Problem Type**: `best_practice`
- **Relevance**: The new package network and FEM are two coupled instruments; their agreement must not be described as independent physical qualification if they share assumptions.
- **Key Insight**: A different linear solver or implementation does not test a different physical model. State shared assumptions explicitly (effective materials, conduction-only paths, lead/board coupling, no resolved mutual die impedance) and retain a falsifiability case where the models should diverge when a term differs. The GBJ source and harness should therefore describe FEM/network agreement as conditional numerical evidence, not as proof of real thermal behavior.
- **Severity**: high

#### 4. Model certificates require semantic binding in addition to artifact hashes
- **File**: `docs/solutions/best-practices/model-certificates-need-semantic-binding.md`
- **Module**: `zapote`
- **Problem Type**: `best_practice`
- **Relevance**: The GBJ replay binds native/manufacturing JSON, waveform, source PDF, raw FEM artifacts, and a package-specific model through the common harness.
- **Key Insight**: Hashes prove which bytes were supplied, not that the equations, topology, identities, and claims agree. An executable validator must recompute semantics and retain rejecting controls for changed topology, parameter ranges, duplicate/missing cases, and rehashed contradictory output. Exact component facts and temperature limits do not transfer across units. Device and assembly applicability stays `INDETERMINATE` after numerical qualification.
- **Severity**: high

#### 5. Thermal evidence must prove complete connectivity and scope ratings to the assembly
- **File**: `docs/solutions/logic-errors/thermal-model-rating-and-connectivity-boundaries.md`
- **Module**: `zapote-thermal-sense` (procedure transfers to this thermal review)
- **Problem Type**: inferred (no `problem_type` in frontmatter)
- **Relevance**: GBJ accepts native pin/net/trace identity and reports package, lead, board, and cooling limits while the assembled path and hardware remain unknown.
- **Key Insight**: Do not replace a complete connected group with a union of endpoints; reject malformed or duplicate evidence before normalizing it. Reconfirm exact-part evidence and scope each rating to the assembly that earned it. A native connectivity result can be correct while the device definition, lead path, connector, or installed harness remains wrong or unqualified. Keep conditional arithmetic separate from hardware applicability.

#### 6. Qualification exports need clean-build replay and protected candidate boundaries
- **File**: `docs/solutions/best-practices/qualification-exports-require-clean-build-replay-2026-09-01.md`
- **Module**: `electrical_qualification`
- **Problem Type**: `best_practice`
- **Relevance**: The GBJ study retains candidate-only source, native, manufacturing, waveform, cooling, and FEM artifacts while the production board remains unchanged.
- **Key Insight**: Rebuild or regenerate candidate inputs from declared sources in an isolated root, compare normalized output byte-for-byte, and keep verification separate from publication. Narrow normalization must remove only demonstrated toolchain noise; broad rewriting can hide identity or topology drift. Snapshot protected production artifacts and reject path escapes, aliases, or mutations. A syntactically valid evidence tree is not enough.
- **Severity**: high

#### 7. Measurement conventions and source identities must be explicit
- **File**: `docs/solutions/best-practices/measurement-convention-must-be-stated-2026-07-28.md`
- **Module**: `temper_placer`
- **Problem Type**: `best_practice`
- **Relevance**: The GBJ cooling budget mixes catalog sink resistance, airflow endpoints, FEM reservoir temperatures, and point-estimate diode forward voltage; each quantity has different conditions and authority.
- **Key Insight**: Same-unit numbers can answer different questions. Name the measurement basis and test conditions in fields, distinguish catalog/free-air/shutoff values from installed flow, and treat a number copied from a source as conditional unless the source's operating point matches the design point. Re-derive from primary artifacts when a threshold verdict is close.
- **Severity**: high

### Contradicted documented rules observed in the current diff

#### A. GBJ diode pair mapping contradicts the native sign/topology contract
- **File**: `zapote/packages/zapote-thermal/src/joint_model.rs:132`
- **Rule**: `model-certificates-need-semantic-binding.md` requires semantic checks to bind model claims to the exact source topology; the FEM balance learning likewise requires exact native identities rather than a plausible self-consistent model.
- **Observed line**: `let pair = if s.line_sign > 0.0 { [0, 3] } else { [1, 2] };`
- **Why this is a contradiction**: The native/PFC mapping in `zapote/packages/zapote-harness/src/pfc_power.rs:113-116` injects `bridge.2 = -a`, `bridge.3 = +a`, and sends the positive terminal current through the bridge positive pin. The current code's positive/negative pair choice therefore needs to be justified against the reviewed pin/conduction direction; as written, the semantic topology is not visibly derived from the source contract. The symmetric fixture can mask a swapped pair because it yields 10 W per diode either way. Preserve an asymmetric half-cycle regression through the mandatory harness and make the source-to-pair mapping explicit.
- **Review status**: Direct current-diff contradiction; parent correctness reviewer independently reported the same issue as P1.

#### B. The mandatory harness omits a predeclared fan-loss scenario
- **File**: `zapote/packages/zapote-harness/src/bridge_thermal.rs:96-97`
- **Rule**: `gate-subset-blindness-2026-07-27.md` says a gate that evaluates a real subset of its declared universe must expose its denominator/scope; prefer default inclusion over an include-list that silently omits new cases.
- **Observed lines**: `let nominal = named("nominal-fine")?;` and `let weak = named("weak-assembly")?;` while `zapote/packages/zapote-thermal/src/joint_model.rs:460-467` adds `Scenario { name: "fan-loss", ... }` for GBJ.
- **Why this is a contradiction**: `run_gbj_model` reports only nominal and weak cases, so the fan-loss evidence can change or exceed a limit without affecting any emitted mandatory cooling finding. Require and surface the fan-loss case explicitly, retaining `INDETERMINATE` for unmodeled shutdown timing and installed airflow.
- **Review status**: Direct current-diff contradiction; parent correctness reviewer independently reported the same issue as P2.

### Recommendations

- Preserve the FEM balance procedure from the current `fem-balance` learning: independently check volumes, material interfaces, exterior ports, electrical Joule balance, thermal reactions, per-contact residuals, and the global residual before interpreting temperatures.
- Keep native package identity, pin semantics, trace UUIDs, and source bytes as authoritative inputs. Do not let regenerated producer hashes or a symmetric waveform stand in for a semantic topology check.
- Make every GBJ scenario generated by `joint_model` visible in the mandatory harness, including fan-loss. Emit the denominator/sensitivity name and retain `INDETERMINATE` whenever installed airflow, transient behavior, or AC2 current sharing is unresolved.
- Retain the three-target language in reports: numerical FEM/network agreement is conditional model evidence and a validity proxy; it is not hardware qualification or a guaranteed hot-loss bound.
- Keep candidate replay isolated and reproducible. Regenerate geometry/SIF from retained inputs, validate raw artifact hashes and tool versions, and ensure candidate evidence cannot rewrite or silently replace maintained board artifacts.

