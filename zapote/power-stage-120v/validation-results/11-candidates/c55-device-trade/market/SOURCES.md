# c55 device trade: where the market evidence came from

Read on 2026-10-27 local time (PDT), which is 2026-10-28 UTC. Everything here was collected by an agent; nothing was simulated. Downloads are kept outside git in `/Users/bennet/Desktop/temper/worktrees/runs-native21/c55-dl/<PART>/`. The extracted values are in `datasheets.json` (each value has its page number), `models.json` and `distributor-2026-10-27.csv`.

## How the files were fetched
- **DigiKey.** Public product and search-list pages were read in Chrome with no login and no cart. The page cleared its Cloudflare check by itself. Prices are list prices in USD, not quotes. The 80-piece column uses the largest price break at or below 80, and the 2000-piece column the largest at or below 2000.
- **Mouser.** Mouser showed a "Verification Required" slider bot check. Bot checks are not bypassed, so there is **no Mouser data** for any part. Every part's DigiKey stock is below 2000, so a Mouser read (done by hand) or a quote is still owed.
- **Infineon.** Plain `curl` returns an empty HTTP 202, so files were fetched in Chrome on infineon.com. Model zips came from direct navigation to their `content/dam/.../24/50/...zip` URLs, which were found by logging the URL the page's Download button opened. PDFs came from the `assets/row/.../24/49/` URLs.
  - The CM8 datasheet sha256 matches the expected `426b5d31…97c7`.
  - The 600 V CM8 zip sha256 matches the expected `32050b46…2f69`.
  - The 2EDR8259X datasheet sha256 matches the expected `f49391ca…ae33`.
- **Wolfspeed and onsemi.** Datasheets were fetched with plain `curl -L`.
- **ST.** The datasheet was fetched in Chrome from st.com/resource/en/datasheet.
- **Renesas.** The datasheet was fetched with `curl`.
- **Cookie banners** (Wolfspeed, onsemi) were set to essential cookies only, or "Reject All".

## What we got
### A. Baseline and CM8
- **DigiKey reads for both parts:**
  - IPW65R018CM8XKSA1 has only **2 in stock** and a 24-week lead time.
  - IPW65R018CFD7XKSA1 has 459 in stock and an 8-week lead time.
- **New finding: a vendor model of the exact 650 V CM8 part now exists.** Infineon publishes "650 V CoolMOS 8 SPICE Model Library" (v01_00, listed May 7, 2025). Its library `cm8/c8_650/IFX_C8_650V.lib` (Version 1253, dated 2025-04-24) contains `IPW65R018CM8_L0/_L1/_L3`. This replaces the IPW60R016CM8 proxy.
  - The 600 V library was still fetched as asked. It is unzipped at `cm8/c8_600/IFX_C8_600V.lib`. The zip has no folder inside, so the `c8_600/` directory was created for it.

### B. 650 V SiC parts chosen, all TO-247-3
None of the SiC parts DigiKey carries in this range has 2000 or more in stock.

| Part | DigiKey stock | Vendor SPICE model |
|---|---|---|
| Infineon IMW65R026M2H (CoolSiC G2) | 270, "no backorders" | **Obtained.** The G2 library v1380 has `IMW65R026M2H_L1/_L3`. It is plaintext: the "SIMPLIS Encryption" tags are markers only. |
| Wolfspeed C3M0025065D | 430 | **Not obtained.** See below. |
| onsemi NTHL032N065M3S | 845, plus 5,850 factory stock | **None published.** The onsemi SPICE library has 900 V SiC MOSFET models only. M3S parts get only the PLECS model generator and Elite Power Simulator. |

- **Wolfspeed model.** Its only SPICE download is "All SPICE Models (ZIP)", and it opens a Terms-of-Use "I Accept" modal. The modal was not accepted and the URL was not extracted, because accepting terms needs the user's OK. No account is needed: a user click, or permission for the agent to click, is enough. C3M0025065D is rated at VGS = 15 V, which matches today's +15 V drive.
- **Rejected SiC parts:**
  - NTHL023N065M3S: 0 in stock, next delivery 2028.
  - ST SCTW/SCTWA 650 V G2: obsolete or not stocked at DigiKey. The keyword "N65G3" returned nothing.
  - IMW65R020M2H: 16 in stock.

