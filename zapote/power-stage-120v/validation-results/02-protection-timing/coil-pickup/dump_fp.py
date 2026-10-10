import pcbnew, json, sys
b = pcbnew.LoadBoard(sys.argv[1])
refs = set(sys.argv[3].split(','))
out = {}
for fp in b.GetFootprints():
    r = fp.GetReference()
    if r not in refs: continue
    p = fp.GetPosition()
    pads = []
    for pd in fp.Pads():
        q = pd.GetPosition()
        pads.append(dict(num=pd.GetNumber(), net=pd.GetNetname(), x=q.x/1e6, y=q.y/1e6,
                         layers=[b.GetLayerName(l) for l in pd.GetLayerSet().Seq() if pcbnew.IsCopperLayer(l)][:4]))
    out[r] = dict(x=p.x/1e6, y=p.y/1e6, rot=fp.GetOrientationDegrees(), side='B' if fp.IsFlipped() else 'F',
                  value=fp.GetValue(), fpid=str(fp.GetFPID().GetLibItemName()), pads=pads)
json.dump(out, open(sys.argv[2], 'w'), indent=1)
