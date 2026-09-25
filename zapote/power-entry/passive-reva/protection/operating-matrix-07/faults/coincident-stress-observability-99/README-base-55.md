# Post-injection observations for BYPASS-NEG

This small diagnostic fills the detector-independent observation gap described
in remaining-readiness49. The frozen checker rejects the bypass flag before
reading waveform behavior; the existing adapter's latch fields begin only
after a detector edge. Neither alone establishes what a bypassed circuit did.

The standalone Rust tool reads every decoded fault42 row and reports sampled
post-injection extrema for external fault, q, en, gate, channel, body and boost
inductor current. It reports counts plus first/last sampled simultaneous
q<=2.5V, en<=2.5V, abs(gate)<=0.20V, independently of the detector. Separate
channel-above0.1A counts/times expose sampled current returning later. Post
rows INCLUDE the injection row; strictly pre-injection rows exclude it.
Absent off/current-above observations have null timestamps, not zero.

Every report has accepted:false. Counts are observations, not durations or
continuous retention. The tool does not establish causal shutdown, healthy
operation, source phase, maximum sampling gap, physical interruption, or a
protection verdict. Equal-time observations remain separate and can disagree;
this is not a substitute for the campaign's event-ambiguity checks. Positive
time gaps are not limited here. The separately accepted prefix, phase, and
fault pipelines remain mandatory. It is for the fixed662ms BYPASS horizon.

Input guards: exact named42-column contract (order may vary), all finite
fields, nonnegative start within1ns, nondecreasing time, endpoint662ms within
1ns, initially low injection marker, one low-to-high marker crossing strictly
after650ms and before662ms, no later marker fall, and a strictly later sample.
An equal-time marker threshold crossing rejects. Lines are allocation-bounded
at16KiB. Report files use create_new; existing files are never overwritten.

CLI: `/private/tmp/matrix07-bypass55-parent INPUT.tsv|- NEW-REPORT.json|-`.
Use the fixed fault decoder13 on an immutable, independently hash-bound raw
archive and retain every pipeline exit. No new full capture or existing
campaign archive was scanned in this work. No BYPASS case is accepted.

Parent corrected the Luna candidate's icomp header, test channel/body mapping,
gate threshold label, rising-edge horizon, negative-start handling, later
marker fall, and misleading unit fixtures. Original worker-candidate.rs remains
retained. Standalone rustc --edition=2021 -D warnings builds passed; seven unit
tests and15 independent CLI cases passed. Independent probes cover no-detector
on/off, returned current, exact threshold boundaries, reordered columns,
equal-time rows, marker ambiguity, unsummarized NaN, missing endpoints/start,
negative start, endpoint injection, marker falls, oversized input, no-clobber
and stdin/stdout. The actual decoder42 schema also matches byte-for-byte by
column identity. Parent source/binary/test bindings are in parent-review.json.
