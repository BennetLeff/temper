# P1 rail-order fixture: digital construction receipt

Date: 2026-09-23. Scope: **LAB ONLY**, standalone mains-disconnected driver-stage coupon, isolated current-limited low-voltage supplies. No powered Rev38 mating or AC, VD, VB, PFC-power test occurred. This receipt accepts fixture connectivity and the executable event checklist only. It does not accept physical gate shutdown, rail source adequacy, insulation, or an orderable fixture.

## Frozen inputs

The Rev38 `zapote/power-entry/passive-reva/protection/interface-integration-38/elec/src/driver_stage.ato` at commit `8b26664fec4d5acf00e56b8125b01bcb0bc18795` hashes to SHA-256 `a5896531ef006dfa390b9fdee7ad6a681f87a8105c15f627911d24c39c5b741c`. The same commit's `gate-enable-corners.md` hashes to `ed5981a83a24bc1d468c6402dd1fb05a74eccc160fd6c7dcc1effe058c5b8305`. Those bytes define signal names and proposed observation thresholds. They do not establish hardware behavior.

Fixture inputs in this worktree and the exact files copied to `/tmp/temper-rail-fixture` both hash to:

| Input | SHA-256 |
| --- | --- |
| `rail-order-fixture-01/ato.yaml` | `b90445a5b640bbfa57acb1a7c6d23c761e2f387ad286eb62d2b5e3f600ba99a4` |
| `rail-order-fixture-01/elec/src/rail_order_fixture.ato` | `8eb6791f8111d7fa7e59e42edbf43fb6d434922ad0fd1e90e43c997098db064d` |

The raw netlist hash is **scratch-path dependent**: a second build from byte-identical source under `/private/tmp/temper-rail-fixture-parent` produced `90353f81116e5d39f1b893f1831b7972656f7de089ae2e73f875d1bdd14ac1fe` because Atopile embeds the absolute scratch path in each `sheetpath`. Diffing the two netlists showed only those path strings changing. The source SHA pair and the exact generated node-map audit, rather than a raw hash across different scratch paths, are the portable identity checks.

The source-copy equality was checked with `shasum -a 256` on both pairs before the build. The generated `/tmp/temper-rail-fixture/build/default.net` SHA-256 was `987d71d4bed96f580823d9e81c38bcf7e0f947d2090ec3f6d9bf48db78840df2` on two successive Atopile 0.2.69 builds. The build used a cached local Atopile environment because `ato` in this shell is a broken symlink; no network install was required. It completed with generic component **No MPN** warnings. These headers and test points remain digital candidates, not a procurement BOM or reviewed physical interface.

## Replay

From the Zapote parallel worktree root:

```sh
fixture=zapote/auxiliary/rail-order-fixture-01
scratch=/tmp/temper-rail-fixture
mkdir -p "$scratch/elec/src"
cp "$fixture/ato.yaml" "$scratch/ato.yaml"
cp "$fixture/elec/src/rail_order_fixture.ato" "$scratch/elec/src/rail_order_fixture.ato"
cmp "$fixture/ato.yaml" "$scratch/ato.yaml"
cmp "$fixture/elec/src/rail_order_fixture.ato" "$scratch/elec/src/rail_order_fixture.ato"
(
  cd "$scratch"
  PYTHONPATH="$(find /Users/bennet/.cache/uv/archive-v0 -mindepth 1 -maxdepth 1 -type d -print | paste -sd ':' -)" \
  PYTHONDONTWRITEBYTECODE=1 \
  /Users/bennet/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/bin/python3.11 \
  -m atopile.cli.cli build
)
rustfmt --check zapote/auxiliary/evidence/rail-order-audit.rs
rustc --edition=2021 --test zapote/auxiliary/evidence/rail-order-audit.rs -o /tmp/rail-order-audit-tests
/tmp/rail-order-audit-tests
rustc --edition=2021 zapote/auxiliary/evidence/rail-order-audit.rs -o /tmp/rail-order-audit
/tmp/rail-order-audit "$scratch/build/default.net" zapote/auxiliary/evidence/rail-order-cases.tsv
```

The `/tmp` copy also keeps generated Atopile output out of the shared worktree. A normal Atopile 0.2.69 installation can build from the fixture directory directly. The audit consumes the **generated** netlist and checks an exact 13-component, 10-net node map: two separate supply positives, a shared HOT0, seven independent observation lines, and no SELV return or extra power feed. Tests deliberately mutate the AUX/logic tie, return separation, probe feed, missing ENA observation, extra component, fault-masked ENA, recovery-as-ARM, event order, and two otherwise valid rows that weaken or prematurely grant gate eligibility. Result: **11 passed; 0 failed**. Actual generated netlist plus matrix: **PASS**, with analog status **INDETERMINATE**.

The matrix's ordered `events` traces and `ena_requirement`/`gate_requirement` columns are a laboratory capture protocol. `capture_required` means the physical waveform has not been measured. In particular, ENA off at or below 0.8 V and eligible at or above 2.3 V are criteria to check against the reviewed Rev38 corner source; the passive fixture cannot make them true. `reject_if_observed` on the injected ENA-high case is a rejection criterion, not a successful fault result.

## Remaining gate

A reviewed, exact native pad map and safe coupon/instrument connection are required before a physical build or any powered observation. A live Rev38 hookup requires a separate isolation and operator-protection review. Actual partial-rail, hiccup, loss, discharge and deliberate re-arm waveforms must be captured against the thresholds and time limits in the frozen source; the Rev38 source may change after this pin. Complete dynamic loads and fault waveforms remain required before selecting a HOT rail producer or protected AUX implementation.
