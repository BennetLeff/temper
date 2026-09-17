# PFC option research independent technical review

Review scope: read-only review of the three option reports, candidate JSON,
retained PDFs and standalone arithmetic receipts on 2026-09-17. No builds,
hardware tests, or source edits performed.

Findings

1. **High — invalid onsemi source artifact.**
   `replacement-fet/sources/NVHL040N65S3F.pdf` is HTML, not a PDF: `file(1)`
   reports HTML document text and the bytes begin with `<!DOCTYPE html>` and
   “Access to this page has been denied.” Nevertheless, `REPORT.md:156-158`
   says three retained datasheet PDFs are hash-checked, and
   `candidates.json:59-67` identifies this denial page as the exact Mouser
   datasheet bytes. The NVHL voltage/current/RDS/Qg/Qgd claims therefore have
   no retained source evidence. Re-fetch a valid official or distributor PDF,
   hash that file, and update the source register; until then mark the
   fallback’s data unverified and do not use it for ranking.

2. **Medium — UCC27624 source revision/path drift.**
   The retained `replacement-pair/sources/UCC27624-RevE.pdf` header is
   `SLUSE44E – APRIL 2020 – REVISED MARCH 2026` (lines 1-2 of the PDF text).
   `REPORT.md:100` still labels it “Rev D” and points to nonexistent
   `sources/UCC27624-RevD.pdf`; `candidates.json:82` says “Rev D (2025-06)”.
   The hash in `candidates.json:218` does match the actual RevE file, so the
   electrical numbers are not disproved, but the source identity is wrong.
   Rename/fix the report and candidate revision/date/path to Rev E, March
   2026, and retain the matching path/hash.

3. **Low/medium — unsupported semantic label for Pair B gate voltage.**
   The retained onsemi NTH4L060N065SC1 PDF states recommended gate-voltage
   operating range `-5/+18 V` and separately reports a typical RDS(on) test at
   15 V; it does not identify 15 V as a recommended turn-on voltage.
   `replacement-pair/candidates.json` labels this as
   `mosfet.recommended_vgs_on_v: 15` and the Pair B qualification text asks
   to verify a “15 V gate plateau”. Keep 15 V as the proposed screen/test
   condition, but rename the field to `screen_vgs_v` (or state “RDS test
   condition”); do not present it as a manufacturer recommendation.

Checks that passed: retained NTH and TI UCC27524A values match their PDFs;
Infineon IMZA claims match the official Rev 2.2 datasheet (web verification);
reported I²R and Qg·V·f arithmetic recompute; Miller on/off values in the
replacement-FET JSON agree with its Rust receipt; existing-drive formulas
retain the stated conditional/upper-bound caveats. Previously known rootfixes
(132-V nominal current, low-voltage test qualification, sink-current formula,
RMS-vs-DPT current, UCC27524 15-V nominal, and SiC 18-V rail) were not
repeated as new findings.
