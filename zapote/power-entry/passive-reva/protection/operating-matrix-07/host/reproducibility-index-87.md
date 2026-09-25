# Reproducibility index 87 — parent reviewed, interim

[The JSON index](reproducibility-index-87.json) lists exact source closures,
acceptance and diagnostic receipts, tool sources/pins, original launch/analysis
entrypoints, and the manufacturer's model-boundary evidence. Every listed
small regular file was SHA-256 hashed during index creation. This identifies
the actual uncommitted model bytes; the repository commit is context only.

All14 indexed completed or partial raw archives are present, and their current
file sizes match the recorded receipts. Their large-file digests are copied
from the prior source-bound receipts and explicitly marked **not rehashed in
this indexing pass**. Baseline raw is under `numerical-repair/nonstopping-first-invalid/run`,
F2-CREST under `faults/settled-direct-capture-38/F2-CREST`, and F2-ZERO under
`faults/settled-direct-capture-51/full-F2-ZERO`. The worker incorrectly assumed
that those archives lived beside their later analysis receipts; none was lost.
The original worker index is retained separately.

Commands are classified as historical, pending, or reconstructed from a frozen
interface. None ran during indexing. Fixed-output launch/analysis scripts must
never be rerun over live or recorded output. The actually completed F2-ZERO
legacy witness used `legacy-strict-67.sh`; the older script is historical and
contains the failed preflight comparison. The bare F2-CREST prefix scan also
needs its declared CASE/OUT environment, so it is not presented as a standalone
replay command. The phase43 pipeline recipe is explicitly reconstructed from
its reviewed interface and accepted parameters, not claimed as a saved shell
transcript. Each standalone Rust source can be built using its retained README
and reviewed tool manifest; changing compiler or simulator versions creates a
new tool identity and requires revalidation.

The index remains interim: DIODE-SHORT is running; BOTH-SHORT and BYPASS-NEG
remain prepared. SW-SHORT is INDETERMINATE with a partial-run archive and no
accepted own prefix/phase/complete fault window. Prepared scripts are not
completed results. Current scope and remaining work are summarized in the
[parent-corrected report](campaign-report-87.md).
