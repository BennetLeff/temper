# N-DPT-ST report — STW65N65DM2AG vendor DPT vs the C7 control

Task **N-DPT-ST** · attempt **attempt-001** · campaign `2026-09-17-pfc-campaign`
Base revision `83113048974fbe34508e715aec735dfb25642d3a` · contract C1.1
`0accd9bc55afbf875b08ed4dcdd8b7bbaf009d6f6fd1824f6b03c58797a825d6`

## 1. Question and changed variable

Does the retained board device **STW65N65DM2AG** (STMicroelectronics) really cost
about **twice** the **IPW65R045C7** (C7) on switching, measured by the SAME
independent ngspice double-pulse testbench that produced the C7 result?
Hypothesis: the analytic model's ~2.05× claim (93.183 W vs 45.5023 W) is
confirmed by an independent vendor model.
Actual changed variable: **none** — no design, model, or board edit. This is an
independent simulation instrument (ngspice), deliberately not importing or
reproducing `zapote-erc::pfc_switching`.

**Outcome: the ST model could not be captured. The STW result is UNKNOWN and the
2× claim remains unverified by a vendor model.** A precise capture failure is the
result; no substitute device and no hand-written model were used.

## 2. Identities and what reproduced

| Role | Part | Model | 25 °C control target | re-run result |
|---|---|---|---|---|
| Baseline control | IPW65R045C7 | Infineon CoolMOS C7 Level-0 (`d159f168…8983`) | Eon 102.50 / Eoff 104.79 / Eoss 9.76 µJ | **Eon 102.495 / Eoff 104.786 / Eoss 9.757932 µJ** |
| Task device | STW65N65DM2AG | **ST model NOT_CAPTURED** | — | **UNKNOWN** |

**Control reproduced.** The control netlists were copied byte-for-byte from
N-DPT attempt-001 (`dpt_ipw65r045c7_L0_25c.cir` sha256 `d0549c16…151a`, model libs
identical — see `inputs.json` `testbench_reuse`). Re-running them on this host
gave ngspice `.meas` lines **byte-identical** to the prior attempt at both 25 °C
and 125 °C (`diff` clean; `raw/logs/control_*`). The testbench is unchanged, so a
comparison would have been meaningful had the ST model been obtained.

## 3. Testbench (reused, not rebuilt)

Clamped-inductive double pulse, ngspice-45.2: 400 V bus → 180 µH → switching node
→ 0 V sense → DUT → ground; freewheel SiC diode across the DUT. Gate PWL 0→12 V
through a behavioural external resistor **9.7 Ω on / 5.3 Ω off** (vendor internal
Rg = 0.82 Ω, Lg = 5 nH retained). E = ∫v(drain)·i(dsense)dt over a 182 ns window
(`meas … integ`). No testbench parameter was touched.

## 4. ST capture result (STEP 1)

**NOT_CAPTURED.** The model exists only at ST:
`https://www.st.com/resource/en/spice_model/stw65n65dm2ag_spice.zip`
("STW65N65DM2AG PSpice model", v1.0, 13 Jan 2016), established from **ST's own
archived product page** (`raw/failure_records/wayback_product_20260212.html`,
Wayback 20260212103247, HTTP 200, 277843 bytes). Its existence and exact path are
ST-authored; the model bytes were never obtained.

Every route failed (`raw/capture_log.txt`, `raw/failure_records/`):
- **st.com**: every path (HTML pages and the resource zip), both IPv4/IPv6, with
  HTTP/2, HTTP/1.1, TLS 1.2/1.3, python-urllib and wget → `curl (92) HTTP/2
  INTERNAL_ERROR` or connect/read timeout, **0 bytes**; alternate hosts
  `my.st.com`, `www.st.com.cn`, `eds.st.com` also 0 bytes. The apex
  (54.194.135.49) serves only a 301 redirect; forcing the www vhost there gives
  404.
- **Archives**: the exact zip is **absent** from the Wayback Machine (CDX `[]`)
  and archive.today ("No results"); Save-Page-Now returned 523/500. Sibling
  MDmesh DM2 models *are* archived (e.g. `stw50n65dm2ag_spice.zip`), this part is
  not.
