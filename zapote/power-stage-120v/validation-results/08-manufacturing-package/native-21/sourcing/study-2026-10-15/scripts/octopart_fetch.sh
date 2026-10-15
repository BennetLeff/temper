#!/bin/bash
# Fetch Octopart public search pages (no login, no API key) for each MPN in a list file, 4 s apart, into downloads/octopart/.
# Stops at the first bot-check page (it is recorded, not bypassed). usage: scripts/octopart_fetch.sh MPNLIST.txt
S=$(cd "$(dirname "$0")/.." && pwd); OUT=$S/downloads/octopart; mkdir -p $OUT
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
while IFS= read -r m; do
  [ -z "$m" ] && continue; case "$m" in \#*) continue;; esac
  f=$OUT/$(printf '%s' "$m" | tr '/,() ' '_____').html
  [ -s "$f" ] && continue
  q=$(python3 -I -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$m")
  code=$(curl -s -m 30 -A "$UA" -H "Accept-Language: en-US,en" -o "$f" -w "%{http_code}" "https://octopart.com/search?q=$q")
  echo "$(date -u +%FT%TZ) $code $m $(wc -c < "$f")" >> $OUT/_fetch.log
  if grep -q -i "just a moment\|px-captcha\|access denied" "$f" || [ "$code" != 200 ]; then echo "STOP: bot check / HTTP $code at $m" >> $OUT/_fetch.log; mv "$f" "$f.blocked"; break; fi
  sleep 4
done < "$1"
