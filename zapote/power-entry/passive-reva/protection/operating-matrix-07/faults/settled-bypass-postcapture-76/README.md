# BYPASS-NEG bounded post-capture packet

Mechanical derivative of parent-reviewed postcapture-69 (`run.sh` base
SHA-256 `6d697294d4aa710c1b7cb87f20fc54a81af7f59fa745b6dc072a3e7091d88a73`).
Only case/source/output roots, BYPASS-NEG manifest/case hashes, runner
`bypass-neg`, validator `f2-open`, and the existing `bypass: true` parameter
literal were substituted. The complete-capture/export/raw-hash gates, 10 GiB
floor, five bounded passes, observation stream, exact selector endpoint, and
crest phase interval are unchanged.

This is a frozen negative control: F2 is commanded open and the checker’s
bypass rejection is expected. It can never be a protection PASS. Any missing
detector/latch waveform witness remains separately labelled diagnostic data.
The separate `legacy-strict.sh` records the strict timestamp-checker result after the full diagnostic packet completes; it has not run.

