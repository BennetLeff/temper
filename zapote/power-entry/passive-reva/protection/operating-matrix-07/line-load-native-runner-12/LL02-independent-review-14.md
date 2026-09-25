# LL02 independent case review

This is a read-only review of the completed
`full-LL02-initialized/LL02` artifacts against `event-aware-normal-v1` and
`accepted-baseline-11`.  It is not an acceptance receipt; the case remains
`complete_review_pending` until the parent binds the raw/source hashes and
records a disposition.

## Capture and event audit

LL02 is the 108.000000 VAC RMS case with `RLOAD=208.230244479 ohm`.  The
materialized case binds source deck SHA-256
`db9d544938b792aac009c1ee4fcf27f52a8283beb167e40262d495d4c098ac94`, generated
deck SHA-256 `664cf804ea82c0554c1e58cc69e23a4a881c533f46718d83f831bb87c6dadc2a`,
and the recorded include-set digest.  Capture metadata reports native
little-endian `normal15`, both vector masks 65535, 29,682,485 points, endpoint
`0.650000000000000022 s`, zero backwards rows, and 80 equal-time repeats.  It
is intentionally diagnostic (`first_invalid=true`, `accepted=false`,
`continue_after_duplicate=true`).

`raw15-event-audit.txt` exits zero: 55 equal-time groups, maximum group size
3, no missing right context, no logic-column changes, no boundary groups, and
largest positive gap `5.000000000143778e-7 s` (below the
`9.615384615e-7 s` ceiling).  E3 same-time diagnostics are finite and small:
spread `3.402977198174138955e-13 J`, sum-absolute
`5.953503755320004204e-12 J`.  The rows were retained; no timestamp rewrite
or deduplication is indicated.

## Electrical metrics and margins

The event-aware metrics pipeline exits zero and reports no derived screen
violations:

| quantity | LL02 result | frozen screen / review |
| --- | ---: | --- |
| settled line RMS | 108.000000 V | 108--132 V; exactly lower endpoint |
| settled input RMS | 7.509729 A | <=15 A |
| real input/load power | 802.223598 / 705.399729 W | positive load and input power |
| PF | 0.989116 | finite, in range |
| settled VB envelope | 381.307658..385.188525 V | 370.134..409.096 V |
| three cycle means | 382.7540017, 383.2968601, 383.7974188 V | chronological |
| cycle drift | 0.002726 | <0.005 |
| complete-prefix VD peak | 385.299212 V | <500 V |
| complete-prefix VB peak | 385.188525 V | <450 V |
| complete-prefix VDS peak | 386.595233 V | <650 V |
| complete-prefix \|VGS\| peak | 14.982208 V | <25 V |
| armed/on fractions | 1.000000 / 1.000000 | >=0.99 |
| storage delta rate | 26.916854819 W | diagnostic |
| Pin-Pout-dE/dt | +69.907013879 W | only negative values beyond tolerance stop |

The complete-prefix inductor-current peak is 25.777695 A.  The maintained
checker has no automatic inductor-current rating screen, so this is a reported
device-stress value for the parent/model review, not an implied PASS or a
hardware current qualification.

## Pipeline interpretation and blockers

The unchanged strict checker exits 1 at `line 22417826` with
`time not strictly increasing`; its decoder/normalizer also exit 1 and the
gzip child is `-1`.  This is the expected strict-checker branch for the
versioned event-aware policy: equal binary64 times are retained and accepted
for diagnostic metrics only when the event audit proves no backwards time,
context loss, or logic change.  It would be a blocker if the parent elects the
legacy strictly-increasing checker as the acceptance policy; it is not a new
electrical screen failure under `event-aware-normal-v1`.  The event-audit and
metrics decoder/normalizer/gzip pipelines all exit zero.

The case is therefore numerically within the modeled normal screens and has a
complete event audit, but cannot be promoted automatically.  Parent still
needs to verify the raw compressed digest, runner/binary/source identities,
all child statuses, and the five staged include hashes against the baseline.
`diagnostic_only=true`, `accepted=false`, and `result.status=
complete_review_pending` remain authoritative.  The positive 69.9 W residual
is modeled accounting rather than heat closure; no thermal, SOA, fuse,
hardware, or product-compliance claim follows from LL02.
