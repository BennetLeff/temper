# Anonymous-pipe normal capture runner 27

Parent reviewed and adopted for the LL05 retry. See `parent-review.json`.
Production changes replace the named export FIFO with a dedicated anonymous
compressor stdin pipe. The native host inherits its owned dynamic descriptor
as `/dev/fd/N`; the parent drops its writer after host startup. Logs remain
separate. Circuit, host, source binding, checkers, timeouts and the 10 GiB
reserve are unchanged.

Parent warning-clean build and all three inherited tests passed. The retained
20 us native comparison has 316 rows and byte-identical binary payloads through
anonymous-pipe and regular-file export. Parent independently checked gzip,
source changes, hashes and the complete normal15 decoder output. See
`parent-probe-verification.json` and `fixtures/real-native-20us-retained/`.
The original worker probe receipt remains diagnostic-only; adoption is recorded
separately by the parent. This does not predict acceptance of a full grid run.

The initial restricted execution failed opening `/dev/fd/N` with EPERM. The
same synthetic test and subsequent real native comparison passed outside the
filesystem sandbox. Preserve `fixtures/dynamic-fd-eprem/` as failed-open
evidence; its empty gzip is separate from LL05's incomplete export. Use the
approved execution environment for production capture.

The full LL05 retry must use a new output directory and pass every existing
capture, audit, endpoint and electrical check. LL05's first failed export is
retained; its cause is not established.
