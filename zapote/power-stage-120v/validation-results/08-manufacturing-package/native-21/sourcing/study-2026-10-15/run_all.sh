#!/bin/bash
# Re-run every number in the 2026-10-15 sourcing study. Offline steps read only the committed caches; ONLINE steps are
# commented out (they re-read the vendors and stop at the first bot check; DigiKey was read by hand in a browser).
set -e; cd "$(dirname "$0")"
VR=../../../..                                      # validation-results
# ONLINE: python3 -I scripts/jlc_snapshot.py snapshot/bom-jlcpcb.s32.csv snapshot/jlc-2026-10-15.json scripts/extra_mpns.txt
# ONLINE: scripts/octopart_fetch.sh scripts/octopart_mpns.txt; scripts/octopart_fetch.sh scripts/octopart_mpns_2.txt
# ONLINE: python3 -I scripts/octopart_parse.py downloads/octopart snapshot/octopart-2026-10-15.json   (downloads/ not committed)
python3 -I scripts/build_snapshot.py snapshot/bom-jlcpcb.s32.csv snapshot/jlc-2026-10-15.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/SNAPSHOT-2026-10-15.csv snapshot/SNAPSHOT-2026-10-15.json
# s35 BOM (J2/J5 7466004R, which the JLC cache holds under "extra"): the committed ../SNAPSHOT-2026-10-15.csv is
# snapshot/s35/SNAPSHOT-s35.csv plus the s32 74650074 row, so the s32 and s35 cards join against one dated snapshot.
python3 -I -c "import json;d=json.load(open('snapshot/jlc-2026-10-15.json'));m={b['mpn'] for b in d['bom']};d['bom']+=[r for r in d['extra'] if r['mpn'] not in m];json.dump(d,open('snapshot/s35/jlc-bom-plus-extra.json','w'))"
python3 -I scripts/build_snapshot.py snapshot/s35/bom-jlcpcb.s35.csv snapshot/s35/jlc-bom-plus-extra.json snapshot/octopart-2026-10-15.json \
    snapshot/digikey-2026-10-15.json "$VR/08-manufacturing-package/native-21/sourcing/STOCK-2026-10-13*.csv" \
    snapshot/s35/SNAPSHOT-s35.csv snapshot/s35/SNAPSHOT-s35.json
rm -f snapshot/s35/jlc-bom-plus-extra.json snapshot/s35/SNAPSHOT-s35.json
python3 -I scripts/buildability.py --control
python3 -I scripts/buildability.py snapshot/SNAPSHOT-2026-10-15.csv --json results/buildability-s32.json
# needs TDK's B32674-678 PDF (June 2026; tdk-electronics.tdk.com) at downloads/tdk-b3267x/MKP_B32674_678.pdf, not committed:
# python3 -I scripts/digitize_b32676_irms.py downloads/tdk-b3267x/MKP_B32674_678.pdf results/b32676_irms_curves.json
python3 -I scripts/c5c6_ripple.py results/b32676_irms_curves.json results/c5c6_ripple.json
python3 -I scripts/bank_stock.py $VR/11-candidates/c34-bank-margin/results/bank_margin.json snapshot/octopart-2026-10-15.json \
    snapshot/octopart-2026-10-15.json snapshot/jlc-2026-10-15.json results/bank_stock.json
