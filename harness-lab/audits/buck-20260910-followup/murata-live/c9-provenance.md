# C9 exact MPN provenance audit

Audit checkout: `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`.
Base `a75ca538d87d6578917d0cb3a50da7f14ebdc210` was verified before reading.
This is read-only; no BOM, source, registry, or repository file was changed.

## What history proves

`git log --all -S'GRM32ER71E106KA12L'` identifies the first source introduction
as commit `ded9c25422283979f759be82ea1ecb59af69c52b` (2026-07-15,
`fix(elec): resolve 8 P0/P1 electrical design bugs from atopile audit`). That
commit replaced the former XC6220-based 3V3 path with `BuckConverter3V3` and
introduced `c_in.mpn = "GRM32ER71E106KA12L"`, together with the 10 uF +/-20%,
X7R, 25 V declaration and 1210 footprint. The commit message and diff explain
the topology replacement and the prior design bug; they contain no Murata
approval sheet, manufacturer URL, search result, or curve proving the exact
`GRM32ER...` orderable.

The parent source had a separate `BuckConverter15V` using
`GRM32ER71H106KA12L` (H rather than E) for a 10 uF/50 V input capacitor. It did
not contain the new 3V3 C9 identity. This establishes the C9 E-code as part of
the July 15 buck redesign, but does not establish why the E thickness code was
selected or that the exact part was procurable.

The identity was then propagated without new exact-part proof:

- `26a0462987ce7ca29d03b0d822d1e696e2e7b7f1` (2026-07-26) copied the MPN into
  the reconciled `docs/hardware/BOM.md` row (`C_IN`, 10 uF 20% X7R 25 V).
- `e08c4ef390ee1aa47d9a61ed56dbe85358e3623a` (2026-08-07) added the C9 entry
  to `scripts/part_stress_limits.yaml`; its source is only the Atopile MPN and
  rail declaration (`modules.ato:1474-1479` in the then-current source), not a
  manufacturer document.
- `ce344553c3d4aface00a554c99e78a0ccd9fd8f1` (2026-09-09) added the exact
  string to `harness-lab/engineering/circuit-contract.json`; the contract
  records source topology identity, not independent procurement evidence.
- The generated/retained harness netlist and export repeat the same string,
  proving propagation through Atopile compilation, not part existence.

## Vendor evidence found or absent

No retained repository source proves C9 `GRM32ER71E106KA12L` exists as an exact
Murata orderable. `harness-lab/audits/buck-20260909/sources/README.md:3-14`
retains only TI and Bourns PDFs plus a Murata C11/C12 product link. The existing
requirements audit explicitly says the exact C9 manufacturer page/specification
was not recovered and warns that a similarly named `GRM32D...` part is not
evidence (`harness-lab/audits/buck-20260909/requirements-components.md:78-82`).
The current C9 search endpoint
`https://www.murata.com/en-global/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71E106KA12%23`
returned a Murata HTML product-page response during the follow-up retrieval,
not a C9 PDF or approval sheet. Live SimSurfing reports zero exact C9 matches,
while its official model/listing surface contains the D-code sibling
`GRM32DR71E106KA12`; that sibling must not be silently substituted for the
source E-code.

The exact C9 string also appears in historical ERC reports, BOM and stress
documents, but those are downstream copies. No commit in the reachable history
adds a C9-specific Murata PDF, approval sheet, SimSurfing curve export, or
manufacturer confirmation. `GRM32ER71E106KA12L` is therefore an inherited,
unverified identity in the current source/contract, not a vendor-qualified
component claim.

## Consequences

The current source declarations (10 uF, +/-20%, 25 V, X7R) may continue to
describe the design candidate, but they should not be represented as exact
manufacturer-verified C9 specifications. In particular, do not infer that the
D-code 10 uF/25 V X7R listing is equivalent: the E/D code difference is exactly
the unresolved identity question. The existing required
`capacitor_effective_capacitance_dc_bias` evidence remains open.

The next evidence step is an exact-part Murata approval sheet or manufacturer
confirmation for `GRM32ER71E106KA12L`, including its orderable status, package
suffix L, tolerance, rated voltage, dielectric and DC-bias/temperature/aging
curves. Retain the original bytes, revision/date and SHA-256. If Murata confirms
no exact E-code part, record that falsifier and make any replacement a separate
user-approved BOM decision; this audit does not choose one.

## Source pointers

- Introducing commit: `ded9c25422283979f759be82ea1ecb59af69c52b`
- BOM propagation: `26a0462987ce7ca29d03b0d822d1e696e2e7b7f1`
- Stress-limit propagation: `e08c4ef390ee1aa47d9a61ed56dbe85358e3623a`
- Harness contract propagation: `ce344553c3d4aface00a554c99e78a0ccd9fd8f1`
- Current Atopile declaration: `elec/src/modules.ato:1444-1451`
- Current contract: `harness-lab/engineering/circuit-contract.json:6`
- Existing evidence limitation: `harness-lab/audits/buck-20260909/requirements-components.md:78-82`
- Exact C9 Murata endpoint: https://www.murata.com/en-global/api/pdfdownloadapi?cate=luCeramicCapacitorsSMD&partno=GRM32ER71E106KA12L%23
