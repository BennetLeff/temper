# AR-MOV attempt-001 — MOV clamp capture and device/controller stress derivation

Task ID: **AR-MOV** · Attempt: **attempt-001** · Campaign: 2026-09-17-pfc-campaign · Kind: source_research.
Contract C1.1 `0accd9bc…a825d6` (matches dispatch). Dispatch `source_revision` `3691798c…`;
HEAD `fd9d70577` is that commit plus the coordinator's own AR-FAULT-correction commit, and the
tree also carried the coordinator's uncommitted dispatch/registry edits. Source-only task, so the
delta cannot affect an external number. Recorded, not silently ignored.

**Hypothesis / actual changed variable.** The MOV's surge-clamped terminal voltage sets both the
active-bridge MOSFET's required rating and the TEA2209T's node stress; the change is replacing
AR-VERIFY's **ASSUMED ~400 V** with a **captured** datasheet value and separating the product surge
current from the datasheet's clamp-test current.

## 1. Capture result (primary source)

| Item | Value |
|---|---|
| Part | **V150LA10AP** (Littelfuse LA Series, branding P150L10, 14 mm disc) |
| Document | Littelfuse *Metal-Oxide Varistors Datasheet — LA Series Radial Lead Varistors* |
| Revision | **Revised: VL 16/9/2024**, © 2024 Littelfuse — 13 pages |
| Page | **2**, table *LA Series Ratings & Specifications* |
| **Clamp** | **VC = 395 V MAXIMUM at IPK = 50 A, 8/20 µs** (25 °C) |
| Rating basis | ITM = 4500 A (8/20 µs); WTM = 45 J (10/1000 µs); VNOM 216–264 V @ 1 mA DC; VM(AC)=150 V, VM(DC)=200 V; C=800 pF |
| File | `raw/littelfuse_LA_series_datasheet.pdf`, sha256 `8e6c56a7901cc2748a4a58685ccdc7228b13ee07dc5442c411824172e00a7ecc`, 1,376,391 bytes, magic `%PDF-1.7` |

No substitution was needed — the intended part was captured directly. The clamp is reported **with
its surge current and waveform**, as required.

**Capture path.** The manufacturer host rejected every direct request with HTTP 403 (Akamai) on
`www.littelfuse.com`, `m.littelfuse.com` and `www.littelfuse.cn`; the one permitted alternate mirror
(the distributor-hosted copy of the manufacturer PDF) returned an HTML consent wall at HTTP 200, not
a PDF. The manufacturer's own PDF was then retrieved from the Internet Archive snapshot `20260711204225`
of the manufacturer assetdocs URL (headers retained in `raw/hdr_wayback.txt`). All failures are retained
in `raw/capture_failures.json`. **Note on the earlier 403s:** AR-VERIFY's primary URL used assetguid
`8f6b9e0a-…`, which does not resolve to a real Littelfuse asset; the real LA assetguid is
`f7c547ce-c2fa-4789-86cc-ec39a5060afb`.

## 2. Source conditions — and the current that is actually specified

The datasheet specifies the clamp **at 50 A only**. The provisional product contract (IEC 61000-4-5,
1 kV L-L / 2 kV L-PE combination wave) with the standard 2 Ω generator implies a **prospective
short-circuit current of 500 A (L-L) / 1000 A (L-PE)** at 8/20 µs. The MOV is across L-N, so it clamps
the **differential (L-L)** mode; the L-PE surge is not clamped by it.

At 500 A the MOV clamps **higher** than at 50 A (p.7 Figure 10 shows the 14 mm family V-I rising with
current), but **no guaranteed value is tabulated there**, and the actual MOV current is itself set by
the unknown clamp. An automated curve trace of Figure 10 hopped between the adjacent V130/V140/V150/V175
curves and was **rejected as an unreliable instrument**; no digitised value is used. Therefore:

> **clamp at the product surge current = `null`; the sourced 395 V is a LOWER BOUND for any I > 50 A.**

## 3. Derived stresses — MOSFETs (each against its own limit)

The off active-bridge device blocks the line terminal voltage, which the L-N MOV clamps.

| Case | Terminal V | 600 V margin |
|---|---:|---:|
| Steady, 132 V rms line peak | 186.68 | 3.21× |
| Sourced clamp (50 A, 8/20 µs) | **395** | **1.52×** |
| Sensitivity, if surge clamp = 440 / 500 / 600 V | 440 / 500 / 600 | 1.36× / 1.20× / **1.00×** |

