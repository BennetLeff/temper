import pcbnew,sys,collections
b=pcbnew.LoadBoard(sys.argv[1])
c=collections.Counter()
pads=[(f.GetReference(),p) for f in b.GetFootprints() for p in f.Pads() if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD]
for t in b.GetTracks():
    if t.GetClass()!='PCB_VIA': continue
    pos=t.GetPosition()
    for ref,p in pads:
        if p.HitTest(pos): c[ref]+=1; break
print({k:v for k,v in c.items() if k.startswith('U')})
