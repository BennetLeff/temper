# Bridge cooling concept comparison

The comparison keeps the same board, 15 A RMS branch, 40 °C inlet and 40 W
allowance.  It ranks design evidence; it does not promote a fabrication choice.
All junction temperatures below use the legacy assumed whole-bridge
`RθJC=1.25 °C/W`; they are conditional screens, not qualified predictions.

| Concept | Sourced assembly | Approx. concept envelope | Thermal screen | Flow evidence | Fit / availability |
|---|---|---|---|---|---|
| Baseline | 395-1AB + 2 × MF80251V1 fans + spreader | 170 × 160 × 95 mm | 120 °C junction; 107.86 °C local PCB, 2.14 K margin | Requires ≥43.4 CFM through gross face at 500 LFM; installed point unknown | Enclosure fit indeterminate; 395-1AB and fan snapshots available |
| Compact dedicated | 396-1AB + 1 × MF80251V1 | 145 × 125 × 70 mm concept allowance | 142.8 °C junction under the retained legacy `RθJC=1.25 °C/W` screen; fails 125 °C by 17.8 K on that screen | One fan cannot establish 500 LFM after duct losses | Enclosure fit indeterminate; 396-1AB snapshot available |
| Shared cooker airflow (revised) | 392-120AB + 1 × 9RA1212E1001, upstream PFC loads | 170 × 160 × 175 mm concept allowance | Same conditional 116.8 °C / 118.64 °C distributed screen | Sanyo curve supports a plausible 100 CFM point only if duct/system pressure is no more than ~30 Pa; measure or solve the intersection | Enclosure fit indeterminate; DigiKey snapshot shows 22 units, recheck before ordering |

The compact concept could be used in a future comparison experiment but should
not lead the 40 W ranking under the legacy screen.  The baseline is mechanically simpler and preserves
the prior work, but its 5 K junction margin and 2.14 K PCB margin are too small
for unmeasured contact, flow and sensor error.  The shared concept has the best
potential margin if the enclosure can supply a 100 CFM operating point and
separates the bridge from upstream heat.  Its conditional 105 W distributed
screen still misses the 15 K objective by about 8.64 K, so an enclosure-level
model must prove a lower bridge-zone resistance or a separate path for the
other loads.  The revised fan has enough free-air capacity to make the
catalog point physically plausible; it does not prove that the installed duct
will reach it.

The superseded shared concept used two 41 CFM free-air Sunon fans. Their
combined 82 CFM endpoint cannot establish the sink's 100 CFM catalog point,
even before duct losses. Its historical proposal remains in
[`proposals/shared-392-120ab.json`](proposals/shared-392-120ab.json), outside
the three active comparison rows.

All three concepts use a chassis-supported sink and a separate spring clamp.
The heatsink must not hang from the bridge leads or solder fillets.  Any exposed
metal, screw, spreader or fin near the mains bridge requires the safety owner's
creepage, clearance, insulation and chassis-bonding review.

Source dimensions, ratings and distributor snapshots are in
[`sources/README.md`](sources/README.md); machine-readable records are in
[`proposals/`](proposals/).
