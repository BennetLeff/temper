# Native-21 procurement check — 2026-10-09 UTC

[CSV](codex-procurement-2026-10-09.csv): 26 task lines, with two materially useful alternate-source rows (C21/C22 and C1/C2). Pages read between 05:21 and 05:33 UTC, corresponding to the evening of October 8 in America/Mexico_City.

18 lines have enough verified distributor stock for the specified buy quantities. Their extended-price subtotal is **$907.25 USD**, including the RS UK choke at an indicative USD conversion. Coilcraft direct has another stocked line, T1, for **$80.01**, giving **$987.26** for fully available distributor and direct lines. These are partial-BOM totals; they exclude taxes, tariffs, shipping and optional reeling fees.

- **NOT_FOUND:** C5/C6 — B32656G0275J000, exact Mouser listing but non-stocked and quote-only; no verified stock or public price. The task's TDK MOQ 360 was carried into the CSV and remains unconfirmed. R34 — RT0603BRD0710K6L, no exact authorized listing verified; distributor search results offered other resistance values.
- **LEAD_TIME over 8 weeks:** T2/T3 — 750320775, factory 16 weeks and Digi-Key incoming estimate March 17, 2027. C1/C2 — R463N410000N1M, Mouser MOQ 1 / 38 weeks, or Digi-Key MOQ 360 / 24 weeks. R77/R95/R110 — RT0603BRD076K12L, Mouser MOQ 1 / 15 weeks. D3 — MRT130KP295CV, Microchip direct multiples of 100 / 42 weeks, estimated August 2, 2027.
- **PARTIAL:** C21/C22 — 942C12P22K-F, Digi-Key has 8 versus buy quantity 12 (only 10 are needed without spares). Mouser has 50 incoming expected October 26, 2026, priced at $88.56 for 12. That future stock is unconfirmed; its factory fallback is 26 weeks.

Two task descriptions need correction: D3's exact MPN is **Microchip**, rather than Littelfuse; 74650074R uses **soldered THR** termination, while the task says press-fit. ISO7710DW tubes are an allowed packaging variant, but Digi-Key marks the tube version no longer manufactured. No engineering substitutes were selected.

Quantity interpretation: each unique non-passive MPN gets two spares; passive spares are 20% rounded up, minimum two. Fuses and clips were unspecified and also receive two spares. Housing and contact quantities are separate keyed values in bundle rows 23–24; their single-unit-price field is blank, with component prices and combined extended prices recorded in notes.

A useful price break: Digi-Key's 30 MOSFETs cost $369.08, less than the task-formula 22 at $433.84. The CSV retains 22 so the subtotal follows the requested quantities.

Primary evidence is the linked product pages and their UTC read times in the CSV. RS UK charges GBP; its $95.57 estimate converts £72.17 using [Wise GBP/USD](https://wise.com/us/currency-converter/gbp-to-usd-rate), 1.3242 read at 05:31:07.109 UTC. Destination eligibility and freight were not established. Manufacturer availability for 750320775 requires login. All work was read-only; no purchase, cart, quote, login, account, sample request or form submission occurred.
