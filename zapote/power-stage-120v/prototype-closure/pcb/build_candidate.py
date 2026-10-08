"""Apply the native19 HOT5 ECO through KiCad's API; source remains Atopile.

The JSON contains authored poses/routes, not a placement or routing algorithm.
Use KiCad's bundled Python. The baseline is supplied explicitly and hash checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

import pcbnew
from source_snapshot import verify_source_snapshot

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
REPO = UNIT.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import gen_schematics as source  # noqa: E402 — existing repository adapter, loaded after explicit path.


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(xy: list[float]) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(*(pcbnew.FromMM(x) for x in xy))


def identifier(name: str) -> pcbnew.KIID:
    return pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-native19/" + name)))


def build(baseline: Path) -> None:
    verify_source_snapshot(UNIT)
    layout = json.loads((HERE / "hot5-layout.json").read_text())
    if digest(baseline) != layout["baseline_sha256"]:
        raise ValueError("native18 baseline hash mismatch")
    out = UNIT / "native-19"
    netlist = source.parse_netlist(out / "frozen/default.net")
    exported = json.loads((out / "frozen/resolved-components.json").read_text())
    attributes = {x["address"].split("::", 1)[1]: x["attributes"] for x in exported["components"]}
    tree = source._sexp((out / "frozen/default.net").read_text())[0]
    components = source._children(source._children(tree, "components")[0], "comp")
    paths = {
        source._field(c, "ref"): source._field(source._children(c, "sheetpath")[0], "names").split(
            "::", 1
        )[1]
        for c in components
    }
    pin_nets = {(ref, pin): net.name for net in netlist.nets.values() for ref, pin in net.nodes}
    board = pcbnew.LoadBoard(str(baseline))
    before = {t.m_Uuid.AsString(): t.GetNetname() for t in board.GetTracks()}
    for name in sorted({n.name for n in netlist.nets.values()}):
        if not board.FindNet(name):
            board.Add(pcbnew.NETINFO_ITEM(board, name))
    by_ref = {f.GetReference(): f for f in board.GetFootprints()}
    uuid_replacements = {}
    for ref, pose in layout["poses_mm_deg"].items():
        a = attributes[paths[ref]]
        lib, name = a["footprint"].split(":", 1)
        local = out / "candidate-libs" / (lib + ".pretty")
        if not (local / (name + ".kicad_mod")).is_file():
            raise FileNotFoundError(f"missing committed footprint {a['footprint']}")
        fp = pcbnew.FootprintLoad(str(local), name)
        if fp is None:
            raise ValueError(f"missing footprint {a['footprint']}")
        old = by_ref.get(ref)
        uuid_replacements[fp.m_Uuid.AsString()] = (
            old.m_Uuid.AsString() if old else identifier(ref).AsString()
        )
        if old:
            fp.SetPath(old.GetPath())
            board.Remove(old)
        fp.SetReference(ref)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetValue(a["mpn"])
        fp.SetField("MPN", a["mpn"])
        fp.SetField("SourceInstance", paths[ref])
        fp.GetField("MPN").SetVisible(False)
        fp.GetField("SourceInstance").SetVisible(False)
        fp.SetPosition(point(pose[:2]))
        fp.SetOrientationDegrees(pose[2])
        board.Add(fp)
        fp.Reference().SetPosition(
            point(layout.get("reference_positions", {}).get(ref, [pose[0], pose[1] - 2.5]))
        )
        for index, child in enumerate(
            list(fp.Pads()) + list(fp.GraphicalItems()) + list(fp.GetFields())
        ):
            uuid_replacements[child.m_Uuid.AsString()] = identifier(
                f"{ref}/child/{index}"
            ).AsString()
        fp.Value().SetVisible(False)
        by_ref[ref] = fp
    root_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-native19-sch/root"))
    for ref, fp in by_ref.items():
        fp.SetPath(pcbnew.KIID_PATH(f"/{root_id}/{netlist.components[ref].tstamp}"))
        for pad in fp.Pads():
            if (ref, pad.GetNumber()) in pin_nets:
                pad.SetNet(board.FindNet(pin_nets[(ref, pad.GetNumber())]))
        for model in fp.Models():
            model.m_Filename = model.m_Filename.replace(
                "${KIPRJMOD}/../models3d/", "${KIPRJMOD}/models3d/"
            )
    for track in board.GetTracks():
        resize = layout.get("resize_vias", {}).get(track.m_Uuid.AsString())
        if resize:
            if track.GetNetname() != resize["net"]:
                raise ValueError("via resize net mismatch")
            track.SetWidth(pcbnew.FromMM(resize["diameter_mm"]))
            track.SetDrill(pcbnew.FromMM(resize["drill_mm"]))
    for item in list(board.GetTracks()) + list(board.Zones()):
        new_net = layout.get("rename_copper", {}).get(item.m_Uuid.AsString())
        if new_net:
            item.SetNet(board.FindNet(new_net))
    removed = []
    for track in list(board.GetTracks()):
        if track.m_Uuid.AsString() in layout["remove_tracks"]:
            removed.append(track.m_Uuid.AsString())
            board.Remove(track)
    if sorted(removed) != sorted(layout["remove_tracks"]):
        raise ValueError("expected old U8 routes absent")
    additions = []

    def endpoint(value):
        if isinstance(value, str):
            ref, pin = value.split(".")
            pad = next(p for p in by_ref[ref].Pads() if p.GetNumber() == pin)
            return [pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)]
        return value

    for route_index, (net, layer, points) in enumerate(layout["routes"]):
        points = [endpoint(p) for p in points]
        for segment, (start, end) in enumerate(zip(points, points[1:])):  # noqa: B905 — KiCad Python 3.9; adjacent pairs intentionally differ in length.
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(point(start))
            track.SetEnd(point(end))
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetLayer(board.GetLayerID(layer))
            track.SetNet(board.FindNet(net))
            target_uuid = identifier(f"route/{route_index}/{segment}").AsString()
            uuid_replacements[track.m_Uuid.AsString()] = target_uuid
            board.Add(track)
            additions.append(
                {"uuid": target_uuid, "net": net, "layer": layer, "start_mm": start, "end_mm": end}
            )
    for index, (net, x, y) in enumerate(layout["vias"]):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point([x, y]))
        via.SetWidth(pcbnew.FromMM(0.55))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(board.FindNet(net))
        target_uuid = identifier(f"via/{index}").AsString()
        uuid_replacements[via.m_Uuid.AsString()] = target_uuid
        board.Add(via)
        additions.append({"uuid": target_uuid, "net": net, "via_mm": [x, y]})
    pcbnew.SaveBoard(str(out / "section.kicad_pcb"), board)
    serialized = (
        (out / "section.kicad_pcb")
        .read_text()
        .replace("${KIPRJMOD}/../models3d/", "${KIPRJMOD}/models3d/")
    )
    serialized = serialized.replace(
        "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_Shunt_Vishay_WSK2512_6332Metric_T2.21mm.step",
        "${KIPRJMOD}/models3d/linked-parts/WSK25121L000FEA-envelope.step",
    )
    for old_uuid, new_uuid in uuid_replacements.items():
        serialized = serialized.replace(old_uuid, new_uuid)
    (out / "section.kicad_pcb").write_text(serialized)
    saved = pcbnew.LoadBoard(str(out / "section.kicad_pcb"))
    # Re-serialize after deterministic IDs are installed: KiCad sorts objects by UUID.
    pcbnew.SaveBoard(str(out / "section.kicad_pcb"), saved)
    # KiCad 10's net-code ordering varies between loads. Canonicalize only
    # complete top-level track/via forms, then re-read and verify all identities.
    canonical = (out / "section.kicad_pcb").read_text()
    pattern = re.compile(r"^\t\((?:segment|via)\n.*?^\t\)\n", re.MULTILINE | re.DOTALL)
    blocks = pattern.findall(canonical)
    if blocks:
        ordered = iter(
            sorted(blocks, key=lambda block: re.search(r'\(uuid "([^" ]+)"', block).group(1))
        )
        canonical = pattern.sub(lambda _match: next(ordered), canonical)
    (out / "section.kicad_pcb").write_text(canonical)
    saved = pcbnew.LoadBoard(str(out / "section.kicad_pcb"))
    after = {t.m_Uuid.AsString(): t.GetNetname() for t in saved.GetTracks()}
    expected = {
        k: layout.get("rename_copper", {}).get(k, v) for k, v in before.items() if k not in removed
    }
    expected.update({x["uuid"]: x["net"] for x in additions})
    if after != expected:
        raise ValueError("saved copper UUID/net identity differs from authored routes")
    actual_pads = {
        (f.GetReference(), p.GetNumber(), p.GetNetname())
        for f in saved.GetFootprints()
        for p in f.Pads()
        if p.GetNumber()
    }
    expected_pads = {(r, p, n) for (r, p), n in pin_nets.items()}
    if actual_pads != expected_pads:
        raise ValueError(
            f"source/native pad mismatch: missing {expected_pads - actual_pads}; extra {actual_pads - expected_pads}"
        )
    identity_rows = []
    for fp in saved.GetFootprints():
        ref = fp.GetReference()
        expected_attrs = attributes[paths[ref]]
        expected_path = f"/{root_id}/{netlist.components[ref].tstamp}"
        actual_identity = {
            "mpn": fp.GetValue(),
            "footprint": fp.GetFPIDAsString(),
            "source_instance": fp.GetField("SourceInstance").GetText(),
            "schematic_path": fp.GetPath().AsString(),
        }
        expected_identity = {
            "mpn": expected_attrs["mpn"],
            "footprint": expected_attrs["footprint"],
            "source_instance": paths[ref],
            "schematic_path": expected_path,
        }
        if actual_identity != expected_identity:
            raise ValueError(
                f"component identity mismatch {ref}: {actual_identity} != {expected_identity}"
            )
        identity_rows.append({"reference": ref, **actual_identity})
    (out / "verification/component-identity.json").write_text(
        json.dumps(sorted(identity_rows, key=lambda row: row["reference"]), indent=2) + "\n"
    )
    rules = baseline.with_suffix(".kicad_dru").read_text().replace("'nc'", "'u_ref-nc'")
    new_names = [
        "hot5_uv_sense",
        "hot5_uv_raw",
        "hot5_ok_hot",
        "outb",
        "u_hot5_schmitt-nc",
        "ocp_kelvin_p",
    ]
    for side in ("A", "B"):
        old = f"{side}.NetName == 'hot5'"
        rules = rules.replace(
            old, "(" + " || ".join([old] + [f"{side}.NetName == '{n}'" for n in new_names]) + ")"
        )
    (out / "section.kicad_dru").write_text(rules)
    receipt = {
        "baseline_sha256": digest(baseline),
        "board_sha256": digest(out / "section.kicad_pcb"),
        "source_net_sha256": digest(out / "frozen/default.net"),
        "layout_sha256": digest(HERE / "hot5-layout.json"),
        "components": len(saved.GetFootprints()),
        "source_pad_nets_match": True,
        "retained_copper": len(before) - len(removed),
        "renamed_copper": layout.get("rename_copper", {}),
        "resized_vias": layout.get("resize_vias", {}),
        "source_component_identity_matches": True,
        "removed_copper": removed,
        "new_copper": additions,
        "physical": "NOT_RUN",
    }
    (out / "verification/build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("new_copper",)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    build(parser.parse_args().baseline)
