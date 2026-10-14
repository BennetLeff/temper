# D3 / D17 bus TVS: second sources at JLC (2026-10-14, after stage 30)

D3 / D17 (2 × Good-Ark 30KPA150CA, P600, consigned) are the largest line the board can still change without the owner:
$19.64 per board at 500, zero DigiKey stock (`sourcing/STOCK-2026-10-13.csv`). R2-02 (`../r2-cost/PROPOSALS.md`) named two
JLC alternatives on the same P600 footprint.

    python3 -I scripts/jlc_fetch.py detail C522439 C1976335
    python3 -I scripts/jlc_fetch.py search "30KPA150"

(records cached in `scripts/jlc-raw/`). Every 30KPA150 variant JLC lists has **zero stock**: Brightking 30KPA150CA/B
(C522439, $5.88 at 100) and 30KPA150A/B (C522438), Littelfuse 30KPA150A (C1976335, $1.86 at 500), 30KPA150CA (C19111562),
-B, -HR and -HRA variants, and Microchip 30KPA150AE3 / 30KPA150E3.

**Disposition:** no design stage. The pair is sized by clamp voltage at the design current (466.8 V at 129.8 A against
520 V, DECISIONS 2026-10-09 stage 14 item 3), not by the 2 J energy. A smaller family has a lower rated peak pulse
current at a similar clamp voltage, so it would need its own clamp-at-current check; that was not done. A
second-source swap only moves a consigned line between suppliers. DC-LINK-CLAMP.md also forbids a silent change of suffix
or family. This belongs with the owner's sourcing round: quote Littelfuse 30KPA150A (unidirectional suits the DC bus) or
the CA against the Good-Ark part, with owner approval of the MPN.
