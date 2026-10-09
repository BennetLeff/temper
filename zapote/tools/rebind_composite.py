"""Re-bind a unit input to a fresh native export of an edited board.

Only native-derived parts change: the embedded native export (structured, and
as text where the input carries it) and the board, export and extractor
hashes. Source, model, profile and any qualification are untouched. Refuses to
write unless the fresh native measurements equal the input's current ones,
ignoring identity fields and per-pad 'pad_type' (added by newer extractors), so
it can only re-record an edit that measured nothing, such as silkscreen.

Usage: python3 rebind_composite.py INPUT.json NATIVE.json BOARD.kicad_pcb OUT.json
"""
import hashlib
import json
import pathlib
import sys

IDENTITY = {"board_sha256", "board_file_utf8", "extractor_sha256"}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in IDENTITY and k != "pad_type"}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


source_path, native_path, board_path, out_path = map(pathlib.Path, sys.argv[1:])
composite = json.loads(source_path.read_text())
native_text = native_path.read_text()
native = json.loads(native_text)
board_sha256 = hashlib.sha256(board_path.read_bytes()).hexdigest()
if native["board_sha256"] != board_sha256:
    sys.exit("native export is not of this board")
fresh = {k: native[k] for k in composite["native"]}
if strip(fresh) != strip(composite["native"]):
    sys.exit("native measurements differ; this is a re-measurement, not a re-binding")
composite["native"] = fresh
if "native_export_utf8" in composite:
    composite["native_export_utf8"] = native_text
composite["identity"].update(
    board_sha256=board_sha256,
    native_export_sha256=hashlib.sha256(native_text.encode()).hexdigest(),
    extractor_sha256=native["extractor_sha256"],
)
out_path.write_text(json.dumps(composite, indent=2) + "\n")
print(json.dumps({"out": str(out_path), "identity": composite["identity"]}, indent=1))
