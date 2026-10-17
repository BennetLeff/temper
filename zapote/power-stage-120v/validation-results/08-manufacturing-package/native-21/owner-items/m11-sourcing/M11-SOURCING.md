# M11 insulation stack: sourcing for the native-21 prototype lot

**Lot:** 5 boards plus 2 spare stacks, so **7 stacks**. Read date for every web source is **2026-10-08** unless the row says otherwise.
**Spec:** `validation-results/08-manufacturing-package/native-21/owner-items/m11/RECOMMENDATION.md` (§4, §4.1, §4.2) and DECISIONS.md 2026-10-08 "heatsink HOT↔PE insulation stack (review M11)".
**Scope:** research only. Nothing was ordered, carted, quoted through a form or emailed.

**Access limits:**
- **Blocked:** Digi-Key, Mouser, Newark/Farnell, Distrelec/RS, Bürklin and DAU returned HTTP 403 or a bot wall to both WebFetch and curl. McMaster pages need JavaScript.
- **How such figures are marked:** rows that rely on those sites quote search-result text and are marked **"snippet, unverified"**. The browser agent must confirm them (§9).

**Evidence classes:**
- **CITED:** a page I read.
- **SNIPPET:** search-engine text only.
- **CALC:** computed by `calc/per_device_calc.py` in this folder, or in the arithmetic shown here.
- **EST:** an engineering estimate.

---

## 0. Summary

| # | Item | Recommended route | Indicative cost per stack | Longest lead |
|---|---|---|---|---|
| 1 | AlN tiles A + B | **Option B (custom shared tiles), cut from stock 2.032 mm lapped-both-sides AlN plate.** Option A (per-device catalogue) **does not fit** (§1). | £133 per stack material share (4 Almath plates at £232 over 7 stacks), **≈ £150–250 ($190–320) all-in** (EST) once cutting and chamfer are added | **RFQ, typ. 3–6 weeks (EST)**, the longest item |
| 2 | Thermal compound | **Electrolube HTCP20S** (metal-oxide filler, 2.5 W/mK, 42 kV/mm, 10¹⁴ Ω·cm) | $2–15 | stock or 47 days (Silmid) |
| 3 | GAP PAD HC 3.0, 0.020" | **GPHC3.0-0.020-02-0816** sheet, hand-cut 32 × 22 | $8–16 | stock, or a 10-week backorder (conflicting snippets) |
| 4 | Spreader bar | Online CNC, spec in §4 | EST $25–60 each at qty 7 (no public price; instant quote needed) | 3–10 working days (published lead-time options) |
| 5 | Comb spring | **Custom.** No off-the-shelf multi-device clamp fits (§5). Spec in §5. | EST $15–40 each at qty 7 (RFQ) | 2–4 weeks (EST, spring shop RFQ) |
| 6 | FR-4/G-10 strip 3 mm | 1/8" G-10 sheet or waterjet-cut strips; metric 3.0 mm needs an EU source | < $5 per stack | stock / 2–4 days |
| 7 | M4 screws + serrated washers | Commodity | < $1 per stack | stock |

---

## 1. AlN insulator

### 1.0 Option A: per-device catalogue insulators (requested first). Verdict: **does not fit the approved stack**

**What the catalogue offers.** Every distributor-stocked TO-247 ceramic insulator I found is **alumina**, not AlN, and is far smaller than the stack needs.

| Part | Maker | Material | Size (mm) | t (mm) | k (W/mK) | Breakdown | Hole | Stock / price | Source |
|---|---|---|---|---|---|---|---|---|---|
| AOS 247 | Fischer Elektronik | Al₂O₃ | 20 × 23 | 1.0 | 9.0 (Digi-Key listing) or 25 (reseller) — conflicting | 10 kV/mm (listing) | listed as wafer; hole not confirmed | Digi-Key "In-Stock: 1,000" (SNIPPET, unverified) | https://www.digikey.com/en/products/detail/fischer-elektronik/AOS-247/26111281 (403); https://www.distrelec.be/en/aluminium-oxide-disc-fischer-elektronik-aos-247/p/17559975 (SNIPPET) |
| AOS 218/247 | Fischer Elektronik | Al₂O₃ | 25 × 21 | 1.5 | ~25 (listing) | — | — | not read | https://www.distrelec.nl/en/aluminium-oxide-disc-to-218-to-247-fischer-elektronik-aos-218-247/p/17559972 (SNIPPET) |
| 4180G | Boyd (Aavid) | Al₂O₃ | 23.24 × 18.80 | 2.03 | 15.06 (listing) | not published in listing | for TO-218/247/3P (hole status to confirm) | Digi-Key 4180G (403); Future Electronics page timed out | https://www.digikey.com/en/products/detail/boyd-laconia-llc/4180G/1625664 (SNIPPET) |
| 5061-00581C | QuickCool (Conrad) | ceramic, 25 W/mK | 20.5 × 17.5 | 1.5 | 25 | — | — | not read | https://www.conrad.com/en/p/quickcool-5061-00581c-insulating-washer-l-x-w-20-5-mm-x-17-5-mm-suitable-for-to-247-1-pc-s-180978.html (SNIPPET) |
| TO-247 ceramic sheet, with Ø3.7 hole or without | Xiamen Innovacera | Al₂O₃ **or AlN** | not published (TO-220 version 14 × 20 × 1) | not published | — | — | both | manufacturer, RFQ only | https://trends.directindustry.com/xiamen-innovacera-advanced-materials-co-ltd/project-99777-1173358.html (SNIPPET) |

I found **no distributor-stocked AlN TO-247 insulator** from Fischer, Boyd/Aavid, Kyocera, CoorsTek or AMEC Thermasol. Innovacera makes one to order but publishes no size. There is **no standard ceramic insulator for the GBJ (BR1)** package at all.

**Fit against the stack geometry (CALC, from RECOMMENDATION §1 and §4.1):**