- **Distributor/mirror**: Mouser (bot block), Digi-Key (403), TME (403),
  Component Search Engine (302; ECAD footprint only). Web/GitHub search found
  datasheets and CAD footprints, **no** ST SPICE model.
- **Relays** (allorigins, codetabs, corsproxy, cors.eu.org, jina) → 522/520/429/
  422/timeout, no ST bytes.

**Provenance verification: NONE.** No candidate file was ever downloaded, so no
copy could be verified as ST's own model; nothing was accepted on trust.

## 5. Results (µJ; f = 129107.392 Hz)

| Device, T | Eon | Eoff | Eoss(400 V) | (Eon+Eoff)·f | vs C7 vendor 26.76 W |
|---|---:|----:|---:|---:|---:|
| **IPW65R045C7, 25 °C** | **102.495** @ 12.070 A | **104.786** @ 14.985 A | **9.7579** | **26.7615 W** | **1.0001** |
| IPW65R045C7, 125 °C | 99.4706 @ 12.033 A | 97.3056 @ 14.944 A | 8.6862 | 25.4053 W | 0.9494 |
| **STW65N65DM2AG, 25 °C** | **null** | **null** | **null** | **null** | **null** |
| STW65N65DM2AG, 125 °C | null | null | null | null | null |

The 25 °C control reproduces the independent C7 vendor result
**(Eon+Eoff)·f = 26.7615 W vs 26.76 W** (ratio 1.0001), and vs the analytic C7
overlap 37.3682 W gives 0.7162 (overlap-only 0.6824) — the same ~0.72× the prior
attempt reported.

**Ratios.** Analytic STW/C7 total = 93.183 / 45.5023 = **2.0479× (~2×)** — an
analytic-model claim, not a vendor result. The **vendor** STW-to-C7 ratio is
**null**, because the ST Eon/Eoff are unknown.

## 6. Refinement evidence (control, same testbench)

| Control | Eon (µJ) | Eoff (µJ) |
|---|---:|---:|
| nominal (tstep 1e-10, tmax 1e-9) | 102.495 | 104.786 |
| 5× (5e-11 / 5e-10) | 102.504 | 104.782 |
| 10× (2e-11 / 2e-10) | 102.500 | 104.777 |
| integration window start −10 ns | 102.495 | 104.877 |

Eon spread ≤ 0.009 µJ (0.009 %), Eoff spread ≤ 0.009 µJ (0.009 %); Eoss grid
25→43 bias points 9.7579→9.7616 µJ (0.037 %). All match N-DPT attempt-001's
refinement claims. The instrument is numerically converged.

## 7. Case accounting

| Count | Value |
|---|---|
| Devices attempted / valid / capture-failed | 2 / 1 / **1** |
| DPT cases planned / valid / unrun (ST) | 4 / 2 / **2** |
| Refinement/control runs | 4 |
| ngspice invocations | **9** of 48 budget |
| Checker | **not_applicable** (none issued) |

Touched: this attempt directory only. No commits, no `git stash`.

## 8. Most important caveat

The headline control number is a **vendor typical-device macromodel simulation,
not a measurement and not a hardware qualification**; and the ST device — the
campaign's **largest claimed lever** — has **no independent result at all**,
because its only published model sits behind an unreachable `st.com`
(Akamai edge fails on every request). The ~2× claim is therefore **still
unverified** by any vendor model.

## 9. Next observation (single)

Ask the coordinator to provide the STW65N65DM2AG model from a machine or network
that can reach `st.com` (or an ST-authored mirror with its bytes hashed),
then re-run this exact testbench. That is the one observation that would settle
the 2× question; otherwise the "ST is ~2× the C7" branch cannot be closed by
vendor simulation and should be marked unverifiable-by-vendor-model.

## 10. Accounting

Wall time ≈ 1.0 h. Deadline `2026-09-18T01:10:00Z`: met. Deliverables:
`inputs.json`, `result.json`, `REPORT.md`, `manifest.json`, `raw/` (models,
netlists, logs, tools, derived, capture_log.txt, failure_records).
