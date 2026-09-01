# R14/high-voltage refloorplan: stopped-indeterminate receipt

## Verdict

The declared first family was exhausted reproducibly, but this run is
**stopped-indeterminate**, not a negative topology certificate and not a board
promotion.

All 240 declared candidates were materialized and measured. Every candidate
cleared the 13.1 mm K1-J1 target, with measured gaps from
13.304745870407777 mm through 13.77882654659717 mm. None cleared the complete
pre-route contract:

- the shape-aware `discharge.r_snub1-p2` net-41 copper to SELV pad-copper
  minimum was
  9.55333347008141..11.545158055694412 mm against 12.6 mm;
- J1 pad 1 to declared net-41 segment 6 was the closest route relationship in
  all 240 candidates;
- all 240 candidates introduced or worsened affected safety signatures; and
- 60 candidates also introduced a courtyard overlap.

There was no routing stage because the pre-route survivor set was empty.

## Why the family did not expand

The plan permits one second family only when the complete first family proves
one canonical *fixed-object* veto. That condition was not met. The common
route clearance veto is between already-movable J1 and the already-declared
net-41 route chain, while the affected safety failures contain several
distinct relationships. Expanding another object would therefore be a new
design hypothesis rather than an evidence-authorized continuation.

## Why this is not a negative certificate

Two required measurement conditions remain unresolved:

1. The pinned pad-position oracle passed all 10 registered sites across 16
   probes, but `--verify-live-oracle` could not find a Python interpreter with
   pcbnew bindings. The run cannot claim that the live external oracle was
   checked.
2. Three clean baseline DRC runs were stable at 406 errors and 402 warnings,
   but `silk_overlap` was exactly 199 in every run. Repository policy treats
   199/499 as a kicad-cli cap, not an authoritative count.

Neither limitation makes the candidate geometry pass, and neither authorizes
scope expansion. They do prevent this run from promoting its bounded rejection
into a stronger topology-negative claim.

## Production state

No production artifact changed:

| Authority | SHA-256 |
|---|---|
| `pcb/temper.kicad_pcb` | `00a27419b82101e3518ddbf9d174f8359d76940c495ca1e5bd3d9cc32d7ac4d9` |
| production J1 library footprint | `aa0df7dde7a78aa2ea851aa9998f6806b92eb8a117d0dd73f6862ee444c784b8` |
| `power_pcb_dataset/drc_ceiling.json` | `c6b2198e62ca5b15878884b1e2822a8b3bbd7372ace8f6198aeccffe83189fb2` |

The approved predecessor J1 geometry is preserved as
`approved-j1-footprint.kicad_mod`, with the board-ready block in
`approved-j1-board-footprint.kicad_sexpr`. The active builder is Rust-owned;
the predecessor Python builder remains only as a differential oracle.

## Reproduction

From the repository root with current pyo3 extensions installed:

```bash
make netlist
.venv/bin/python scripts/generate_kicad_dru.py
env -u CONDA_PREFIX make extensions-check
.venv/bin/python scripts/check_pad_world_position_oracle.py
.venv/bin/python docs/evidence/r14-hv-domain-refloorplan-20260831/run_campaign.py --replay
```

The replay must end with:

```text
REPLAY PASS 99d444bf75797b4b82e91549e9ae0d0f0d8dddb198fa8c2bfc967b6563665325
```

The replay content-binds the generated netlist, generated DRU, and domain
manifest. It also derives and compares `terminal-receipt.json`, so a stale or
edited concise verdict fails replay even when the full manifest is unchanged.

## Next bounded design decision

The evidence says that another small R14 east shift is not the next move. The
next design step needs a new declared topology that creates more separation
between J1 pad 1 and the high-voltage route itself—most plausibly an
enclosure-authorized J1 relocation/access change, a layer/corridor redesign
that moves net 41 away from the connector, or an isolation-slot concept with
manufacturing authority. That work must start with a new declaration; it is
not an implicit expansion of this campaign.
