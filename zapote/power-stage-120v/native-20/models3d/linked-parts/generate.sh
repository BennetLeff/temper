#!/bin/sh
set -eu
cd "$(dirname "$0")"
for source in ./*.geo; do
  output="${source%.geo}.step"
  gmsh "$source" -0 -format step -o "$output" -nopopup >/dev/null
  # OpenCASCADE writes wall-clock time into the STEP header. Pin it so
  # regeneration of identical geometry does not make an unrelated diff.
  perl -pi -e "s/'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}'/'2000-01-01T00:00:00'/ if /^FILE_NAME\(/" "$output"
done