### C. 650 V reverse-conducting IGBTs
- **Infineon IHW40N65R5 (TRENCHSTOP 5 RC-H5):** the L1 SPICE model was obtained and is plaintext.
- **Infineon IHW40N65R6 (RC-H6):** the L1 SPICE model is plaintext. The L2 model is SIMetrix-only and its body is **encrypted** (SMX_AES), so it is unusable in ngspice or LTspice.
  - **650 V RC-H6 does exist:** IHW30N65R6, IHW40N65R6 and IHW50N65R6 are all active at DigiKey.
  - DigiKey returns nothing for "N65R7". No 650 V R7 part was found; the R7 line appears to be at higher voltages, but that was not checked here.
  - IHW30N65R5 is Last Time Buy (LTB date 2027-03-15).
- **ST STGWA50IH65DF (IH series):** datasheet and DigiKey read only.
  - It has a co-packed diode, which is not reverse-conducting (RC) technology.
  - The package is the long-lead TO-247.
  - STGWA40IH65DF is not stocked and has a 600-piece minimum order.

### D. GaN (reference only)
- **Renesas TP65H035G4WS:** the datasheet was obtained and DigiKey shows 803 in stock.
- **No SPICE model:** the Renesas documentation list loads dynamically, and the search was cut off at its time limit.
- **Pinout is G-S-D with the tab on Source**, not G-D-S, so it does not fit the board's footprint as-is.

### E. Gate driver
- **2EDR8259X, Rev 1.7 (2026-04-09):** values are extracted in `datasheets.json` under `2EDR8259X`.
  - The "8" in the part number is the 8 V output UVLO class: turn-on typ 8.0 V / max 8.5 V, turn-off min 6.6 V / typ 7.0 V (p13).
  - VDDA/VDDB recommended range is 8.5–21 V (p12). Absolute maximum is 22 V.
  - The output is rail-to-rail between VDDx and GNDx (p9). There is no separate VEE pin.

## Datasheet findings that matter for the sim, with pages in datasheets.json
- **Gate drive today is +15 V / -1.6 V. The SiC vendors recommend:**

  | Part | Recommended on / off | RDS(on) at VGS = 15 V |
  |---|---|---|
  | C3M0025065D | 15 V / -4 V | 25 typ / 34 max mΩ at 25 C; 33 typ mΩ at 175 C. VGS(th) typ is 2.3 V at 25 C and 1.9 V at 175 C. |
  | IMW65R026M2H | 18 V / 0 V | 34 mΩ typ at 25 C (no max given). About 46 mΩ at 175 C, read from figure. It is stated to tolerate a 0 V turn-off and bipolar drive. |
  | NTHL032N065M3S | 18 V / -5…-3 V | 41 mΩ typ at 25 C and 52 mΩ typ at 175 C, both at only 15 A. Its pin pitch is 5.56 mm nominal. |

- **The IGBTs specify no short-circuit rating and no maximum switching frequency.** All of their switching tests use VGE 0/15 V.
- **IHW40N65R6 gives a soft turn-off Eoff close to this bus.** Conditions: VCE 162 V, Cr 30 nF, 40 A, 10 Ω. Result: 0.11 mJ at 25 C and 0.22 mJ at 175 C (p5).
- **IHW40N65R5 gives only hard-switched values** at 400 V.
- **STGWA50IH65DF does not characterise turn-on at all** ("designed for soft-commutation only"). Its snubbed Eoff is at 320 V.

## Caveats
- The DigiKey stock figure for IMW65R033M2H differed between the search list (401) and the detail page (161) a few minutes apart. Both numbers are recorded.
- List-only rows in the CSV have just the quantity-1 price, and that price fills the 80 and 2000 columns. Use them only as indicators.
- Figure readings in `datasheets.json` are approximate.
