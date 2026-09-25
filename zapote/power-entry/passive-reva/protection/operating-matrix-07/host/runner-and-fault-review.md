# Host verification, 2026-09-20

The corrected line/load runner compiles with `rustc --edition=2021 -D warnings -O` and its self-test passes from `line-load-runner/`. The intentionally invalid compressor output emits an expected shell error. The independent review findings prompted actual pipeline cleanup on adapter/checker/file creation failure, checked FIFO creation/type, and exact parameter-token matching. Production deck inverse replacement is verified. No accepted baseline receipt or grid execution exists.

The fault adapter compiles as both a normal binary and a test binary with `-D warnings`; all nine tests pass. All fixture tests now use the production streaming implementation, with no second normalizer algorithm. Extra nonfinite fields, AC subtraction overflow, duplicate headers, nonincreasing time and wrong mutation controls are rejected. Current after injection, detector assertion and latch-off is reported separately. These are transport/checker-readiness results, not executed fault evidence.

The first-invalid harness compiles with `-D warnings`; three tests pass, including callback ownership and named-value capture. All sixteen actual ngspice diagnostic names were observed. The host ran the unchanged full electrical deck for two wall seconds: 61,162 callbacks through 8.020217585 ms, all names present, successful partial export. The completed diagnostic replay in `first-invalid-capture/run/` reproduced the original first nonincreasing time at 256.990362 ms. The later vendor-driver startup in `normal-vendor-driver-candidate/tracked/run/` instead aborted at 97.345625 ms with a solver timestep error. Both are rejected startup traces, not circuit acceptance.

The host independently compiled and ran the final recursive-include runner self-test (session63306, exit0). It passed nested vendor-library copying/hashing, non-UTF8 comments with nested directives, missing/traversing/symlink includes, digest mutation and process cleanup checks. The expected directory-output shell error belongs to a negative control. A follow-up comment-only correction documents the parser's lossy text view accurately. No accepted baseline receipt was created and no grid case ran.

The newer runner accepts `--first-invalid-snapshot`, appending the fixed
case-local `first-invalid.tsv` argument to the four existing tracker arguments.
The actual spawn uses the same tested argument builder, and the source identity
receipt records the chosen argument list. The host independently rebuilt with
`-D warnings` and passed its self-test (session89783, exit0). The current
hysteretic-driver capture needs this flag; the older four-argument protocol
remains the default. This is runner readiness, not matrix execution.
