#!/bin/bash
# buck-reva release exporter — release owner tool.
# Targets ONLY the standalone prototype project; refuses without a verified board freeze.
# KiCad CLI flags verified against kicad-cli 10.0.6 `--help` on 2026-09-10.
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCH="$PROJ_DIR/buck-reva.kicad_sch"
PCB="$PROJ_DIR/buck-reva.kicad_pcb"
FREEZE="$PROJ_DIR/verification/board-freeze.md"
SRC_MANIFEST="$PROJ_DIR/source-manifest.json"
RELEASE="$PROJ_DIR/release"
LOG="$RELEASE/verification/export.log"

KICAD_CLI="${KICAD_CLI:-}"
EXPECTED_VERSION="10.0.6"
VERIFY_ONLY=0

usage() {
  echo "Usage: $0 --kicad-cli /path/to/kicad-cli" >&2
  echo "  or: KICAD_CLI=/path/to/kicad-cli $0" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kicad-cli) KICAD_CLI="${2:-}"; shift 2 ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$KICAD_CLI" ]]; then
  echo "REFUSED: explicit KiCad CLI path required (--kicad-cli or KICAD_CLI env)." >&2
  exit 2
fi
if [[ ! -x "$KICAD_CLI" ]]; then
  echo "REFUSED: kicad-cli not executable at '$KICAD_CLI'." >&2
  exit 2
fi

VERSION="$("$KICAD_CLI" --version 2>&1 | head -n 1)"
echo "kicad-cli: $KICAD_CLI version: $VERSION"
if ! printf '%s' "$VERSION" | grep -q "$EXPECTED_VERSION"; then
  echo "REFUSED: expected KiCad runtime $EXPECTED_VERSION, got: $VERSION" >&2
  echo "Document and validate an explicit version change before proceeding." >&2
  exit 2
fi

# Freeze gate: final export waits for the board owner's freeze + source hashes.
if [[ ! -f "$FREEZE" || ! -f "$SRC_MANIFEST" ]]; then
  echo "AWAITING BOARD FREEZE: $FREEZE and/or $SRC_MANIFEST absent." >&2
  echo "Independent preparation (BOM/DigiKey/notes) may proceed; do not export a fixture as the final prototype." >&2
  exit 3
fi
if [[ ! -f "$SCH" || ! -f "$PCB" ]]; then
  echo "REFUSED: standalone project files absent: $SCH / $PCB" >&2
  exit 3
fi

verify_freeze_hashes() {
  # The freeze binds one complete, project-relative source manifest. Anything
  # else fails closed before a KiCad command can run.
  python3 - "$PROJ_DIR" "$SRC_MANIFEST" <<'EOF'
import json, hashlib, sys, os, re
proj, man = sys.argv[1], sys.argv[2]
try:
    with open(man, encoding="utf-8") as f:
        d = json.load(f)
except Exception as e:
    print(f"REFUSED: cannot read source manifest: {e}", file=sys.stderr); sys.exit(2)
pairs = list(d.get("files", {}).items()) if isinstance(d.get("files"), dict) else []
required = {
    "buck-reva.kicad_sch", "buck-reva.kicad_pcb", "buck-reva.kicad_pro",
    "buck-reva.kicad_dru", "buck-reva.kicad_sym", "fp-lib-table", "sym-lib-table"
}
if d.get("schema") != "buck-reva.source-manifest.v1" or d.get("revision") != "A":
    print("REFUSED: source manifest schema/revision is not buck-reva Rev A.", file=sys.stderr); sys.exit(2)
if not pairs:
    print("REFUSED: source-manifest.json files mapping is empty or absent.", file=sys.stderr); sys.exit(2)
seen = set()
bad_shape = []
for rel, expect in pairs:
    if not isinstance(rel, str) or rel in seen or os.path.isabs(rel) or rel.startswith("../") or "/../" in rel:
        bad_shape.append(str(rel)); continue
    seen.add(rel)
    if not isinstance(expect, str) or not re.fullmatch(r"[0-9a-f]{64}", expect):
        bad_shape.append(rel)
if bad_shape:
    print("REFUSED: duplicate/out-of-project path or malformed SHA-256: " + ", ".join(bad_shape), file=sys.stderr); sys.exit(2)
missing_required = sorted(required - seen)
mods = sorted(p for p in seen if p.startswith("buck-reva.pretty/") and p.endswith(".kicad_mod"))
if missing_required:
    print("REFUSED: source manifest omits required inputs: " + ", ".join(missing_required), file=sys.stderr); sys.exit(2)
if not mods:
    print("REFUSED: source manifest omits all local footprint dependencies.", file=sys.stderr); sys.exit(2)
bad = []
for rel, expect in pairs:
    p = os.path.join(proj, rel)
    if not os.path.isfile(p):
        print(f"MISSING input: {rel}", file=sys.stderr); bad.append(rel); continue
    got = hashlib.sha256(open(p, "rb").read()).hexdigest()
    if got != expect:
        print(f"HASH MISMATCH: {rel}\n  manifest: {expect}\n  actual:   {got}", file=sys.stderr)
        bad.append(rel)
if bad:
    sys.exit(1)
print(f"Freeze hash check OK: {len(pairs)} inputs match {man}.")
EOF
  python3 - "$FREEZE" "$SRC_MANIFEST" <<'EOF'
import hashlib, re, sys
freeze, manifest = sys.argv[1:]
text = open(freeze, encoding="utf-8").read()
actual = hashlib.sha256(open(manifest, "rb").read()).hexdigest()
m = re.search(r"Source-manifest SHA-256:\s*`?([0-9a-f]{64})", text)
if not m:
    print("REFUSED: board-freeze.md does not bind a full source-manifest SHA-256.", file=sys.stderr); sys.exit(2)
if m.group(1) != actual:
    print(f"REFUSED: board freeze manifest digest mismatch (freeze {m.group(1)}, actual {actual}).", file=sys.stderr); sys.exit(1)
print(f"Board freeze binding OK: source manifest {actual}.")
EOF
}