The required rating follows from the **clamped terminal voltage**, **not** from the controller's 700 V
limit and **not** from the 400 V bus. The 600 V class is the candidate class (IPW60R017C7 / IPW65R045C7),
not a completed qualification. Because the true clamp above 50 A is unknown, the margin at the product
surge is **unknown and strictly smaller** than 1.52×.

## 4. Derived stresses — controller (its own limits, independent of the MOSFET)

TEA2209T Rev 1.1 (2021-04-14), p.8 absolute-max: pins **L, R, VR, VCCHL, VCCHR, GATEHR, GATEHL** and the
differentials **dV(VR-L), dV(VR-R)** are **440 V operating / 700 V mains-transient**; p.12 notes surges
must be limited below 700 V.

| Case | Node V | of 440 V operating | of 700 V transient |
|---|---:|---:|---:|
| Steady line peak | 186.68 | 0.424 | 0.267 |
| Sourced clamp (395 V) | 395 | **0.898** | 0.564 |
| If surge clamp = 500 V | 500 | **1.136 (exceeds)** | 0.714 |
| If surge clamp = 600 V | 600 | 1.364 (exceeds) | 0.857 |

At the sourced clamp the nodes are just under their operating limit; if the surge current drives the
clamp above 440 V they **exceed the operating limit during the surge** (while staying under the 700 V
transient limit). The node voltage is set by the circuit clamp: **a higher-rated MOSFET does not lower
it, and the controller's 700 V allowance does not require an 800/1000 V device.** L-PE common mode is
INDETERMINATE (not clamped by the L-N MOV).

## 5. Surge contract — explicitly PROVISIONAL

The IEC 61000-4-5 **1 kV L-L / 2 kV L-PE** level is **ASSUMED, not adopted**: it lives in a curriculum
checklist (`docs/architecture/induction_curriculum.md:2112`), not a committed requirements document
(`docs/specs/REQUIREMENTS.md` names no surge level). Every surge-derived number above is conditional on
it. What would settle it: (a) a released requirement naming standard, level and waveform and whether an
L-PE clamp is fitted; (b) a captured/measured V-I curve read at the actual MOV current.

A separate conflict stands: `docs/specs/REQUIREMENTS.md:511` says "MOV: 275 V, 10 kA", but the committed
part is V150LA10AP (150 V rms MCOV) on a 132 V-max board; a 275 V MCOV part would not clamp the 186.7 V peak.

## 6. Internal fault — explicitly out of scope

**A line-surge MOV across L-N does not resolve an internally powered fault.** The boost-switch-short
capacitor-discharge loop (179.24 J in 2240.47 µF) never reaches the MOV terminals — nor the shunt U12.
That loop's interruption and energy distribution are **AR-PROTECT's** question, and no MOV clamp figure
is admissible as a bound on it.

## 7. Accounting

- Case census: expected 1; attempted 1; **valid 1**; failed 0; unsupported 0; unrun 0.
- **Checker:** `not_applicable` by dispatch (G0 unimplemented) → no receipt; per ADMISSION.md this is
  **not a validated run** and is retained as evidence only. **Hardware qualification NOT_PERFORMED.**
- Sources captured: 1 primary PDF (manufacturer document). Manufacturing capture failures: 4 (three host
  403s + one HTML mirror). Reused: TEA2209T.pdf (unchanged from AR-VERIFY, sha256 `fb611299…`).
- Solver invocations 0; model/CAD/BOM edits 0; bench work none; procurement none. Touched files: only
  this attempt directory. No commits, no stash.
- Evidence pointers: `raw/littelfuse_LA_series_datasheet.pdf`, `raw/littelfuse_LA_series_page2_table.txt`,
  `raw/capture_failures.json`, `raw/hdr_wayback.txt`, `raw/compute_ar_mov.py`, `raw/compute_result.json`,
  `inputs.json`, `result.json`.
- Unresolved: (a) clamp at the real surge current (null, lower bound 395 V); (b) committed surge level;
  (c) L-PE common-mode stress; (d) bus surge excursion (boost switch is a separate case); (e) MOV energy
  margin for a 500 A 8/20 µs event (ITM 4500 A suggests survival but energy is not established).
- Recommended next observation: obtain the V150LA10A(P) V-I curve at the MOV's calculated operating
  current (a clean single-part datasheet curve, or a measured clamp), then re-run this arithmetic. It is
  the only input that can move the 600 V margin and the 440 V controller limit verdict.

---

**The single most important missing input:** the **V150LA10AP clamp voltage at the actual MOV current of
the surge event** — an 8/20 µs V-I value read at a few hundred A under a committed surge requirement, not
the datasheet's 50 A test point. The captured 395 V @ 50 A is a lower bound, so both the MOSFET rating
margin and the controller node stress are one-sided until this is known.