1. **Height (z) fails for every catalogue part.**
   - The tile stands on the board (foot at z ≈ 0.2) and must reach tab-metal top (≤ 25.49 mm) + 6.5 mm = **≥ 32 mm**.
   - The largest catalogue insulator is 25 mm. Its top would sit at z ≈ 25.2, which is *below* the top of the tab metal.
2. **Width (x) cannot reach 6.5 mm overhang at all.**
   - The FETs stand on an **18 mm pitch with 2 mm body gaps** (Q5|Q6, Q3|Q2). A per-device insulator can be at most ≈ 18 mm wide.
   - The "≈ 29 × 34 mm" target in the request is therefore geometrically impossible for Q5, Q6, Q3 and Q2. 20 mm (AOS 247) and 23 mm wide parts already overlap the neighbour.
3. **Inter-device joints need wide pedestal relief grooves.**
   - This uses the §4.1 tile-joint method: path = (tab-metal edge → joint) + tile thickness + (joint → groove edge) ≥ 8.0 mm, with plastic margin (E − E1)/2 ≥ 0.675 mm.

   | Joint | Body gap | Groove width needed, 2.0 mm tile | Reaches under tab metal | Same, 1.0 mm tile |
   |---|---:|---:|---:|---:|
   | Q5 \| Q6 | 2.00 | 8.65 mm | **2.65 mm** each side | 10.65 mm, 3.65 mm under |
   | Q6 \| Q3 | 6.10 | 4.55 mm (the approved 5 mm groove) | 0 | 6.55 mm, 0 |
   | Q3 \| Q2 | 2.00 | 8.65 mm | **2.65 mm** | 10.65 mm, 3.65 mm |
   | Q2 \| BR1 | 3.55 | 7.10 mm | 1.10 mm (Q2 side) | 9.10 mm, 2.10 mm |

   Each FET would lose about 2.65 mm of its ≈ 13 mm tab-metal width from pedestal contact, roughly 20 % of the area. The 1-D model gives that area no credit.
4. **Holed parts are excluded.**
   - Through a hole, the path from tab metal to PE is only the ceramic thickness (1–2 mm).
   - Restoring 8 mm would need a pedestal counterbore of about Ø15.6 mm under every hole. That removes contact right over the die.
5. **1.0 mm and 1.5 mm parts fail on two counts.**
   - **Compliance:** they are not reinforced by thickness (cl. 29.3.1 needs ≥ 2 mm). They would need the lab's 29.3.3 route.
   - **Geometry:** they don't fill the board's 1.835 mm tab offset. The PE pedestal face then moves about 0.8 mm over the board, toward the leads, which is the RECOMMENDATION §3 "thin film" problem.

**Thermal, per FET.** CALC uses the same assumptions as `stack_calc.py`:
- tab area 151–240 mm², 1-D through the ceramic with no spreading credit;
- **two** grease interfaces, optimistic = TC-5622 0.06 °C·cm²/W, conservative = TIC 1000A proxy;
- Ts 64.7 °C, LS loss 7.45 W.

| Insulator | Ceramic alone (°C/W) | Rcs optimistic | Rcs conservative | ≤ 0.7 (D-36) at conservative | Tj LS (cons) |
|---|---|---|---|---|---|
| AlN 1.0 mm, k 150 | 0.028–0.044 | 0.078–0.123 | 0.372–0.590 | yes | 71.2 °C |
| AlN 1.0 mm, k 170 | 0.024–0.039 | 0.074–0.118 | 0.368–0.585 | yes | 71.1 °C |
| **AlN 2.0 mm, k 150** (approved) | 0.056–0.088 | 0.106–0.168 | 0.399–0.634 | **yes** | 71.5 °C |
| AlN 2.0 mm, k 170 | 0.049–0.078 | 0.099–0.157 | 0.393–0.624 | yes | 71.4 °C |
| Al₂O₃ 1.0 mm, k 24 (stack_calc EST) | 0.174–0.276 | 0.224–0.355 | 0.517–**0.822** | **no** | 72.9 °C |
| Al₂O₃ 1.0 mm, k 9 (AOS 247 Digi-Key listing) | 0.463–0.735 | 0.513–0.814 | 0.807–1.281 | **no** | 76.3 °C |
| Al₂O₃ 2.03 mm, k 15 (4180G listing) | 0.564–0.896 | 0.614–0.975 | 0.908–1.442 | **no** | 77.5 °C |

**Option A conclusion:**
- **Catalogue parts:** none fits. Every one is too small in z, and alumina also fails D-36 at the conservative end.
- **Per-device custom AlN:** a custom per-device tile is possible only by giving up about 20 % of the contact under four FETs to wide relief grooves. That is a change to the approved §4.1 geometry, not a sourcing substitution.
- **DFM middle ground to put to the owner:**
  - Keep tile A (Q5 + Q6) and split tile B at the Q2|BR1 gap into **B1 (Q3 + Q2, ≈ 38.6 × 31.8 mm)** and **C (BR1, ≈ 35.2 × 31.8 mm)**. Every tile is then ≤ 43 mm, so all three cut from 2" stock.
  - The cost is a 7.1 mm groove at x ≈ 74.3–81.4. That takes 1.1 mm of contact under Q2's tab-metal edge (CALC above). It needs an owner decision and a §4.1 path re-check; I have not adopted it.

### 1.1 Option B: custom shared tiles (approved geometry)

**Size needed:**
- **Tile A:** 42.75 × 31.8 × 2.00 ± 0.05 mm.
- **Tile B:** 73.75 × 31.8 × 2.00 ± 0.05 mm.
- **Finish:** both faces lapped, flatness ≤ 0.03 mm, 0.3 mm edge chamfer, no holes, k ≥ 150 W/mK.
- **Quantity:** 7 of each (5 boards + 2 spares).

