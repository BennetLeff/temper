#!/bin/bash
# Fetch the public datasheets this study cites into ../dl (untrusted data; read only via pdftotext).
set -u
cd "$(dirname "$0")/../dl"
while read -r f u; do
  [ -z "$f" ] && continue
  curl -sSL -A "Mozilla/5.0" -o "$f" "$u"
  echo "$f $(wc -c <"$f") $(file -b "$f" | cut -c1-20)"
done <<'LIST'
tl431.pdf https://www.ti.com/lit/ds/symlink/tl431.pdf
lm339b.pdf https://www.ti.com/lit/ds/symlink/lm339b.pdf
tlvh431.pdf https://www.ti.com/lit/ds/symlink/tlvh431.pdf
tps7a47.pdf https://www.ti.com/lit/ds/symlink/tps7a47.pdf
tps3701.pdf https://www.ti.com/lit/ds/symlink/tps3701.pdf
lm4040.pdf https://www.ti.com/lit/ds/symlink/lm4040.pdf
R24C2T25_R.pdf https://recom-power.com/pdf/Econoline/R24C2T25_R.pdf
2edr8259.pdf https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf
LIST
