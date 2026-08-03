# ci-corpus — the executable incident record

Every past incident is re-encoded as a **committed seed artifact** plus the
gate that must reject it (Phase 1, `incidents.yaml`), and every CI gate in the
inventory carries a **demonstrated failing case** — a canary seed it must
reject (Phase 2, `canaries.yaml`). One shared runner,
`scripts/check_incident_corpus.py`, executes both phases over this directory
and the same verdict classes. See
`docs/plans/2026-08-02-032-feat-incident-corpus-oracle-plan.md` (R19 + R30).

## Running the corpus

```bash
uv run python scripts/check_incident_corpus.py --manifest ci-corpus/incidents.yaml   # Phase 1
uv run python scripts/check_incident_corpus.py --manifest ci-corpus/canaries.yaml    # Phase 2
```

Exit 0 = every entry demonstrated its contract (Phase 1 also accepts declared
UNVERIFIED entries with a recorded reason); exit 1 = any FAIL, any coverage
violation, a computed UNVERIFIED (broken fixture), or an empty corpus / empty
canary set. Both phases run in CI (python-tests.yml, consistency-gates job)
and **never** carry `continue-on-error`.

## Layout

```
ci-corpus/
  incidents.yaml        Phase 1 manifest (the history tranche)
  canaries.yaml         Phase 2 registry (the totality contract)
  board/                board-class seeds (.kicad_pcb / board+netlist pairs)
  constraint/           constraint/geometry-class seeds (.py defect shapes, .ato)
  workflow/             workflow-class seeds (directory trees of .yml)
  test/                 test-class seeds (.py fixtures, evidence docs, registries)
```

Seeds are intentionally-invalid artifacts. They live under `ci-corpus/`
precisely so normal tooling never picks them up (KTD3) — no gate scans this
directory.

## Manifest schema

Both manifests share one entry shape (KTD5). Phase 1 keys on `id`, Phase 2
keys on `gate` (which must equal the normalized `scripts/manifest.yaml`
ci-gate path). Common fields:

| field | meaning |
|---|---|
| `seed` | repo-relative path to the seed artifact (file, or a directory tree when `layout: directory`) |
| `pristine` | the passing counterpart, or the literal `pending` for still-unfixed defects (KTD8) |
| `pristine_pending_reason` | required when `pristine: pending` |
| `layout: directory` | directory-scanning gate (KTD7): seed/pristine are trees materialized to a temp dir per run; a single-file seed cannot flip a directory scanner |
| `gate` | the script that must reject the seed |
| `flags` | invocation flags; `{seed}`/`{pristine}` substitute with the side being run (KTD4: same script, same flags, external process, exit-code verdict) |
| `seed_exit_codes` | the gate's rejection exit code(s) on the seed — any other non-zero seed exit is a **gate error**, reported UNVERIFIED, never mistaken for a rejection |
| `evidence` | the evidence doc recording the incident |
| `status` | Phase 2: `fail-closed` or `advisory` (from the workflow's `continue-on-error` state, KTD11) |
| `status: unverified` + `reason` | the gate cannot be driven against an external seed today — registered, never dropped (KTD8) |

## Adding an incident (Phase 1)

1. Commit the seed artifact + its pristine counterpart under the right class
   directory (or register the seed with `pristine: pending` + a reason if the
   defect is still on main).
2. Add one entry to `incidents.yaml` with a unique `id`.
3. Run the Phase 1 corpus; the entry must report PASS or declared-UNVERIFIED.
4. Spot-check the falsifier: temporarily point the entry's pristine at its
   seed — the run must flip exactly that incident to FAIL (over-broad) — or
   the seed at its pristine — it must flip to FAIL (regression).

## Adding a gate canary (Phase 2)

A new `disposition: ci-gate` script in `scripts/manifest.yaml` fails the
Phase 2 coverage check until it appears in `canaries.yaml` — the canary must
land in the same change that wires the gate (KTD10). Prefer reusing a Phase 1
incident seed (reference it by path — never duplicate it); otherwise commit a
minimal seed from the gate's documented defect class and the passing pristine.
A gate that cannot yet be driven against an external seed gets a `kind:
triage` entry recording why (the coverage gap is named, never silent).

## Retiring a seed

When a gate legitimately stops rejecting a registered seed — a fix makes the
defect class impossible, or the gate's scope legitimately narrows — the entry
is retired with a recorded `retired_reason`, never silently removed (KTD9, the
same declared-equivalent-with-justification discipline R42 uses). A retired
entry drops out of the liveness denominator without failing the run; deleting
the entry without a recorded reason fails the coverage check.
