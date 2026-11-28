import pcbnew,sys,collections
b=pcbnew.LoadBoard(sys.argv[1])
pads=[]
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD: pads.append((f.GetReference(),p))
n=0; refs=collections.Counter(); tented=collections.Counter()
for t in b.GetTracks():
    if t.GetClass()!='PCB_VIA': continue
    pos=t.GetPosition()
    for ref,p in pads:
        if p.GetBoundingBox().Contains(pos) and p.HitTest(pos):
            n+=1; refs[ref[0]]+=1; break
print('vias with centre inside an SMD pad:',n,dict(refs))
