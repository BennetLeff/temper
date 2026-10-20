"""KiCad native API adapter. Circuit and layout decisions live in Rust/TSV, not here."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
CAD = ROOT / 'cad'
BOARD = CAD / 'differential-probe.kicad_pcb'
LIB = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
LAYERS = {'F.Cu': k.F_Cu, 'In1.Cu': k.In1_Cu, 'In2.Cu': k.In2_Cu, 'B.Cu': k.B_Cu,
          'Edge.Cuts': k.Edge_Cuts, 'F.SilkS': k.F_SilkS, 'Dwgs.User': k.Dwgs_User}

def vec(x: float, y: float) -> k.VECTOR2I:
    return k.VECTOR2I(k.FromMM(float(x)), k.FromMM(float(y)))

def save(board: k.BOARD) -> None:
    k.SaveBoard(str(BOARD), board)

def export_pads(board: k.BOARD) -> None:
    lines = ['reference\tpin\tnet\tx\ty\tw\th\tangle\tthrough']
    for fp in board.GetFootprints():
        for p in fp.Pads():
            xy, sz = p.GetPosition(), p.GetSize()
            lines.append(f'{fp.GetReference()}\t{p.GetNumber()}\t{p.GetNetname()}\t{k.ToMM(xy.x):.6f}\t{k.ToMM(xy.y):.6f}\t{k.ToMM(sz.x):.6f}\t{k.ToMM(sz.y):.6f}\t{p.GetOrientationDegrees():.3f}\t{int(p.GetAttribute() == k.PAD_ATTRIB_PTH)}')
    (ROOT / 'validation/pcb-pads.tsv').write_text('\n'.join(lines) + '\n')
    lines = ['reference\tvalue\tfootprint\tdnp']
    for fp in board.GetFootprints():
        lines.append(f'{fp.GetReference()}\t{fp.GetValue()}\t{fp.GetFPID().GetLibItemName()}\t{int(bool(fp.GetAttributes() & k.FP_DNP))}')
    (ROOT / 'validation/pcb-footprints.tsv').write_text('\n'.join(lines) + '\n')
    lines = ['kind\tnet\tlayer\twidth\tx1\ty1\tx2\ty2']
    for item in board.GetTracks():
        a, b = item.GetStart(), item.GetEnd()
        kind = 'via' if isinstance(item, k.PCB_VIA) else 'track'
        lines.append(f'{kind}\t{item.GetNetname()}\t{board.GetLayerName(item.GetLayer())}\t{k.ToMM(item.GetWidth()):.6f}\t{k.ToMM(a.x):.6f}\t{k.ToMM(a.y):.6f}\t{k.ToMM(b.x):.6f}\t{k.ToMM(b.y):.6f}')
    (ROOT / 'validation/pcb-tracks.tsv').write_text('\n'.join(lines) + '\n')

def seed() -> None:
    board = k.BOARD()
    board.SetCopperLayerCount(4)
    board.GetDesignSettings().SetBoardThickness(k.FromMM(1.6))
    xml = ET.parse(ROOT / 'validation/netlist.xml').getroot()
    nets = {}
    pin_nets = {}
    for node in xml.findall('nets/net'):
        name = node.attrib['name']
        net = k.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net
        for pin in node.findall('node'):
            pin_nets[(pin.attrib['ref'], pin.attrib['pin'])] = name
    extra = {}
    for line in (ROOT / 'layout/landings.tsv').read_text().splitlines()[1:]:
        ref, pin, net = line.split('\t')
        extra[(ref, pin)] = net
    components = {n.attrib['ref']: n for n in xml.findall('components/comp')}
    labels = {a[0]: (a[1], a[2]) for a in (line.split('\t') for line in
              (ROOT / 'layout/references.tsv').read_text().splitlines()[1:])}
    for line in (ROOT / 'layout/placement.tsv').read_text().splitlines()[1:]:
        ref, x, y, angle, override = line.split('\t')
        node = components.get(ref)
        library_id = override or node.findtext('footprint')
        lib, name = library_id.split(':')
        libpath = CAD / 'Probe.pretty' if lib == 'Probe' else LIB / f'{lib}.pretty'
        fp = k.FootprintLoad(str(libpath), name)
        if fp is None:
            raise ValueError(f'Could not load {library_id}')
        fp.SetReference(ref)
        fp.SetValue(node.findtext('value') if node is not None else ref)
        fp.SetFPID(k.LIB_ID(lib, name))
        if node is not None:
            path = node.find('sheetpath').attrib['tstamps'] + node.findtext('tstamps')
            fp.SetPath(k.KIID_PATH(path))
            if node.find("property[@name='dnp']") is not None:
                fp.SetAttributes(fp.GetAttributes() | k.FP_DNP)
        else:
            fp.SetAttributes(fp.GetAttributes() | k.FP_BOARD_ONLY | k.FP_EXCLUDE_FROM_BOM | k.FP_EXCLUDE_FROM_POS_FILES)
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(float(angle))
        fp.Reference().SetTextSize(vec(.8, .8))
        fp.Reference().SetTextThickness(k.FromMM(.12))
        fp.Reference().SetTextAngle(k.EDA_ANGLE(0, k.DEGREES_T))
        fp.Reference().SetLayer(k.F_SilkS)
        fp.Reference().SetPosition(vec(*labels[ref]))
        fp.Value().SetVisible(False)
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            name_net = pin_nets.get(key) if node is not None else extra.get(key)
            if name_net:
                pad.SetNet(nets[name_net])
        board.Add(fp)
    save(board)
    export_pads(board)
    print(f'Seeded {len(list(board.GetFootprints()))} footprints')

def apply() -> None:
    board = k.LoadBoard(str(BOARD))
    nets = {str(n.GetNetname()): n for n in board.GetNetInfo().NetsByNetcode().values()}
    for item in list(board.GetTracks()) + list(board.Zones()) + list(board.GetDrawings()):
        board.Remove(item)
    for line in (ROOT / 'layout/copper.tsv').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        a = line.split('\t')
        kind = a[0]
        if kind == 'track':
            _, net, layer, width, x1, y1, x2, y2 = a
            t = k.PCB_TRACK(board)
            t.SetStart(vec(x1, y1)); t.SetEnd(vec(x2, y2))
            t.SetWidth(k.FromMM(float(width))); t.SetLayer(LAYERS[layer]); t.SetNet(nets[net]); board.Add(t)
        elif kind == 'via':
            _, net, x, y, diameter, drill = a
            v = k.PCB_VIA(board)
            v.SetPosition(vec(x, y)); v.SetWidth(k.FromMM(float(diameter)))
            v.SetDrill(k.FromMM(float(drill))); v.SetViaType(k.VIATYPE_THROUGH)
            v.SetLayerPair(k.F_Cu, k.B_Cu); v.SetNet(nets[net]); board.Add(v)
        elif kind in ('line', 'circle'):
            _, layer, width, x1, y1, x2, y2 = a
            s = k.PCB_SHAPE(board)
            s.SetShape(k.SHAPE_T_SEGMENT if kind == 'line' else k.SHAPE_T_CIRCLE)
            s.SetStart(vec(x1, y1)); s.SetEnd(vec(x2, y2)); s.SetWidth(k.FromMM(float(width))); s.SetLayer(LAYERS[layer]); board.Add(s)
        elif kind == 'text':
            _, layer, x, y, size, text = a
            t = k.PCB_TEXT(board); t.SetText(text.replace('\\n','\n')); t.SetPosition(vec(x,y))
            t.SetTextSize(vec(size,size)); t.SetTextThickness(k.FromMM(.15)); t.SetLayer(LAYERS[layer]); board.Add(t)
        elif kind in ('zone','keepout'):
            _, net, layer, x1, y1, x2, y2 = a
            z = k.ZONE(board); z.SetLayer(LAYERS[layer])
            z.Outline().NewOutline()
            for x,y in [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]:
                p = vec(x,y); z.Outline().Append(p.x,p.y)
            if kind == 'zone':
                z.SetNet(nets[net]); z.SetLocalClearance(k.FromMM(.25)); z.SetMinThickness(k.FromMM(.15))
                z.SetPadConnection(k.ZONE_CONNECTION_FULL)
            else:
                z.SetIsRuleArea(True); z.SetDoNotAllowZoneFills(True)
                z.SetDoNotAllowTracks(net == 'all'); z.SetDoNotAllowVias(net == 'all')
                z.SetDoNotAllowPads(False)
            board.Add(z)
        else:
            raise ValueError(f'Unknown command: {kind}')
    board.BuildConnectivity()
    k.ZONE_FILLER(board).Fill(board.Zones())
    save(board)
    export_pads(board)
    print(f'Saved {BOARD}; {len(list(board.GetTracks()))} track/via items')

def mutant(kind: str, target: str) -> None:
    """Known-bad native fixtures prove the custom spacing checks are active."""
    board = k.LoadBoard(str(BOARD))
    if kind == 'clearance':
        track = k.PCB_TRACK(board)
        track.SetStart(vec(16, 24)); track.SetEnd(vec(16, 26))
        track.SetWidth(k.FromMM(.25)); track.SetLayer(k.F_Cu)
        track.SetNet(board.FindNet('GND')); board.Add(track)
    elif kind == 'slot':
        removed = 0
        for item in list(board.GetDrawings()):
            if item.GetLayer() != k.Edge_Cuts:
                continue
            points = (item.GetStart(), item.GetEnd())
            if all(38 <= k.ToMM(p.x) <= 40 and 28 <= k.ToMM(p.y) <= 38 for p in points):
                board.Remove(item); removed += 1
        assert removed == 4, f'Expected four C1 slot edges, got {removed}'
    else:
        raise ValueError(kind)
    k.SaveBoard(target, board)

if __name__ == '__main__':
    if sys.argv[1] == 'seed': seed()
    elif sys.argv[1] == 'apply': apply()
    elif sys.argv[1] == 'pads': export_pads(k.LoadBoard(str(BOARD)))
    elif sys.argv[1] == 'mutant': mutant(sys.argv[2], sys.argv[3])
    else: raise ValueError('Expected seed, apply, pads or mutant')
