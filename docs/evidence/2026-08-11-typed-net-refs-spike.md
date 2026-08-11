<!-- provenance: commit=2426f5cf59dbdc37c93ab7ffeaa0e3b435c36f9c dirty=false (base) -->

# Typed net refs spike: parse-don't-validate at the config boundary, prototyped and costed

**Recommendation: parse-don't-validate at the config -> netclass-assignment
boundary, with case-sensitive (strict) resolution.** Concretely: a
`ValidatedNetClassMap` Rust type whose only constructor,
`ValidatedNetClassMap::resolve(known_nets, raw)`, returns `Result<Self,
Vec<UnresolvedNetClassKey>>` -- `Ok` only when *every* key in the raw
`net_classes:` mapping is an exact, case-sensitive match against a real net
name. **What it makes unrepresentable**: a `ValidatedNetClassMap` value that
contains a key naming no real net cannot exist -- not "is checked for," does
not exist as a producible value. Prototyped end-to-end as a new pyo3 method,
`Netlist.apply_net_class_mapping_strict`, which turns the exact miss that
caused the real incident into `ValueError: 5 net_classes key(s) do not match
any real net...` at the call site, instead of a silent 6-of-11 partial
application.

**What it costs**: one new ~260-line Rust module (`net_class_validation.rs`,
about half of it tests, no dependencies beyond `std`), one new pyo3 method
(~35 lines, additive -- the existing oracle-parity method is untouched),
9 Rust unit tests + 10 Python integration tests, all green. That
is the true cost of the prototype. The cost of generalizing it is much
larger and is why this stays a spike: a **handle-based `NetId`** (the
strongest unrepresentability guarantee considered) would touch every one of
the ~140 `NetName`/`NetClassName`/`ComponentRef` construction sites already
found across `temper-drc-rs` and `temper-design-bundle` alone (Sec. 1), and
none of that guarantee would survive the pyo3 crossing back into Python
undiminished (Sec. 4) -- Python can still mutate a validated `Net`'s `.name`
field directly after the fact, demonstrated in Sec. 4. Sec. 1 also found a
second, more dangerous instance of the identical defect shape, live and
unconditional inside the CI-gating DRC path itself
(`board_py_bridge.rs::build_board_state` / `drc_marshal.rs` silently
default an unmatched net to class `"Unknown"` and the thinnest
0.2 mm/0.2 mm rules, rather than erroring) -- Sec. 5 names it the
highest-leverage next step, not fixed here because it is a behavior
change to a CI gate and needs its own advisory-vs-blocking decision. Sec. 5
also gives the per-file cost to wire this prototype into the other 3
broken config files' real call sites, and relates it to the
`check_netclass_map_board_correspondence.py` gate that already catches the
same defect at the data layer.

---

## 1. Survey: where net names and component refs cross as raw strings

Before proposing anything, the blast radius, measured directly against
`origin/main` (commit `2426f5cf5`):

| Where | What | Count |
|---|---|---|
| `temper-drc-rs/src/board.rs` | Already has `NetName(pub String)` / `ComponentRef(pub String)` / `NetClassName(pub String)` newtypes -- but every field is `pub`, and `impl From<&str> for NetName` is public and unconstrained | 3 newtypes, all freely constructible |
| `temper-drc-rs/src/**` | `NetName(` / `NetClassName(` direct construction call sites | 58 + 81 = 139 (the large majority are test fixtures, e.g. `rules/mod.rs`, `rules/erc/net_connectivity.rs`; production sites are `board_py_bridge.rs` and `drc_marshal.rs`, both parsing straight from pyo3-marshalled strings with no validation) |
| `temper-io-types`, `temper-drc-rs`, `temper-design-bundle`, `temper-orchestration`, `temper-constraint-compiler`, `temper-pcl-ir` (`src/**`) | Lines matching `net_name` | 432 |
| Same six crates | `ComponentRef(` construction sites | 47, across 19 files |
| `temper-design-bundle/src/*.rs` + `temper-drc-rs/src/*.rs` | pyo3 `.getattr("name")` / `.getattr("ref")` / `.getattr("net_class")` -- i.e. a raw string crossing the FFI boundary by attribute name, with no schema | 73 |
| `packages/temper-placer/src/**`, `scripts/**` (Python) | Files referencing `net_classes` | 37 |