**Does a larger tile work?** The rule is overhang ≥ 6.5 mm beyond the tab metal, plus the fixed joint and fixed thickness.

| Direction | Can it be larger? | Limit |
|---|---|---|
| Thickness | **No.** It must stay 2.00 ± 0.05; the 2.04 mm stack fills the 1.835 mm tab offset (§3). | Stock 2.032 mm (0.080") lapped plate is inside tolerance. |
| Height (z, up from the board) | **Yes, a little.** Taller only adds overhang. | The comb mounts on the bar at z ≈ 40–45 and the bar ends at z ≈ 55. Keep the tile top ≤ z ≈ 36–38 so the comb base clears it. **A 50.8 mm square used as-is does not fit** (it would reach z ≈ 51). |
| Tile A outer end (x < −4) | Yes, a few mm. | The bar ends at x −8; an extra overhang there is harmless. Check the enclosure. |
| Tile B outer end (x > 113) | Yes, a few mm. | Enclosure, plus the moved plenum end cap. Check in R26 CAD. |
| Joint end (x 38.75 / 39.25) | **No.** | The joint must stay centred in the 6.1 mm Q6–Q3 gap over the 5 mm groove (§4.1, 8.0 mm path). |

So no catalogue square can be used as-is. Tile B (73.75 mm) needs a plate ≥ 74 mm, and both tiles must be cut to height.

**Nesting.** A 114.3 mm (4.5") plate yields 3 × tile B stacked (96.0 mm with 0.3 mm kerf) plus 2 × tile A turned 90° in the 40.5 mm strip (85.8 mm). That is 3 B + 2 A per plate (CALC). A 114.0 mm plate gives the same yield. **7 stacks need 4 plates:** 7 B take 3 plates, and the 7 A take the 4th plate plus the spare strips.

**Supplier candidates:**

| Supplier | What's public | 2 mm? | Lapped / flatness | MOQ / price | Lead | Source |
|---|---|---|---|---|---|---|
| **Valley Design** (US) | Stock AlN-110: 4.5" sq × 0.080" (114.3 × 2.032 mm), **lapped both sides (25 µ" Ra)**, 170 W/mK. AlN-144: 2" sq × 0.080" LBS, 170 W/mK. AlN-115: 4.49" sq × 0.080" ± 0.0005" LBS. Offers dicing of AlN. | **yes (2.032)** | LBS. Thickness ±0.001–0.002" default. Flatness not published; ask. | "CALL"; no public price or MOQ | not published | https://valleydesign.com/aluminum-nitride , https://valleydesign.com/aluminum-nitride/stockpage/ |
| **Almath Crucibles** (UK) | SUB1141142ALN, 114 × 114 × 2 mm, 170 W/mK (210 W/mK on request). "Can be cut to smaller sizes on request." Pack sizes 1 / 5 / 10. | yes | finish and flatness **not stated** (probably as-fired, so lapping needed) | **from £232.00 excl. VAT per plate**; "not always held in stock" | ask | https://almathcrucibles.com/product/sub1141142aln/ |
| **Precision Ceramics** (UK) | CeramAlum PCAN1000, 170 W/mK. Fully sintered AlN is diamond-ground to tight tolerance. | custom | grinding / lapping in house | RFQ | RFQ | https://precision-ceramics.co.uk/materials/ceramalum/ |
| **Kyocera Fineceramics Europe** | AN216A (the grade cited in the spec): 150 W/mK, 14 kV/mm, εr 8.6, flexural 310 MPa (datasheet 2023-04-03). Custom parts via sales. | custom | RFQ | RFQ | RFQ | https://www.kyocera-fineceramics.de/fileadmin/user_upload/Download/werkstoffdatenblaetter/aluminiumnitrid/Kyocera_Fineceramics_Europe_AN216A.pdf |
| **Xiamen Innovacera** (CN) | AlN panels: thickness 0.25–2 mm, length 50.8–152.4 mm, width 25.4–127 mm. Tile A at 42.75 mm long is under their stated minimum length; ask. | yes (max 2 mm) | RFQ | RFQ | RFQ | https://www.directindustry.com/prod/xiamen-innovacera-advanced-materials-co-ltd/product-99777-2854904.html (SNIPPET; page 403) |
| Stanford Advanced Materials (US/CN) | AlN substrate TDS NR0916: 0.25–1.5 mm standard, 180–230 W/mK. Custom machined AlN parts offered. | outside std range; ask | polished options | RFQ only | RFQ | https://samaterials.com/tds/1718614952-NR0916.pdf , https://www.samaterials.com/aluminum-nitride/2081-aluminum-nitride-custom-machined-parts.html |
| Maruwa (JP) | AN-170/200/230 grades. Standard large sizes are φ180–380 × 1–10 mm t (another product line); custom sizes. | via custom | RFQ | RFQ | RFQ | https://www.maruwa-g.com/e/products/ceramic/000314.html |
| CoorsTek | Only a 2013 AlN 170 W/mK substrate announcement; no current plate datasheet found. | unknown | — | — | — | https://eepower.com/new-industry-products/coorstek-introduces-high-performance-aluminum-nitride-substrates/ |

**Recommended RFQ list:** Valley Design (stock LBS 2.032 mm plus dicing, the shortest path), Almath (public plate price; cut and lap), Precision Ceramics (diamond grinding, UK), and Innovacera (low-cost check).

**Price estimate (EST):**
- **Material:** 4 Almath plates is £928 for 7 stacks, ≈ £133 per stack before cutting.
- **Processing:** dicing, chamfer and (if needed) lapping typically add a setup charge of a few hundred £/$ at this quantity. Expect **≈ £150–250 per stack all-in at qty 7** until quotes arrive.
- **Basis:** this is an estimate built on the one public price, Almath. It is not a quote.

### 1.2 AlN RFQ text, ready to send

> **Subject:** RFQ: aluminium nitride insulator tiles, 2.0 mm, lapped, 2 sizes, qty 7 + 7
>
> Hello,
>
> Please quote the following aluminium nitride (AlN) parts. They are thermal insulators between power semiconductors and an aluminium heatsink in a mains appliance.
>
> **Material:** sintered AlN, thermal conductivity ≥ 150 W/m·K (170 W/m·K grade preferred). Please state the grade, its typical dielectric strength (kV/mm) and its flexural strength, and attach the material datasheet.
>
> **Part 1, "Tile A":** 42.75 × 31.80 mm, thickness 2.00 ± 0.05 mm. **Qty 7.**
> **Part 2, "Tile B":** 73.75 × 31.80 mm, thickness 2.00 ± 0.05 mm. **Qty 7.**
>
> **Both parts:**
> - Length and width tolerance ± 0.10 mm; corners square within 0.1 mm.
> - **Both large faces lapped.** Flatness ≤ 0.03 mm over the whole face; parallelism ≤ 0.03 mm; Ra ≤ 0.8 µm (finer acceptable).
> - **0.3 mm × 45° chamfer** (or R0.3) on all edges of both faces; no sharp edges.
> - **No holes,** no metallisation.
> - **Edge chips:** none > 0.3 mm on the face or 0.5 mm along an edge. No cracks (please state your inspection method: visual at 10× or dye penetrant).
> - Clean, dry and free of lapping residue. Packed individually with separators.
> - A stock 0.080" (2.032 mm) lapped-both-sides plate cut to size is acceptable if the flatness above is met.
>
> **Please quote:**
> 1. Unit price and any setup/NRE at **7 + 7**, **50 + 50** and **500 + 500** pieces.
> 2. Lead time from order.
> 3. Thickness and flatness inspection data per part (or per lot), and whether you can supply a C of C.
> 4. Shipping cost to [owner address / country].
> 5. Whether you would recommend any change to make the parts easier to manufacture (e.g. tolerance, chamfer type).
>
> A drawing can be supplied on request. Thank you,
> [Name, company, address, phone]

---

## 2. Thermal compound (non-conductive, with published dielectric data)

**PDFs:** every figure below was read from the TDS PDFs in `sub-compound/pdfs/` (CITED). Distributor prices are SNIPPET unless marked.
**Requirement:** non-curing, metal-oxide or ceramic filler, published dielectric strength **and** volume resistivity, k ≥ ~2.5 W/mK.

| | **A. Electrolube HTCP (recommended)** | B. DOWSIL TC-5026 | C. 3M TCG-2035 |
|---|---|---|---|
| Part number / pack | **HTCP20S** (20 ml syringe); HTCP35SL (35 ml); HTCP02S (2 ml) | TC-5026, 1 kg only found | no orderable pack found |
| k | **2.5 W/mK** guarded hot plate; 1.7 W/mK heat-flow (calculated) | 2.9 W/mK | 4.1 W/mK (ASTM D5470 mod.) |
| Dielectric strength | **42 kV/mm** (method not stated) | 227 V/mil = 8.9 kV/mm | 4700 V/mm (ASTM D149) |
| Volume resistivity | **1 × 10¹⁴ Ω·cm** | 5.9 × 10¹¹ Ω·cm | 1.36 × 10⁹ Ω·cm at 1 kHz (ASTM D257) |
| Filler | "Powdered metal oxides", non-silicone synthetic oil | "heat-conductive metal oxides" in silicone | "Inorganic thermally conductive filler", non-silicone |
| Temperature | −50 … +130 °C | not in TDS | not in TDS |
| TDS | Electrolube HTCP TDS (no revision or date printed; Farnell copy), p.1 | Form No. 11-3435-01 A (© 2017), electrical p.2 of 3; "not intended for … specifications" | "Technical Data, August 2017", p.1; preliminary |
| TDS URL | https://www.farnell.com/datasheets/2688309.pdf , https://www.farnell.com/datasheets/2876217.pdf | https://www.galindberg.se/storage/5A5B5235123B4DF5FD845AC29E15E94E49D91802EE47241E01F2BC72012B55E7/a6f9ac323a0443af9ee2fd90d95e44f8/pdf/media/4d82eaa4e8144fd2b251b06a957ee0db/DowSil%20TC-5026.pdf | https://multimedia.3m.com/mws/media/1439237O/3m-thermally-conductive-grease-2035.pdf |
| Source, stock, price | ConRo: **£33.40 ex VAT** per 20 ml, min. 3, stock date "02 Dec 2025" (stale) https://www.conro.com/lubricants/greases/Electrolube-HTCP20S-Heat-Transfer-Compound-Plus-20ml ; Silmid £31.86, out of stock, 47-day lead, multiples of 10 https://silmid.com/coatings/specialty-coatings/electrolube-heat-transfer-compound-plus-20ml-syringe ; Octopart $23.44 https://octopart.com/part/electrolube/HTCP20S ; Farnell UK dp/634920 (403) https://uk.farnell.com/electrolube/htcp20s/heat-transfer-htcp-non-silicone/dp/634920 | Farnell IE 1 kg (403) https://ie.farnell.com/dow/tc-5026-kg-1kg-2ctn/thermal-joint-compund-gry-1kg/dp/4354381 ; Ellsworth 1 kg (no price) | — |

**Choose HTCP.**
- **Electrical:** it is the only candidate with high resistivity (10¹⁴ Ω·cm) and a high dielectric figure, and its filler is stated to be metal oxide. Squeeze-out on the tile edges is then a non-issue electrically, though RECOMMENDATION still says wipe it off.
- **Thermal check (CALC):**
  - At a 0.05 mm bond line with k 1.7 W/mK, one interface is 0.29 °C·cm²/W, i.e. 0.12–0.19 °C/W per TO-247.
  - That lies **inside** the conservative stack_calc assumption (0.17–0.27 per interface). The 2 mm AlN Rcs therefore stays ≤ 0.634 °C/W conservative, which meets D-36.
  - At a 0.02 mm bond line it is 0.05–0.08 °C/W per interface.
- **Quantity:** one 20 ml syringe is far more than 7 stacks need (≈ 4 × 25 cm² × 0.05 mm ≈ 0.5 ml per stack). Budget 1 syringe, or 3 if ConRo's minimum applies.
- **Rejected:**
  - **Laird Tgrease 2500:** 3.8 W/mK, 3.5 × 10¹² Ω·cm, but **no dielectric strength** published.
  - **Tgrease 880:** this TDS gives 1.2 W/mK.
  - **Electrolube HTCPX:** 3.4 W/mK, 42 kV/mm, but sold as a 700 g cartridge only.
  - **Fischer WLPK:** no TDS with electrical data found. Fischer WLPF is "electrically non-conductive but no insulator", with no numbers.
  - **Henkel TIC/TGR 4000:** conductive filler.
  - **DOWSIL TC-5622:** no dielectric data in its TDS. Its hold stays, unless Dow answers.
  - **Fallback:** Multicomp Pro non-silicone grease: 2.0 W/mK, 13 kV/mm (D149), 10¹⁴ Ω·cm (D257), TDS V1.0 22/11/19 https://www.farnell.com/datasheets/2874879.pdf . It is below the 2.5 W/mK target.

---

## 3. GAP PAD HC 3.0, 0.020" (BR1)

- **Current name:** BERGQUIST GAP PAD TGP HC3000 ("known as GAP PAD HC 3.0").
- **Sheet part number:** **GPHC3.0-0.020-02-0816** (0.020", fibreglass-reinforced, 8" × 16" sheet). The format is confirmed in the Henkel selection guide https://www.farnell.com/datasheets/4788148.pdf .
- **TDS:** Henkel, Nov 2018 https://datasheets.tdx.henkel.com/BERGQUIST-GAP-PAD-TGP-HC3000-en_GL.pdf (CITED):
  - 3.0 W/mK (D5470);
  - **5000 Vac** dielectric breakdown (D149);
  - 1 × 10¹⁰ Ω·m (D257);
  - εr 6.5;
  - −60 … 200 °C;
  - UL94 V-0.

| Source | Part | Stock / price | Lead | URL |
|---|---|---|---|---|
| Digi-Key | GPHC3.0-0.020-02-0816 (BER366-ND) | **Conflicting SNIPPETs:** 29 in stock at $64.33 (1) / ≈ $57.40 (16); **or** out of stock with a 10-week lead (digikey.ca/.mx). Aggregator: $109.39 (1). | ? | https://www.digikey.com/en/products/detail/bergquist/GPHC3-0-0-020-02-0816/5253848 (403) ; https://zenode.ai/parts/85qfg0aycy |
| Mouser | 0.020" listing not confirmed (one snippet implied 216 in stock) | — | — | browser agent |

**Cut size:** 7 × 32 × 22 mm ≈ 5,000 mm² out of an 82,000 mm² sheet, so **buy one sheet and cut with a scalpel and steel rule**. No small-sheet or die-cut part was found; at this quantity a converter is not worth it. The pad is tacky on both sides with liners, so cut through the liners.

---

## 4. Spreader bar ("pedestal"): machining spec

**Drawing basis:**
- **Board coordinates:** from RECOMMENDATION §4 and §4.2. The bar spans board x −8 … 109 and z 8.0 … 55 (top per the §4 cross-section; §4.2 says ≥ 48). Its face is at y −0.205, its back at y −8.0, and it is 7.8 mm thick.
- **Part datum (below):** X from the left end, Z from the lower (board-side) edge, Y = 0 at the contact face.

**One-page spec for an online machine shop:**

```
PART:        M11 spreader bar ("pedestal"), Temper native-21 power stage
QTY:         7
MATERIAL:    Aluminium 6061-T6 (alt. 6082-T6 / EN AW-6082 T651). Material cert (C of C) requested.
STOCK SIZE:  117.0 x 47.0 x 7.8 mm finished (X x Z x Y)
GENERAL TOL: ISO 2768-mK unless stated

DIMENSIONS / TOLERANCES
  Length X            117.0 ± 0.1
  Height Z             47.0 ± 0.1
  Thickness Y           7.80 ± 0.05      (sets the PE face position; critical)
  FACE F (contact face, Y=0, full 117 x 47):
      flatness          0.03 mm  over the full face            (critical)
      roughness         Ra ≤ 0.8 µm  (fly-cut / face-milled, or surface-ground)
  FACE R (back face, Y=7.8, mates greased to heatsink):
      flatness          0.05 mm; Ra ≤ 1.6 µm; parallel to F within 0.05
  RELIEF GROOVE in face F:
      width 5.0 +0.2/-0 mm, centred at X = 47.0 (X 44.5 … 49.5)
      depth 1.5 ± 0.2 mm
      runs from Z = 0 (open at the lower edge) to Z = 26.0 (board z 34, 2 mm above tile top), end radius R2.5
      groove edges: break 0.2 max
  LOWER EDGE of face F (Z = 0): chamfer 0.3–0.5 x 45°, no burr (creepage end point;
      do not exceed 0.5 mm)
  COMB MOUNT: 3 x M4x0.7 tapped THROUGH, axis ⟂ face F, at Z = 34.0 ± 0.1 (= 42 mm above board),
      X = 4.0, 47.0, 85.8 (± 0.1). Countersink 0.3 x 90° both sides. Holes must not raise burrs on face F
      (flatness applies after tapping).
  SINK MOUNT: 3 x M4x0.7 tapped BLIND from face R, thread depth 5.0 (drill 6.0 max; ≥ 1.5 mm wall
      to face F), at Z = 17.0, X = 20.0, 66.0, 105.0. *** Positions to be confirmed against the R26 sink
      drawing before release. ***
  All other edges: break 0.2–0.5 mm, deburr.

FINISH
  NO anodise (the bar must stay electrically bonded to PE). Bare, or clear trivalent chromate
  conversion (MIL-DTL-5541 Type II Class 3 / RoHS) acceptable. No paint, no bead blast on faces F or R.
  Clean, oil-free; pack each part face F protected (film or foam) — scratches on F > 0.01 mm deep reject.

INSPECTION
  Report per part: thickness at 4 corners + centre; flatness of F (surface plate + indicator or CMM);
  Ra of F (one reading). Thread gauge check on all M4.
```

**Notes for the owner:**
- **Mounting-hole positions are provisional.** The comb holes sit at board x −4.0, 39.0 and 77.8, i.e. off the left end, in the Q6–Q3 gap and in the Q2–BR1 gap. That keeps them between fingers and clear of every tab. The sink holes depend on R26.
- **Groove length:** the groove stops at bar Z 26 (board z 34), 2 mm above the tile top (z 32). The comb base (board z 36–48) sits clear of it.
- **Indicative price and lead.** No vendor publishes a no-upload price for this part:
  - **Protolabs:** standard CNC 3 days, "flexible" option 6–12 days. https://www.protolabs.com/en-gb/resources/blog/cnc-flexible-lead-time-option-save-costs-with-longer-lead-times/
  - **Xometry:** expedite 3–4 business days, no setup fees or minimums (FAQ). https://www.xometry.com/blog/answers-to-most-frequently-asked-questions
  - **PCBWay:** old blog says CNC "starting from $50". https://www.pcbway.ru/blog/News/PCBWay_New_Services__3D_printing_and_CNC_machining.html
  - **JLCCNC:** nothing published.
  - **EST:** **$25–60 per bar at qty 7** from a CN shop (JLCCNC/PCBWay) plus shipping, $60–150 per bar from a US/EU instant-quote shop. Lead 5–15 days.
  - **Flatness check:** the 0.03 mm flatness on a 117 × 47 × 7.8 mm plate is achievable by face milling after stress relief, but confirm it is quotable as a noted tolerance. Some instant-quote tiers only hold ISO 2768-m.

---

## 5. Comb spring clamp

### 5.1 Off-the-shelf check. Verdict: none fits

| Candidate | Force | Mount | Why not | Source |
|---|---|---|---|---|
| Fischer THFU 1 | 60 N ± 5 (SNIPPET) | Snaps into Fischer SK/LAM heatsink profiles | Single device; needs a matching extrusion slot; metal touches the package; at the bottom edge of 60–80 N | https://sg.element14.com/fischer-elektronik/thfu-1/clip/dp/1892310 (403) |
| Fischer THFU 3 | 50 N ± 5 (SNIPPET) | Snaps into SK 480–SK 681, LAM | < 60 N; profile-specific | https://ie.farnell.com/fischer-elektronik/thfu-3/clip/dp/1892352 (403) |
| Fischer THFM 1 | not stated | Screw mount, single device | Single device; force not published. 5.50 SEK incl. VAT, 60 in stock (CITED) | https://www.electrokit.com/en/retaining-clip-for-to-220-to-247-etc.-screw-mount |
| Fischer THFM 20 / THFK 36 | not stated | Multi-device retaining spring (SNIPPET: THFM 20 holds 1–10 TO-247/264; THFK 36 two devices) | **Closest candidate; data not readable.** It must reach over an ≈ 10 mm-deep stack (package 5 + strip 3) from a bar face, at ≥ 60 N per device. Browser agent to check the Fischer datasheet. | search snippet only |
| Boyd/Aavid MAX CLIP (MAX03NG …) | "standard" | Clips into MAX CLIP heatsinks only | Profile-specific | https://www.digikey.com/en/products/detail/boyd-laconia-llc/MAX03NG/1625437 (403) |
| Ohmite CLA-T247-21E | cam clip | Ohmite C-series sinks only | Profile-specific | https://www.digikey.at/en/products/detail/ohmite/CLA-T247-21E/4211081 (403) |

None gives 100–150 N on the GBJ. **Recommend the custom comb below.** Ask the browser agent to read the Fischer THFM 20 sheet before committing; it is the only plausible off-the-shelf multi-device spring.

### 5.2 Custom comb spring specification

```
PART:      M11 comb clamp spring, Temper native-21. QTY 7.
MATERIAL:  Stainless spring steel 1.4310 (X10CrNi18-8, AISI 301), EN 10151 strength C1300
           (Rm 1300–1500 MPa), cold-rolled strip, t = 1.20 ± 0.03 mm.
           Alternative: two laminated layers of 0.79 mm (0.031") 301 full-hard (same rate; see table).
FORM:      Laser-cut or wire-EDM blank (no burr > 0.05 mm, edges deburred/tumbled), then press-brake formed.
           Bend lines across the rolling direction; inside bend radius ≥ 2 t. Stress-relieve 1 h at 400 °C
           after forming (standard for 1.4310) — raises relaxation resistance.
GEOMETRY:  - Base flange 121 x 12 mm, lies on the bar face F above the tiles (bar Z 28…40),
             3 x Ø4.5 holes at bar X 4.0, 47.0, 85.8 (match the bar). Fastened with M4 + serrated washer.
           - Standoff: base is bent 90° outward to clear the tile (2.0 mm), the package (≈ 5.0 mm) and
             the strip (3.0 mm). Outward leg length ≈ 11–12 mm (y −0.2 → ≈ +11), then bent 90° down.
           - 5 fingers hang down from the standoff, free length L ≈ 35 mm (bend to contact line):
               Q5, Q6, Q3, Q2: width b = 14 mm, centred on the device x (board x 9.95, 27.95, 50.05, 68.05)
               BR1: width b = 26 mm, centred at board x 94.4
             Slot between fingers ≥ 2 mm, slot root radius ≥ 1 mm.
           - Each finger ends in a formed transverse rib / dimple (contact line) at board z ≈ 16
             (centre of the strip, strip spans z 9–23). Contact on the FR-4 strip only.
PRELOAD:   Free shape set so that each finger is deflected δ = 2.6 mm when assembled on the nominal stack
           (tile 2.00 + package 5.0 + strip 3.0).
           Target force: 70 N per TO-247 finger (accept 60–82 N over δ 2.2–3.0 mm);
                         ≈ 130 N on the BR1 finger.
VERIFY:    Load-deflection test of 2 parts on a fixture: report F at δ = 2.2 / 2.6 / 3.0 mm per finger.
FINISH:    Passivated (ASTM A967 / citric) — no plating, no coating.
```

**Sizing (CALC).** Cantilever, E = 193 GPa:
- **Stiffness:** k = 3EI / L³. Bending stress σ = 3Etδ / (2L²).

| Variant | b (mm) | t (mm) | L (mm) | k (N/mm) | F at δ 2.6 | σ at 2.6 / 3.0 mm | σ / Rm(1300) |
|---|---|---|---|---|---|---|---|
| TO-247 finger, single 1.2 mm | 14 | 1.2 | 35 | 27.2 | **71 N** | 737 / 851 MPa | 0.57 / 0.65 |
| BR1 finger, single 1.2 mm | 26 | 1.2 | 35 | 50.6 | **131 N** | 737 / 851 | same |
| TO-247 finger, 2 × 0.79 mm laminated | 14 | 2 × 0.79 | 29 | 27.3 | 71 N | 707 / 816 | 0.54 / 0.63 |

- **Force band:** the low rate (≈ 27 N/mm) keeps 60–82 N across ± 0.4 mm of stack tolerance (tile ± 0.05, package A ± 0.1, strip ± 0.1–0.18, forming ± 0.15).
- **1/8" strip instead of 3.0 mm:** a 3.175 mm strip adds 0.175 mm of deflection, i.e. +4.8 N. That stays in band.
- **The standoff leg adds compliance** that the formula ignores. **Tune the free shape on the first article with the load cell (bench plan).**

**Safety-relevant layout rules for the drawing** (the comb is PE metal):
- No part of the comb may sit within 8.0 mm creepage or 2.0 mm clearance of HOT metal, except through the 3 mm strip.
- **Paths for this layout** (EST from the §1 package geometry; **confirm in R26 CAD**):
  - **Down:** contact at z 16 → strip front to its lower edge (7 mm) → round the 3 mm edge → package front → lead exit at z ≈ 4 (≈ 5 mm). That is **≈ 15 mm**.
  - **Up:** tab-metal top edge (z 25.5, y 1.835) → package top (≈ 5 mm) → strip top edge (3 mm) → strip front to the contact (7 mm). That is **≈ 15 mm**.
  - **Clearance:** finger metal (y ≈ 10–11) to the tab-metal top edge is ≈ 9 mm.
  - All three are ≥ 8.0 / 2.0 mm, provided the finger stays in front of the strip and its contact line stays ≥ 6 mm from the strip's long edges.

**Small-run spring sources:**

| Shop | Fit | Source |
|---|---|---|
| Gutekunst Federn (DE) | Custom leaf, stamped and bent springs; stocks 1.4310 catalogue springs. RFQ. | https://www.gutekunst-federn.de |
| Xometry sheet metal | Lists 301 stainless spring temper in 0.004–0.031" only (SNIPPET), so the 2 × 0.79 mm laminated variant applies. | https://www.xometry.com/sheet-cutting/standard-sheet-sizes/ |
| SendCutSend | No 301. 1075 blue-temper spring steel 0.38 mm only; stainless 304/316 (not spring). **Not suitable.** | https://sendcutsend.com/materials/stainless-steel/ |
| JLCCNC sheet metal | SS201, SS304, 5052; no 301. **Not suitable** unless they quote 1.4310 by RFQ. | https://jlccnc.com/materials/sheet-metal |
| Lee Spring, Smalley, Newcomb Spring, Peninsula Spring (US) | Custom flat-spring RFQ shops; not checked for price or MOQ. | to check |
| DIY route | McMaster 301 stainless sheet (several tempers) plus a local laser shop and press brake. | https://www.mcmaster.com/301-stainless-steel-sheets |

---

## 6. FR-4/G-10 pressure strip

**Cut size:**
- **Strip:** 117 × 14 × 3.0 mm, 7 pieces (board x −8 … 109, z 9 … 23).
- **Edges:** break all edges 0.3 mm.

| Source | Product | Thickness | Price / stock | Source |
|---|---|---|---|---|
| Rockwest Composites | G-10/FR-4 sheet 24" × 48" (also 12" × 24") | 1/8" (3.175 mm) | 24 × 48: **$170.99** each (1–5), 6 in stock (CITED) | https://www.rockwestcomposites.com/g10-125-2448.html |
| SendCutSend | G-10/FR-4 waterjet-cut parts, ±0.009" | 0.125" (no 3.0) | Instant quote after upload (not done). Min. part 1" × 2". 2–4 days production. | https://sendcutsend.com/materials/g10-fr4/ |
| McMaster-Carr | Yellow G-10/FR-4 sheet 12" × 24", 36" × 48" | 1/8" | not readable (JS) | https://www.mcmaster.com/grade-g-10/fr4-garolite-bars |
| eBay.de/UK sellers | FR-4 sheets 100–400 × 100–300 mm | **3.0 mm** | EU shipping only | https://www.ebay.de/itm/146503119103 |

**Buy:** one 12" × 24" × 1/8" G-10/FR-4 sheet (yields 7 strips with > 2× spare), or 7 waterjet strips. A true 3.0 mm part needs an EU source (RS/Farnell/Misumi; browser agent to check).

**CTI and RTI are not confirmed.**
- **Temperature:** American Epoxy's G-10/FR-4 sheet gives a temperature index of 140 °C (https://files.elfsight.com/storage/ed815d9f-fbd1-40b2-b741-a91f91476f52/1776341e-c258-41f0-8fd9-5aaf28b9a48f.pdf). Rockwest lists 140 °C continuous and UL94 V-0.
- **CTI:** none of the readable sheets gives a CTI. Ask the vendor for a **UL yellow card (QMFZ2)** showing RTI elec ≥ 130 °C and **PLC 0–3 (CTI ≥ 175 V)**. Glass-epoxy laminates are normally PLC 3 (175–249 V) or better, but this must be confirmed per grade.

---

## 7. Hardware (per bar: 3 × M4 for the comb + 3 × M4 for the sink; × 7)

| Item | Spec | Source / price | Source |
|---|---|---|---|
| Comb screws | M4 × 10, ISO 7380 or ISO 4762, A2-70 or 8.8 zinc. 7.8 mm bar, through-tapped: base 1.2 + washer 0.6 + ≥ 6 engagement → **M4 × 10**. | Commodity; any distributor. No part number read (McMaster/Misumi/Bossard not readable). | — |
| Sink screws | M4 × (sink base thickness + 5), per R26 | — | — |
| Serrated washers | DIN 6798 A (external tooth) M4, A2 or A4 | SFS: CHF 1.20 per 100, MOQ 1000 (CITED) | https://www.sfs.ch/CH/en/dl/p/135324 |
| Alternative | Nord-Lock NL4 (steel) wedge-lock pairs | $82.99 per 200 pairs (SNIPPET) | https://www.transcat.com/nord-lock-nl4-wedge-locking-washers-m4-id-0-17 |

**Need:** 42 screws and 42 washers for 7 bars. Buy packs of 50–100.

**Earthing note:** use the serrated washer under the comb screw head so that the comb is reliably bonded to PE through the bar. The sink-to-bar joint is greased, so it needs its own bonding path; the R26 drawing should show the PE bonding point.

---

## 8. Cost per stack (EST, qty 7)

| Item | Per stack (EST, from the cited figures) |
|---|---|
| AlN tiles A + B (cut + chamfer; lapped stock or lap) | **$190–320** (£150–250); Almath plate share alone £133 |
| HTCP compound | $2–15 (1–3 syringes over 7 stacks) |
| Gap pad (1 sheet over 7) | $8–16 |
| Spreader bar | $25–60 (CN CNC) / $60–150 (US/EU instant) |
| Comb spring | $15–40 (RFQ; small-run setup dominates) |
| FR-4 strip | $2–25 (12 × 24" sheet or waterjet strips) |
| Screws + washers | < $1 |
| **Total per stack** | **≈ $245–460 (CN machining), ≈ $280–550 (US/EU machining). Point estimate ≈ $350.** Lot of 7 ≈ $2.5k |

**Lead-time ranking (EST unless cited):**
1. **AlN tiles,** RFQ plus cutting/lapping: **3–6 weeks**. This is the **longest item and the critical path.** Send the RFQ first.
2. **Gap pad:** possibly a 10-week Digi-Key backorder (SNIPPET). Check stock now; if it is backordered, try Mouser or Arrow.
3. **HTCP compound:** Silmid shows a 47-day lead; the Farnell/ConRo stock state is unknown.
4. **Comb spring:** 2–4 weeks at a spring shop.
5. **Bar:** 3–15 days.
6. **FR-4 and hardware:** stock.

---

## 9. Browser-agent checklist (Digi-Key / Mouser / sites that blocked automation)

1. **Digi-Key GPHC3.0-0.020-02-0816 (BER366-ND):** live stock, price at 1 and lead time (the snippets conflict). Look for a 0.020" Mouser listing.
2. **Electrolube HTCP20S** at Farnell UK (dp/634920), Newark, RS, TME and Conrad: price, stock and lead. Also look for a dated HTCP TDS on electrolube.com that states the test methods for 42 kV/mm and 10¹⁴ Ω·cm.
3. **Fischer AOS 247 and AOS 218/247, Boyd 4180G** on Digi-Key: confirm size, hole and k. This is only to close option A on record; it doesn't change the verdict.
4. **Fischer THFM 20 and THFK 36 datasheets** (fischerelektronik.de): spring force per device, and whether either can mount on a bar face over a ≈ 10 mm deep package + strip stack. These are the only plausible off-the-shelf multi-device springs.
5. **Innovacera** TO-247 AlN sheet page: published sizes. Expected too small; confirm.
6. **Instant CNC quotes** for the bar at JLCCNC, PCBWay and Xometry. **The owner decides before any upload.** Confirm that 0.03 mm flatness and Ra 0.8 can be called out, plus the minimum charge and lead.
7. **Spring material:** whether 1.4310/301 C1300 at 1.2 mm (or 301 full-hard 0.031") is selectable at Xometry or JLCCNC sheet metal. Also the RFQ route at Gutekunst, Lee Spring and Smalley.
8. **FR-4:** a metric 3.0 mm sheet at RS, Farnell or Misumi, with a **UL yellow card** (RTI ≥ 130 °C, PLC/CTI ≥ 175 V) for the chosen grade. McMaster 1/8" G-10 part number and price.
9. **M4 × 10 A2 screws and DIN 6798 A M4 washers:** pack prices at McMaster, Misumi or Bossard.
10. **Almath:** stock and lead for SUB1141142ALN, and whether it is as-fired (it would then need lapping). **Valley Design:** whether AlN-110 or AlN-144 is in stock, and its flatness. Send the RFQ in §1.2 to Valley, Almath, Precision Ceramics and Innovacera. **The owner sends it; nothing has been sent.**

---

## Files

- `sub-compound/pdfs/`: TDS PDFs read for §2 and §3.
- `calc/per_device_calc.py` and `calc/per_device_calc.txt`: option A thermal and joint-creepage arithmetic (same assumptions as `m11/stack_calc.py`).
