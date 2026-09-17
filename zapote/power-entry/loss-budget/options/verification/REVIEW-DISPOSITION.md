# Review disposition

The coordinator used four explicitly requested Luna workers, then separate Luna
contexts for source-code and component-evidence reviews. The raw initial and
final receipts are retained here. These are native reviews from the same model
family, not cross-model validation or laboratory qualification.

Code review: harness-native fallback — the earlier CE review in this continuing
loss-model work ended degraded without a usable independent result; the current
diff has completed native Luna reviews and coordinator verification instead.
No completed formal CE receipt is claimed for this diff.

## Accepted and fixed

- Non-finite actual/expected values could bypass tolerance checks. The adapter
  now rejects them, including a mutated non-nominal scenario.
- Scenario metadata and production bus/frequency/model constants were not bound
  to the intended configuration. Checks now compare them with source-derived
  values and fixed assumptions; regressions regenerate internally consistent
  results using deliberately wrong bus, frequency and Qgd. The unmodified
  control must pass using exact report values, not rounded prose values.
- A generic `Measured` label could masquerade as evidence. Both quantities and
  evidence records reject it while this adapter lacks a verified importer.
- Reference labels and quantity conditions did not identify the actual fixture.
  They now name its pinned bytes and 400 V / 10 A / 20 ns + 30 ns conditions.
- A datasheet download was an access-denied HTML page with a valid digest.
  Replaced it with a parsed LCSC-hosted onsemi PDF; the production document gate
  also rejects correctly hashed non-PDF bytes. This is file-type validation,
  not semantic validation of a datasheet.
- TI driver revision/path, a 15 V test point mislabeled as a recommendation,
  a copied turn-off-current expression, and RMS current proposed for a switching
  test were corrected. The option arithmetic is reproduced independently here.
- Simplification removed dead physical/qualification PASS rationale branches.
  Only the worker's owned code was integrated; unrelated formatting was omitted.

## Rejected or bounded observations

The initial code reviewer proposed making numerical verification indeterminate
whenever a physical assumption remained. Rejected: the explicit contract has
three dimensions so that correct conditional arithmetic can pass without
physical applicability or qualification passing. Both latter dimensions remain
INDETERMINATE by construction for structurally valid inputs. Corruption fails.

The review also mentioned unchanged bridge-thermal findings. They assess
different retained evidence under existing scope; this change does not alter
them or use them to qualify the MOSFET or installed cooling.

The fixed analytical reference is one independent expected result, not a
complete independent simulator. Source pins and regressions prevent the named
recurrences; they cannot establish all semiconductor physics or prevent every
future error. Candidate source conditions, driver uncertainty, missing loss
terms and hardware qualification remain explicit in the option reports.

No PCB, authored circuit, BOM selection, fabrication output or hardware state
changed. No additional deployed-service monitoring applies. Future acceptance
must continue to show the applicability and qualification findings explicitly;
an unexpected PASS without a reviewed evidence importer is a regression.