echo "--- pre-export freeze verification ---"
# Invalidate any previous success before starting. Generated directories remain
# inspectable, but no stale ZIP/manifest can claim this attempt succeeded.
mkdir -p "$RELEASE"
if [[ "$VERIFY_ONLY" -eq 0 ]]; then
  rm -f "$RELEASE/manifest.json" "$RELEASE/buck-reva-fabrication.zip" "$RELEASE/buck-reva-fabrication.zip.sha256"
fi
verify_freeze_hashes

if [[ "$VERIFY_ONLY" -eq 1 ]]; then
  echo "FREEZE VERIFICATION COMPLETE (no export requested)."
  exit 0
fi

printf '%s\n' '{"artifact":"buck-reva prototype release","status":"EXPORT ATTEMPT INVALIDATED — incomplete until a run succeeds"}' > "$RELEASE/manifest.json"
MANIFEST_DIGEST="$(shasum -a 256 "$SRC_MANIFEST" | awk '{print $1}')"
FREEZE_DIGEST="$(shasum -a 256 "$FREEZE" | awk '{print $1}')"

# Rebuild ONLY the designated generated output subdirs (never arbitrary paths).
mkdir -p "$RELEASE/gerbers" "$RELEASE/drill" "$RELEASE/assembly" "$RELEASE/docs" "$RELEASE/verification"
rm -f "$RELEASE"/gerbers/* "$RELEASE"/drill/* "$RELEASE"/assembly/positions-full.csv "$RELEASE"/assembly/positions-smt.csv 2>/dev/null || true
: > "$LOG"
{
  echo "kicad-cli: $KICAD_CLI"
  echo "version: $VERSION"
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "freeze: $FREEZE"
  echo "source-manifest: $SRC_MANIFEST"
} >> "$LOG"

run() { echo "+ $*" >> "$LOG"; "$@" 2>&1 | tee -a "$LOG"; }

# Schematic outputs
run "$KICAD_CLI" sch export pdf --output "$RELEASE/docs/schematic.pdf" "$SCH"
run "$KICAD_CLI" sch export netlist --format kicadsexpr --output "$RELEASE/verification/schematic-netlist.kicadsexpr" "$SCH"
# KiCad 10's BOM exporter raises bad_any_cast when custom fields that are not
# present on every symbol are named on the command line. Export its stable
# default CSV; procurement/bom.csv carries the frozen purchasing fields.
run "$KICAD_CLI" sch export bom --output "$RELEASE/assembly/schematic-bom.csv" "$SCH"

# Native checks: errors hard-fail; full reports retained for warning review.
run "$KICAD_CLI" sch erc --format report --units mm --severity-all --output "$RELEASE/verification/erc-report.txt" "$SCH"
run "$KICAD_CLI" sch erc --format report --units mm --severity-error --exit-code-violations --output "$RELEASE/verification/erc-errors.txt" "$SCH"
run "$KICAD_CLI" pcb drc --format report --units mm --all-track-errors --schematic-parity --refill-zones --severity-all --output "$RELEASE/verification/drc-report.txt" "$PCB"
run "$KICAD_CLI" pcb drc --format report --units mm --all-track-errors --schematic-parity --refill-zones --severity-error --exit-code-violations --output "$RELEASE/verification/drc-errors.txt" "$PCB"

# Copper/mask/silk/paste + Edge.Cuts gerbers (actual layers only; top paste included for stencil).
run "$KICAD_CLI" pcb export gerbers \
  --layers 'F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,Edge.Cuts' \
  --check-zones --precision 6 \
  --output "$RELEASE/gerbers" "$PCB"

# Excellon drill + map (separate PTH/NPTH for the THT terminals).
run "$KICAD_CLI" pcb export drill \
  --format excellon --excellon-units mm --drill-origin absolute \
  --excellon-separate-th --generate-map --map-format pdf \
  --output "$RELEASE/drill" "$PCB"

# Positions: generic full (reconciliation) + SMT-only (usable later); THT listed for manual install.
run "$KICAD_CLI" pcb export pos --format csv --units mm --side both --exclude-dnp \
  --output "$RELEASE/assembly/positions-full.csv" "$PCB"
run "$KICAD_CLI" pcb export pos --format csv --units mm --side both --exclude-dnp --smd-only \
  --output "$RELEASE/assembly/positions-smt.csv" "$PCB"
python3 - "$RELEASE/assembly/positions-full.csv" "$RELEASE/assembly/positions-smt.csv" "$RELEASE/assembly/tht-manual-list.csv" <<'EOF'
import csv, sys
full_p, smt_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
def refs(p):
    with open(p) as f:
        rows = list(csv.DictReader(f))
    key = 'Ref' if rows and 'Ref' in rows[0] else ('Reference' if rows else 'Ref')
    return {r[key]: r for r in rows}
full, smt = refs(full_p), refs(smt_p)
tht = {k: v for k, v in full.items() if k not in smt}
with open(out_p, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Ref', 'Disposition', 'Note'])
    for k in sorted(tht):
        w.writerow([k, 'MANUAL (THT/excluded-from-SMT)', 'Hand-solder per assembly notes; verify J1/J2 pinout at freeze'])
print(f"THT manual list: {len(tht)} refs (J1/J2 expected among them).")
EOF

# Review views: assembly/fabrication PDFs + copper SVG views for both sides.
run "$KICAD_CLI" pcb export pdf --layers 'F.Fab,B.Fab,F.SilkS,B.SilkS,Edge.Cuts' \
  --mode-single --scale 0 --check-zones \
  --output "$RELEASE/docs/assembly-drawing.pdf" "$PCB"
run "$KICAD_CLI" pcb export svg --layers 'F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,Edge.Cuts' \
  --mode-multi --exclude-drawing-sheet --check-zones \
  --output "$RELEASE/verification" "$PCB"

echo "--- post-export freeze re-verification ---"
verify_freeze_hashes
POST_MANIFEST_DIGEST="$(shasum -a 256 "$SRC_MANIFEST" | awk '{print $1}')"
POST_FREEZE_DIGEST="$(shasum -a 256 "$FREEZE" | awk '{print $1}')"
if [[ "$POST_MANIFEST_DIGEST" != "$MANIFEST_DIGEST" || "$POST_FREEZE_DIGEST" != "$FREEZE_DIGEST" ]]; then
  echo "REFUSED: frozen manifest or board-freeze changed during export; release invalidated." >&2
  printf '%s\n' '{"artifact":"buck-reva prototype release","status":"EXPORT INVALID — freeze changed during export"}' > "$RELEASE/manifest.json"
  rm -f "$RELEASE/buck-reva-fabrication.zip" "$RELEASE/buck-reva-fabrication.zip.sha256"
  exit 1
fi

# Hash inputs/outputs; archive ONLY fabricator-intended files; hash the ZIP outside itself.
python3 - "$PROJ_DIR" "$RELEASE" "$VERSION" <<'EOF'
import json, hashlib, os, sys, datetime
proj, rel, ver = sys.argv[1], sys.argv[2], sys.argv[3]
def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()
outs = []
for root, _, files in os.walk(rel):
    for n in sorted(files):
        if n in ('manifest.json', 'export.log', 'buck-reva-fabrication.zip', 'buck-reva-fabrication.zip.sha256', 'closeout.md'):
            continue
        p = os.path.join(root, n)
        outs.append({"path": os.path.relpath(p, rel), "sha256": sha(p)})
ins = []
for relp in ("buck-reva.kicad_sch", "buck-reva.kicad_pcb", "buck-reva.kicad_pro",
             "verification/board-freeze.md", "source-manifest.json"):
    p = os.path.join(proj, relp)
    if os.path.isfile(p):
        ins.append({"path": relp, "sha256": sha(p)})
man = {"artifact": "buck-reva prototype release",
       "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
       "kicad_version": ver, "status": "READY FOR ORDER REVIEW — package inspection recorded in verification/visual-review.md",
       "source_manifest_sha256": sha(os.path.join(proj, "source-manifest.json")),
       "board_freeze_sha256": sha(os.path.join(proj, "verification/board-freeze.md")),
       "inputs": ins, "outputs": outs}
json.dump(man, open(os.path.join(rel, 'manifest.json'), 'w'), indent=2)
print(f"manifest.json: {len(ins)} inputs, {len(outs)} outputs.")
EOF

# Fabricator ZIP: gerbers + drill only (purchasing worksheet stays out).
(
  cd "$RELEASE"
  rm -f buck-reva-fabrication.zip
  # Normalize archive member timestamps; KiCad embeds generation time in the
  # file contents and drill-map PDFs, so the manifest records the actual run.
  find gerbers drill -type f -exec touch -t 200001010000 {} +
  zip -X -r buck-reva-fabrication.zip gerbers drill >/dev/null
)
shasum -a 256 "$RELEASE/buck-reva-fabrication.zip" > "$RELEASE/buck-reva-fabrication.zip.sha256"
cat "$RELEASE/buck-reva-fabrication.zip.sha256"

echo "EXPORT COMPLETE. Next: inspect Gerbers/drills/positions per release-checklist.md (visual review still required)."
