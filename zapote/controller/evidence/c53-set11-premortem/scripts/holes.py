import pcbnew,sys,collections
b=pcbnew.LoadBoard(sys.argv[1])
pth=collections.Counter(); npth=collections.Counter()
for t in b.GetTracks():
    if t.GetClass()=='PCB_VIA': pth[round(pcbnew.ToMM(t.GetDrillValue()),3)]+=1
for f in b.GetFootprints():
    for p in f.Pads():
        d=p.GetDrillSize().x
        if d>0:
            (npth if p.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH else pth)[round(pcbnew.ToMM(d),3)]+=1
print('PTH',sorted(pth.items()),sum(pth.values())); print('NPTH',sorted(npth.items()),sum(npth.values()))
# via types
vt=collections.Counter()
for t in b.GetTracks():
    if t.GetClass()=='PCB_VIA': vt[(t.GetViaType(),round(pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)),2))]+=1
print(vt)
# min track width per interesting net
w=collections.defaultdict(lambda:[9,0])
for t in b.GetTracks():
    if t.GetClass()=='PCB_TRACK':
        n=t.GetNetname(); x=pcbnew.ToMM(t.GetWidth()); w[n][0]=min(w[n][0],x); w[n][1]+=pcbnew.ToMM(t.GetLength())
for n in ['V15_BLW','v15_selv','V_BLOWER','sw_12','sw_3v3','v3v3','V12_FAN2','sw_fan2','selv_gnd','USB_DP','USB_DN','MCU_EN','I2C_SCL_BOOT']:
    print(n,w.get(n))
for z in b.Zones(): print('zone',z.GetNetname(),z.GetLayerSet().Name() if hasattr(z.GetLayerSet(),'Name') else '', z.GetZoneName(), z.IsFilled())