**Finding**: the blast radius is large enough that a repo-wide migration is
not attemptable in a spike, confirming the brief's instruction to scope to
one boundary. But it is not uniform. Two sub-populations exist:

1. **Test-fixture construction** (`rules/mod.rs`, `net_connectivity.rs`,
   `zone_containment.rs`) -- these construct `NetName("N1".into())` etc.
   directly because the tests want a specific, possibly-nonexistent net
   name on purpose (e.g. `NetName("N_ORPHAN".into())` to test an
   orphan-net check). These sites are not bugs; a stricter constructor
   would have to special-case tests, which defeats the type-safety
   argument. Any handle-based redesign has to answer "how do tests build a
   `BoardState` with deliberately-bad nets" before it can be adopted here.
2. **Production marshalling** (`board_py_bridge.rs`, `drc_marshal.rs`,
   `netlist_contracts.rs`, `parse_engine.rs`) -- these parse a `NetName`
   straight out of a pyo3 `Bound<PyAny>` or a KiCad s-expression with no
   validation. This is the population any real fix has to touch, and it is
   much smaller than 139 -- on the order of a dozen call sites across the
   two crates that actually build a `BoardState`/`Netlist` from external
   input.

**A second, more dangerous instance of the identical defect shape, found
while surveying `temper-drc-rs`**: `board_py_bridge.rs::build_board_state`
(the deserializer behind `run_drc`, the actual CI DRC entry point) and
`drc_marshal.rs` (lines 909-930, an independent, duplicated copy of the
same join) both build each `Net` by joining the board's own net list
against a `net_classes: HashMap<String, String>` extracted from the
Python side:

```rust
// board_py_bridge.rs:696-709
let class_name = net_classes_raw
    .get(&name)
    .map(|c| NetClassName(c.clone()))
    .unwrap_or(NetClassName("Unknown".to_string()));
let rules = net_class_rules
    .get(&class_name)
    .cloned()
    .unwrap_or_else(|| NetClassRules { trace_width_mm: 0.2, clearance_mm: 0.2, ..Default::default() });
```

This is the same defect shape walked from the opposite direction: instead
of "a config key matches no real net" (silently ignored, Sec. 1's main
thread), this is "a real net matches no `net_classes` key" (silently
defaulted to class `"Unknown"` and the thinnest, lowest-clearance rules in
the system, 0.2 mm/0.2 mm). It is arguably *more* dangerous than the
config-key miss: it is unconditional, fires on every `run_drc` call (the
actual CI-gating DRC path), not an occasionally-run script, and it
actively substitutes the least-safe class rather than merely leaving a
previous assignment in place. Confirmed live in both files by direct
read, not construction from the doc's prose. Both sites are real and
unwired by this prototype -- `ValidatedNetClassMap`'s pattern (a net with
no matching class should be a hard error, not a default) applies here at
least as strongly as at the config-load boundary, and is the
highest-leverage next step named in Sec. 5.

**The actual defect's production path** (the config-key-miss direction),
traced directly (not from the correspondence-gate doc, independently
re-derived here):

```
configs/temper_deterministic_config.yaml, packages/temper-placer/configs/temper_constraints.yaml,
packages/temper-placer/configs/gate_driver_constraints.yaml
    -> temper_placer.io.config_loader.load_constraints
       (a pure re-export of the Rust pyfunction: temper-design-bundle/src/config_loader.rs
        `load_constraints`, already migrated to Rust)
    -> _constraint_types/config.py's `DesignConstraints.net_classes: dict[str, str]`
       (pydantic `Field`, no validator -- config_loader.rs line ~1261 passes
        the raw YAML `net_classes` dict straight through, unmodified)
    -> scripts/run_feedback_loop.py:212
       `net_class_mapping = getattr(constraints, "net_classes", {})`
       `parse_result.netlist.apply_net_class_mapping(net_class_mapping)`
    -> Netlist.apply_net_class_mapping (temper-design-bundle/src/netlist_contracts.rs:917)
       `if mapping.contains(&name)? { ... } ` -- exact PyAny-level dict
       lookup; a miss falls through with NO error, no log, no count
       surfaced to the caller beyond the aggregate "N updated" line
       `run_feedback_loop.py` already logs but never checks against
       `len(net_class_mapping)`.
```

