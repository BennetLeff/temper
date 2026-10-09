#!/usr/bin/env bash
# Install the pinned KiCad for zapote's live native tests on a Linux CI runner,
# and export KICAD_CLI / KICAD_PYTHON (plus the library paths they need) to
# later steps through $GITHUB_ENV.
#
# 10.0.4 is the version every native fact and fixture in zapote was measured
# on. Changing it is a re-baseline event (AGENTS.md), not a routine bump.
set -euo pipefail
version=10.0.4
sha256=4b1da0156cb1d180ba4a672e9a9981672390545c3b3b4575382b1662e959b220
dir="${RUNNER_TEMP:?}/kicad"
mkdir -p "$dir"
cd "$dir"
curl -fsSL --retry 3 -o kicad.tar \
  "https://github.com/KiCad/kicad-source-mirror/releases/download/${version}/kicad-${version}-x86_64.AppImage.tar"
echo "${sha256}  kicad.tar" | sha256sum -c -
tar -xf kicad.tar
rm kicad.tar
"./kicad-${version}-x86_64.AppImage" --appimage-extract > /dev/null
root="$dir/squashfs-root"
libs="$root/usr/lib:$root/usr/lib/x86_64-linux-gnu"
export LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$root/usr/bin/kicad-cli" version

pcbnew_dir=$(dirname "$(find "$root" -name pcbnew.py -print -quit)")
python=""
for candidate in $(find "$root/usr/bin" -maxdepth 1 -name 'python3*' -type f) /usr/bin/python3; do
  if PYTHONPATH="$pcbnew_dir" "$candidate" -c 'import pcbnew; print(pcbnew.Version())' 2>/dev/null; then
    python="$candidate"
    break
  fi
done
if [ -z "$python" ]; then
  echo "no Python in the KiCad image can import pcbnew (pcbnew.py at $pcbnew_dir)" >&2
  ls "$root/usr/bin" >&2
  exit 1
fi
{
  echo "KICAD_CLI=$root/usr/bin/kicad-cli"
  echo "KICAD_PYTHON=$python"
  echo "PYTHONPATH=$pcbnew_dir"
  echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
} >> "${GITHUB_ENV:?}"
