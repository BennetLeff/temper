# Yangjie GBU2510A source record

This record preserves the exact manufacturer part and the manufacturer-published
values used in the loss and cooling comparison.  The manufacturer endpoint
returned HTTP 403/404 on 2026-09-14, so the Yangjie-authored PDF is retained
from a distributor mirror as a byte-identified copy.  The mirror is evidence
of the document bytes, not a second authority or a substitute part.

* **Manufacturer:** Yangzhou Yangjie Electronic Technology Co., Ltd.
* **Document:** `GBU25005A THRU GBU2510A`, document `S-B407`, Rev. 2.5,
  09-Apr-2024.
* **Exact URL:**
  <https://www.21yangjie.com/pdf/zlqj/zhengliuqiao/GBU25005A%20THRU%20GBU2510A.pdf>
* **Retained PDF:** [`yangjie-gbu2510a.pdf`](yangjie-gbu2510a.pdf), retrieved
  from the Datasheet4U mirror on 2026-09-14.  SHA-256 is
  `8bae78604e65be4d011c2989bbaddd9aab32b55fbdd40a79891aa8803f997794`.
  The PDF metadata identifies the same Yangjie title, `S-B407`, Rev. 2.5 and
  09-Apr-2024 as the manufacturer URL.  No distributor suffix or GBJ-family
  document is used as a replacement.

## Values for GBU2510A

The family table applies the following values to the `GBU2510A` column:

| Parameter | Published value | Test condition / use |
|---|---:|---|
| `VRRM`, `VRMS`, `VDC` | 1000 V, 700 V, 1000 V | Maximum ratings |
| Average rectified output current | 25 A with heatsink at `Tc=100 °C`; 3.5 A without heatsink at `Ta=25 °C` | 60 Hz sine, resistive load |
| `IFSM` | 350 A | 60 Hz half-sine, one cycle, `Tj=25 °C` |
| `I²t` | 508 A²s | Per diode, 1–8.3 ms, `Tj=25 °C` |
| Junction/storage range | −55…+150 °C | Maximum rating |
| Dielectric strength | 2.5 kV AC, 1 minute | Terminals to case |
| `VF` maximum | 1.0 V per diode | `IFM=12.5 A`, `Ta=25 °C` |
| Reverse current maximum | 5 µA at 25 °C; 100 µA at 125 °C | Rated blocking voltage, per diode |
| `RθJA` | 25 °C/W | Without heatsink |
| `RθJC` | 1.0 °C/W | With heatsink; device mounted on 75 × 45 × 5.5 mm aluminum plate |
| Unit mass | approximately 3.97 g | Ordering table, B1/A1 packing |

Figure 3 is the manufacturer’s typical instantaneous forward-voltage curve and
contains separate `Tj=25 °C` and `Tj=125 °C` traces.  It is a typical curve,
not a tolerance envelope.  The only guaranteed forward-loss datum available in
the indexed table is the 1.0 V maximum point above; the loss model therefore
uses a declared bound rather than digitizing the typical curve as a guarantee.

The outline drawing identifies the GBU body (approximately 21.8–22.3 mm wide,
18.3–18.8 mm deep and 17.5–18.0 mm high) and the inline four-lead arrangement
`−, ~, ~, +`.  The local KiCad GBU footprint uses the documented 5.08 mm pad
pitch and 1.6 mm drills; the board owner remains authoritative for the exact
pad coordinates.

The datasheet labels `RθJC` as a device thermal characteristic and does not
state an aggregate resistance for the four-diode bridge at a 40 W total loss.
The 1.0 °C/W datum therefore cannot by itself justify multiplying a whole
bridge loss by that value; element-to-case, lead, solder and spreader heat
partition must be resolved by the physical model.

## Loss binding

For a sinusoidal 15 A RMS input, the bridge conducts two diodes and

`P_bridge = 2 · V_F · (2√2/π) · I_RMS`.

Using the 1.0 V table maximum gives 27.01 W.  This is a conservative point
estimate at the specified test current, not a production upper bound: the
21.2 A waveform peak exceeds the 12.5 A `VF` test point, temperature changes
the forward curve, and the PFC current waveform may not be a pure sine.  The
comparison retains the existing 40 W allowance until a waveform-bound model or
measurement justifies changing it.

The manufacturer bytes remain unavailable directly, but the retained
Yangjie-authored mirror is sufficient to bind the revision and values without
silently changing the part identity.  The mirror URL and byte hash are kept in
the source index for later replacement if the origin becomes retrievable.