`apply_net_class_mapping`'s own Python oracle
(`packages/temper-placer/tests/core/_netlist_py_oracle.py:245`, the pinned
verbatim implementation the Rust version must match bit-for-bit) states the
silent behavior directly in its docstring:

> "This updates the net_class attribute of each Net object based on the
> provided mapping. Nets not in the mapping retain their current net_class
> (typically the default 'Signal')."

That is the exact failure this spike targets: a mains-critical net silently
keeping the lowest-clearance default class, with the only trace being an
aggregate integer nobody compares against the mapping's own size.

## 2. Design: four candidates, evaluated

### Validated newtype -- rejected as insufficient on its own

`NetName(pub String)` already exists in `temper-drc-rs/src/board.rs`. It is
not a counterexample to the "leaky newtype" problem the brief names -- it
*is* the problem, live in the repo today: the field is `pub`, and
`impl From<&str> for NetName` has no constraint on the input, so
`NetName("literally anything".into())` compiles everywhere, including in
the exact production marshalling code
(`board_py_bridge.rs:454/478/500/697`, `drc_marshal.rs:925/950/963`) that
builds a `BoardState` from parsed KiCad data. The type communicates intent
("this string means a net name") but enforces nothing. A validated newtype
only earns its keep when its constructor is the *only* way to obtain one
(private field, no `From`) -- which is exactly what `ValidatedNetClassMap`
does below, but scoped to the mapping, not to every `NetName` in the
codebase (see the handle-type discussion for why that broader move is out
of scope here).

### Handle/index type (`NetId(u32)`) -- strongest guarantee, not worth the churn here

A `NetId(u32)` indexing a `BoardState`'s own net table makes "a net that
does not exist" doubly unrepresentable: not only can't you construct one
with a bad string, you can't even talk about a net without a `BoardState`
in scope to resolve it against (closing the "branded/phantom lifetime"
question the brief raises -- the natural implementation already threads a
`&BoardState` or a generation-tagged arena handle through every consumer,
so it is branded by construction, not as an afterthought).

