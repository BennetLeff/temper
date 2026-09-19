# TEA spacing source identity

This directory records the source identity and the exact clauses used by the
spacing decision. It intentionally does not copy or rewrite standards. The
retained dossier is the working extraction, and the hashes below bind this
decision to the source bytes and the product documents that supplied the
declared environment.

| Source | Identity | Use |
| --- | --- | --- |
| `TEA2209T.pdf` | SHA-256 `fb611299c890a0dcaf7d610ed3fe742a3ab8debf21a75b540b8cede2e7badc99`; retained at `zapote/power-entry/loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-VERIFY/attempt-001/raw/reused_sources/TEA2209T.pdf` | NXP pin functions, limiting values, package dimensions; no PCB creepage/clearance guidance found in the 19-page datasheet. |
| IS 302-1:2008 recovery | SHA-256 `2695a4bc1b2c87dd24a6126d984d01ad30be53c8d905ff196b73241b73f99251` as recorded in `tea-dossier.md` §10 | Functional clearance clauses 29.1.4/29.1.5, functional creepage delegation in 29.2, Annex L. |
| IS 15382-1:2003 recovery | BIS RTI text at `archive.org/download/gov.in.is.15382.1.2003/is.15382.1.2003_djvu.txt`, identity and adoption recorded in `tea-dossier.md` §11 | Working-voltage, clearance and creepage method; Table 4 values; no recovered floating-spacer rule. |
| Product environment | `docs/ENVIRONMENTAL_SPEC.md` SHA-256 `afa367890d4872cce0033455ded49ea9b5826b9ba3a25229f4ec336d34cbaccf`; `docs/specs/SURGE_CONTRACT.md` SHA-256 `fe6c05d9ab61908bff18c34955ade3c274244306bca05567d577c66eb4ac2e6a` | 120 V RMS ±10% board context, altitude, PD2 prerequisite, and transient scope. |

The standard recoveries are evidence for a conditional engineering analysis,
not a compliance certificate. The applicable current IEC/60335 edition,
product part standard, CTI/material group and production assembly remain to be
confirmed by the safety owner.
