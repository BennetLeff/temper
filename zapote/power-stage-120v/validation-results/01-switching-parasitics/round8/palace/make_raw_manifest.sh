#!/bin/zsh
set -euo pipefail

cd ${0:A:h}
find raw -type f -print | LC_ALL=C sort | while IFS= read -r rawfile; do
  case ${rawfile:l} in
    *.lib|*.ibs)
      print -u2 "Licensed vendor model candidate in raw: $rawfile"
      exit 1
      ;;
  esac
  shasum -a 256 "$rawfile"
done