Rejected for this repo, at this stage, on cost: Sec. 1 found 139
construction sites for `NetName`/`NetClassName` in `temper-drc-rs` alone,
the majority in test fixtures that deliberately construct out-of-band net
names to test orphan/mismatch detection. Every DRC rule signature
(`rules/erc/net_connectivity.rs`, `rules/drc/zone_containment.rs`, and the
~30 other rule modules under `rules/`) currently takes `&Net`/`&NetName` by
value or reference; switching to `NetId` means either (a) every rule now
also needs `&BoardState` in scope purely to resolve display strings for
violation messages, which it mostly does not need today, or (b) `NetId`
carries a denormalized display string alongside the index, which
re-introduces exactly the "string that might be stale" problem one layer
down. This is a real migration (plan-and-execute across a whole DRC
engine), explicitly out of scope per the brief ("do not attempt a
repo-wide migration").

### Typestate (`Config<Unvalidated>` / `Config<Validated>`) -- rejected as unneeded machinery

`DesignConstraints` (`_constraint_types/config.py`) has 30+ unrelated
fields (`fixed_components`, `layer_stackup`, `losses`, `seed_filter`, ...).
Phantom-typing the whole struct to gate on one field's validity would force
every one of that struct's ~40 other consumers to pick a type parameter
that means nothing to them. `Result<ValidatedNetClassMap, Vec<...>>`
already gets the identical guarantee -- a bad value cannot exist -- for the
one field that actually has the defect, without touching the other 39.
Typestate earns its cost when *most* of a type's behavior differs
before/after validation (e.g. a request object that can't be routed until
authenticated); here, exactly one field out of many is unsafe, so gating
the whole config type is the wrong-sized tool.

### Parse-don't-validate at the config boundary -- recommended

`ValidatedNetClassMap::resolve(known_nets: &BTreeSet<String>, raw:
&BTreeMap<String, String>) -> Result<Self, Vec<UnresolvedNetClassKey>>` is
the only constructor. This is the smallest change that converts the exact
failure mode observed (silent, partial, no error signal) into the exact
failure mode wanted (loud, total, one deterministic error listing every
broken key). It costs one module and one additive method (Sec. 3), it does
not require deciding how DRC rule signatures pass nets around, and it does
not require a phantom-typed config struct. It gets less unrepresentability
than a handle type (Sec. 4 is explicit about what it does *not* prevent),
but it is the only candidate whose cost is proportionate to what this spike
can actually finish and prove.

### Case sensitivity: strict, on safety grounds

Case-insensitive resolution would have silently "fixed" `AC_L` against the
real `ac_l` -- exactly the two keys from the real incident. That is the
convenience argument for normalizing, and it is real. It is rejected here
because normalizing does not distinguish "this is a deliberate alias" from
"this is a typo that happens to case-fold correctly today": `AC_L`/`ac_l`
folding cleanly is a coincidence of this one pair, not a property that
holds for every future net name on this board. A case-insensitive resolver
would also silently accept a *new* typo introduced later that happens to
differ only in case from a real net -- the exact failure class this spike
exists to close, reintroduced through the back door of "helpful"
normalization. Strict resolution instead forces every one of the 31 broken
keys to be looked at and either renamed to the real net (`AC_L` ->
`ac_l`, `+340V_BUS` -> `+170V_BUS`, both simple, safe, mechanical renames
per `elec/domain_manifest.yaml`'s own rename comment) or flagged as
needing real reconciliation (`CGND`/`VCC_BOOT`, which match no net in any
case-fold and need a documented decision, same as
`temper_constraints.references.yaml`'s `unresolved_components` pattern for
component refs). On a mains-voltage board, loud-and-requires-31-fixes is
the safer failure mode than quiet-and-fixes-2-of-31-by-coincidence.

## 3. Prototype: `Netlist.apply_net_class_mapping_strict`

Implemented on `spike/typed-net-refs`, at the exact seam identified in
Sec. 1 (`Netlist.apply_net_class_mapping`, `temper-design-bundle`'s
`netlist_contracts.rs`), as a new, additive method rather than a change to
the existing one. This is deliberate: `apply_net_class_mapping` is an
oracle-parity shim (module docstring: "must reproduce that implementation
bit-identically"; `test_netlist_rust_differential.py` pins it against
`_netlist_py_oracle.py`). Changing its silent-skip behavior would break a
verified parity contract that exists for an unrelated reason (safe
Python-to-Rust migration). The new method sits beside it, unchanged parity
tests still pass (73/73, see below).

**The type** (`packages/temper-design-bundle/src/net_class_validation.rs`,
new file, no `python` feature gate -- pure logic, unit-testable without
pyo3):

```rust
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct NetName(String);          // private field -- no public constructor

pub struct UnresolvedNetClassKey {
    pub raw_key: String,
    pub class_name: String,
}

#[derive(Debug, Clone, Default)]
pub struct ValidatedNetClassMap(BTreeMap<NetName, String>);

impl ValidatedNetClassMap {
    pub fn resolve(
        known_nets: &BTreeSet<String>,
        raw: &BTreeMap<String, String>,
    ) -> Result<Self, Vec<UnresolvedNetClassKey>> {
        let mut resolved = BTreeMap::new();
        let mut errors = Vec::new();
        for (key, class_name) in raw {
            if known_nets.contains(key) {
                resolved.insert(NetName(key.clone()), class_name.clone());
            } else {
                errors.push(UnresolvedNetClassKey { raw_key: key.clone(), class_name: class_name.clone() });
            }
        }
        if errors.is_empty() { Ok(Self(resolved)) } else { Err(errors) }
    }
    // .get(&str) -> Option<&str>, case-sensitive, via Borrow<str>
}
```

All-or-nothing (one bad key rejects the whole batch, proven by
`one_bad_key_rejects_the_whole_mapping_not_just_that_key`) and
every-error-not-just-the-first (proven by
`all_unresolved_keys_are_reported_not_just_the_first`) are both explicit,
tested properties -- not incidental.

**The pyo3-facing method** (`netlist_contracts.rs`, added beside the
existing `apply_net_class_mapping`):

```rust
fn apply_net_class_mapping_strict(&self, py: Python<'_>, mapping: &Bound<'_, PyAny>) -> PyResult<i64> {
    let mut known_nets = BTreeSet::new();
    for net in self.nets.bind(py).try_iter()? {
        known_nets.insert(net?.getattr("name")?.extract::<String>()?);
    }
    let raw: BTreeMap<String, String> = mapping.extract()?;
    let resolved = ValidatedNetClassMap::resolve(&known_nets, &raw)
        .map_err(|errors| PyValueError::new_err(format_unresolved(&errors)))?;
    // resolved is now known-good against THIS netlist's own names;
    // apply exactly like apply_net_class_mapping does for the matched subset.
    ...
}
```

**Rust unit tests** (`net_class_validation.rs`, default build, no `python`
feature needed):

```
$ cargo test --manifest-path packages/temper-design-bundle/Cargo.toml --lib net_class_validation
running 9 tests
test net_class_validation::tests::all_unresolved_keys_are_reported_not_just_the_first ... ok
test net_class_validation::tests::case_mismatch_is_a_hard_error_not_a_silent_fold ... ok
test net_class_validation::tests::empty_net_table_rejects_any_nonempty_mapping ... ok
test net_class_validation::tests::empty_mapping_is_trivially_valid ... ok
test net_class_validation::tests::exact_match_resolves ... ok
test net_class_validation::tests::format_unresolved_names_every_key ... ok
test net_class_validation::tests::one_bad_key_rejects_the_whole_mapping_not_just_that_key ... ok
test net_class_validation::tests::reproduces_the_real_defect_shape ... ok
test net_class_validation::tests::unknown_net_is_rejected ... ok

test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 24 filtered out; finished in 0.00s
```

Compiles clean (`cargo clippy --features python -- -D warnings`: 0
warnings) and the full existing oracle-parity suite is unaffected:

```
$ uv run --active --no-sync pytest packages/temper-placer/tests/core/test_netlist_rust_differential.py -q
73 passed in 0.19s
```

**Proof against the real repo, read-only** (`pcb/temper.kicad_pcb` +
`packages/temper-placer/configs/temper_constraints.yaml`, neither modified
-- both are in this task's do-not-touch list). This is the actual current
state of `origin/main`, not a reconstruction:

```
$ uv run --active --no-sync python -c "
import yaml
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb
parse_result = parse_kicad_pcb(Path('pcb/temper.kicad_pcb'))
net_classes = yaml.safe_load(Path('packages/temper-placer/configs/temper_constraints.yaml').read_text())['net_classes']
parse_result.netlist.apply_net_class_mapping_strict(net_classes)
"
Traceback (most recent call last):
  ...
ValueError: 5 net_classes key(s) do not match any real net on this Netlist (case-sensitive exact match) -- each assignment would otherwise be a silent no-op:
  net_classes["+340V_BUS"] = "HighVoltage" -- "+340V_BUS" is not a real net name
  net_classes["AC_L"] = "ACMains" -- "AC_L" is not a real net name
  net_classes["AC_N"] = "ACMains" -- "AC_N" is not a real net name
  net_classes["GND"] = "Ground" -- "GND" is not a real net name
  net_classes["PE"] = "ACMains" -- "PE" is not a real net name
```

Same real inputs through the existing, untouched `apply_net_class_mapping`:
6 of 11 keys silently applied, 5 silently skipped, no exception, no
warning -- `updated=6` is the only signal that ever reaches the caller, and
`run_feedback_loop.py` never compares it against `len(net_class_mapping)`.
(This measured count -- 5 of 11 broken in `temper_constraints.yaml` -- is
one more than the correspondence-gate doc's prose table states, because
that table's "4 of 11" underlists `GND`; the gate script's own violation
list, which this doc's Sec. 1 independently reproduces, does report all 5.
Not a discrepancy in the gate's logic, just its summary table.)

This is pinned as a durable, reviewable test, not just a one-off script:
`packages/temper-placer/tests/core/test_apply_net_class_mapping_strict.py`
(10 tests: 8 synthetic contract tests + 2 real-repo integration tests
mirroring `TestRealRepoIntegration` in the correspondence-gate test suites).
All pass:

```
$ uv run --active --no-sync pytest packages/temper-placer/tests/core/test_apply_net_class_mapping_strict.py -q
10 passed in 0.16s
```

## 4. The pyo3 boundary, honestly

**The guarantee holds for the duration of one call and no longer.** It is
not decorative -- inside `apply_net_class_mapping_strict`, a
`ValidatedNetClassMap` genuinely cannot be constructed with an unresolved
key, and that check runs against real data every time the method is
called. But nothing about a `Result<ValidatedNetClassMap, _>` succeeding
inside Rust prevents Python from later invalidating the premise it was
checked against. Demonstrated directly against the built extension:

```python
>>> n1 = rs.Net(name='ac_l', pins=[])
>>> nl = rs.Netlist(components=[], nets=[n1])
>>> nl.apply_net_class_mapping_strict({'ac_l': 'ACMains'})   # validates, applies
1
>>> n1.name = 'totally not a net'      # Net.name is #[pyo3(get, set)] on Py<PyAny> -- no validation
>>> nl.apply_net_class_mapping_strict({'totally not a net': 'HighVoltage'})  # "validates" fine now
1
```

`Net.name` is `#[pyo3(get, set)]` on an opaque `Py<PyAny>` field (by
design -- see `netlist_contracts.rs`'s module docstring on why every field
is opaque: byte-identical dataclass semantics with the Python oracle,
including untyped attribute assignment). `ValidatedNetClassMap::resolve`
checks the mapping's keys against the *Netlist's own current net names*,
not against the board's real net table directly -- those are the same set
only because, in the one production call site this spike targets
(`run_feedback_loop.py`, right after `parse_kicad_pcb`), nothing has
touched `net.name` between parsing and this call. That is a call-discipline
argument, not a type-level one. **The type prevents the exact defect
observed** (a `net_classes:` key that doesn't match the netlist being
silently ignored); **it does not and cannot prevent** a Python caller from
first corrupting the netlist's own net names and then validating against
the corruption. Closing that would require the handle-type approach from
Sec. 2 (a `NetId` that can only be obtained from an immutable board/netlist
snapshot, with no Python-visible setter) -- exactly the migration this
spike found too large to attempt.

**What crosses back to Python is a plain `dict`-shaped mutation, not a
typed object.** `resolved` (the `ValidatedNetClassMap`) never itself
crosses into Python; only its effect does (`net.setattr("net_class",
...)`). Python receives no `ValidatedNetClassMap` handle it could misuse
later -- there is nothing on the Python side claiming to still be
"validated" after the call returns. This is actually the safer shape for a
pyo3 boundary: the type's lifetime is scoped to the single Rust call frame,
so there is no persisted Python-side object whose "already validated"
status could go stale and be trusted anyway. The cost is that every call
site has to go through `apply_net_class_mapping_strict` itself to get the
guarantee -- there is no way to validate once and carry a proof-token
across multiple Python calls, because pyo3 cannot express "this token
proves `resolve` already ran" as anything Python code could not fabricate.

**Net conclusion**: the invariant is preserved *at the one call this spike
wires up*, for as long as Python does not deliberately reach past it by
mutating `.name` afterward (which no production code path does today --
`net.name` is set once, at `parse_kicad_pcb` time, and never reassigned).
It is not preserved as a standing property of the `Netlist`/`Net` Python
objects themselves, because those remain exactly as dynamically typed as
before. Saying otherwise would overstate what this prototype proves.

## 5. Cost of the rest, and relation to the correspondence gates

**Highest-leverage next step, not this spike's prototype target:**
`board_py_bridge.rs::build_board_state` and `drc_marshal.rs`'s
"Unknown"-class defaulting (Sec. 1). Each site is ~15-20 lines and already
has `NetName`/`NetClassName`/`NetClassRules` types in scope; a
`ValidatedNetClassMap`-shaped fix (a net with no matching class is a hard
error, not a silent `"Unknown"`/0.2 mm default) is a close structural
cousin of this spike's prototype. It was not chosen as the prototype
target itself because it is a **behavior change to the CI-gating DRC
path** -- unlike the config-key miss (an occasionally-run script silently
doing less than intended), flipping this to fail-closed changes what
`run_drc` returns on every call today, which needs its own
advisory-vs-blocking decision, exactly like the three correspondence
gates already landed advisory for analogous reasons. Fixing it also
requires first knowing how many real nets on the current board fall
through to `"Unknown"` today -- not measured in this spike, since it
would require running the full DRC marshalling path against production
inputs, which the four-config-file boundary and this spike's one-path
scope both argue against attempting here.

**Wiring the other 3 broken config files' real call sites** (not done in
this spike -- the four config files are explicitly out of bounds, and two
of the three other call sites currently succeed by accident of the same
silent-skip bug this spike is about, so making them fail loudly today
would break `run_feedback_loop.py` and `load_constraints`' current
callers against still-broken data):

| File | Real call site | Cost to wire `apply_net_class_mapping_strict` (or equivalent) |
|---|---|---|
| `configs/temper_deterministic_config.yaml` | `scripts/run_feedback_loop.py:212`, same `Netlist.apply_net_class_mapping` call already traced in Sec. 1 | **Near zero, mechanically** -- swap the method name at one call site. Not done here because the file has 21 of 25 broken keys (per the correspondence-gate survey); wiring it in today would make `run_feedback_loop.py` hard-fail immediately, which is a behavior change to a script outside this spike's boundary. |
| `packages/temper-placer/configs/gate_driver_constraints.yaml` | "same family" per the correspondence-gate doc -- loaded through the same `load_constraints`/`net_classes` path, applied via a different call site than `run_feedback_loop.py` (not traced in this spike; out of scope) | Needs its actual call site traced first; likely comparable cost once found, since it flows through the same `DesignConstraints.net_classes` field. |
| `configs/temper_production_config.yaml` | None -- "not loaded by any code path today" (correspondence-gate doc) | Zero production cost; nothing to wire until something loads it. |

None of these were touched, per the task's explicit boundary (the four
config files with broken keys are off-limits) and per the spike's own
"prototype ONE path" instruction.

**Relation to `check_netclass_map_board_correspondence.py` (merged
2026-08-11) and `check_pcl_config_board_correspondence.py`**: these are
complementary, not redundant, exactly as the correspondence-gates doc's
closing section argues. The gate is a **CI-time, data-level** check: it
parses the *current* YAML files and the *current* board and reports drift
whenever they disagree, without touching or constraining any code path.
`ValidatedNetClassMap` is a **compile-time, code-level** guarantee: no
future Rust code that goes through `apply_net_class_mapping_strict` can
apply an unresolved key, ever, regardless of what any config file
currently contains.

Concretely, of the 31 broken keys the gate finds today, this type would
have prevented **zero of them from being written** (they are YAML data,
not code -- a type constrains what code can construct, not what a human
types into a config file) but would have caught **all 31 the first time
any of them was actually applied** through a strict call site, at the
exact moment of the silent no-op, rather than requiring a separate CI gate
to notice the data drift independently. The two are doing different jobs:
the gate catches "this config file and this board have drifted apart" as a
static fact, checkable with no pipeline run at all; the type catches "this
specific application of a mapping to a specific netlist has an unresolved
key," checkable only by actually running the code path, but with the
advantage that it cannot be silently skipped, forgotten, or
`continue-on-error`'d away the way an advisory gate currently is (all
three correspondence gates are landed advisory today, for the same reason
this spike doesn't hard-wire strict validation into the broken files'
call sites: the fix for the 31 keys is a human/domain reconciliation,
not a mechanical one).

## 6. Was this worth it?

**Yes, at the scope actually costed here -- one call site, additive, fully
tested -- and no further, for now.** The prototype is real, proven against
real repo data, and costs about 200 lines total across two crates plus
tests. It should be adopted as an available, opt-in strict alternative at
the specific call site it targets once `temper_deterministic_config.yaml`'s
21 broken keys are fixed (tracked by the existing correspondence gate).

Generalizing further -- to a handle-based `NetId` covering the DRC engine,
or to every one of the ~140 `NetName`/`ComponentRef` construction sites
found in Sec. 1 -- is **not** recommended at this repo's current stage. The
survey found the blast radius large and structurally split between
production marshalling (worth fixing, small) and deliberate test fixtures
(not a bug, would need special-casing under any handle scheme). The
correspondence gates already catch the data-level version of this defect
across all four files today, landed and running, at a small fraction of
the engineering cost a repo-wide type migration would take. Reconciling
the 31 keys those gates flag -- a domain decision, not a type-system one
-- delivers more safety per unit of effort than continuing this migration
would, for the foreseeable future.
