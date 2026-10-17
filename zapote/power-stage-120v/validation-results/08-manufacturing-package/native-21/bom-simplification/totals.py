#!/usr/bin/env python3
"""Totals for the proposal. d_lines = change in unique BOM lines; d_ext = change in JLC-placed Extended types
(JLC fee $3 per Extended type per order); nostock = no-stock BOM lines resolved. Re-checks each new C-number's
JLC library type and stock live via jlc.py (cached in raw/)."""
import jlc
P = [  # id, risk, d_lines, d_ext, nostock, new C-numbers to verify
 ("B1 100nF 0603 -> CC0603KRX7R9BB104", "safe", 0, -1, 0, ["C14663"]),
 ("B2 100pF C0G -> CL10C101JB8NNNC", "safe", 0, -1, 0, ["C14858"]),
 ("B3 1uF 0805 -> CL21B105KBFNNNE", "safe", 0, -1, 0, ["C28323"]),
 ("B4 4.7uF 1206 -> 1206B475K500NT", "safe", 0, -1, 0, ["C29823"]),
 ("B5 100nF 0402 -> CL05B104KB54PNC", "safe", 0, -1, 0, ["C307331"]),
 ("B6 10k 0603 1% -> 0603WAF1002T5E", "safe", 0, -1, 0, ["C25804"]),
 ("B7 100R 0603 -> 0603WAF1000T5E", "safe", 0, -1, 0, ["C22775"]),
 ("B8 100k 0603 -> 0603WAF1003T5E", "safe", 0, -1, 0, ["C25803"]),
 ("B9 330R 0603 -> 0603WAF3300T5E", "safe", 0, -1, 0, ["C23138"]),
 ("B10 1k 0603 1% -> 0603WAF1001T5E", "safe", 0, -1, 0, ["C21190"]),
 ("B11 5.6k 0603 -> 0603WAF5601T5E", "safe", 0, -1, 0, ["C23189"]),
 ("B12 33k 0603 -> 0603WAF3302T5E", "safe", 0, -1, 0, ["C4216"]),
 ("B13 0R 0603 -> 0603WAF0000T5E", "safe", 0, -1, 0, ["C21189"]),
 ("B14 1k 1206 -> 1206W4F1001T5E", "safe", 0, -1, 0, ["C4410"]),
 ("B15 1R 1206 -> 1206W4F100KT5E", "safe", 0, -1, 0, ["C17928"]),
 ("B16 1N4148W-7-F -> 1N4148W (Semtech)", "safe", 0, -1, 0, ["C81598"]),
 ("B17 MMBT3904-7-F -> MMBT3904 (CJ)", "safe", 0, -1, 0, ["C20526"]),
 ("V1 4.99k 0.1% -> 4.99k 1% Basic", "safe", 0, -1, 0, ["C23046"]),
 ("V2 18.2k 0.1% -> 18k 1% Basic (RCLK)", "safe", 0, -1, 0, ["C25810"]),
 ("V3 30.1k 0.1% -> 30k 1% Basic (RILIM)", "safe", 0, -1, 0, ["C22984"]),
 ("V4 R1/R2 120k -> 100k Basic", "safe", 0, -1, 0, ["C17900"]),
 ("M1 GRM32ER71H106KA12L -> UMK325AB7106KM-T", "safe", -1, -1, 0, ["C386167"]),
 ("S1 R34/R35 10.6k/10k -> 12.4k/11.7k", "safe", 1, 1, 1, ["C861102", "C4553285"]),
 ("S2 6.12k -> 6.2k", "safe", 0, 0, 1, ["C136960"]),
 ("S3 133k -> Viking ARG03BTC1333", "safe", 0, 0, 1, ["C1509631"]),
 ("N1 R3/R4 220k -> 100k Basic", "needs-check", 0, -1, 0, ["C17900"]),
 ("N2 R40/R41 1k 0.1% -> 1k 1% Basic", "needs-check", 0, -1, 0, ["C21190"]),
 ("N3 U1/U2 -> UCC21550BQDWKRQ1", "needs-check", 0, 0, 1, ["C42216738"]),
 ("N4 U35 -> SN6507DGQRQ1", "needs-check", 0, 0, 1, ["C7528027"]),
]
bad = []
for p in P:
    for c in p[5]:
        d = jlc.detail(c)
        want = "base" if p[0].startswith(("B", "V")) or c in ("C17900", "C21190") else None
        if want and d.get("componentLibraryType") != want: bad.append((p[0], c, d.get("componentLibraryType")))
        if not d.get("stockCount"): bad.append((p[0], c, "zero stock"))
for risk in ("safe", "needs-check"):
    s = [p for p in P if p[1] == risk]
    print(f"{risk:12s}: items {len(s)}, unique lines {sum(p[2] for p in s):+d}, Extended types {sum(p[3] for p in s):+d} "
          f"(${-3*sum(p[3] for p in s)} per order), no-stock lines resolved {sum(p[4] for p in s)}")
print("verification problems:", bad or "none")
