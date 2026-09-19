# Source record for TEA construction decision

Retrievals during this review: 3 search queries and 4 page opens; no external
message was sent and no standard text was downloaded.

Primary sources:

- NXP TEA2209T product page (links to the Rev. 1.1 datasheet, UM11493 and
  SOT109-1 packing/package material):
  https://www.nxp.com/products/TEA2209T
- NXP SOT109-1 package overview (1.27 mm pitch, SO16 body description):
  https://www.nxp.com/packages/SOT109-1
- NXP TEA2209DB1584 getting-started page. It identifies the demo board as an
  SO16 TEA2209T implementation and describes the four external bridge leads;
  it does not provide an insulation certificate or a land-pattern waiver:
  https://www.nxp.com/document/guide/getting-started-with-the-tea2209db1584
- IEC webstore scope for IEC 60664-1:2020. It states that the standard covers
  insulation coordination, clearance, creepage and solid-insulation criteria
  for low-voltage equipment up to 2,000 m; the normative tables and Example 11
  are not publicly available in this retrieval:
  https://webstore.iec.ch/en/publication/59671

Retained local primary captures used for dimensions and pin functions are
listed in the coordinator review's `sources/manifest.json`. The Bourns paper
is retained there as an interpretation aid only; it does not establish the
appliance standard or authorize omitting NC lands.

The official sources do not answer the two decisive construction questions:
whether this exact TEA2209T package permits unsoldered NC leads in the proposed
land pattern, and which product-standard clause governs the assembled path.
Those remain explicit external inputs rather than inferred compliance claims.
