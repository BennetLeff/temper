import pcbnew,sys,collections
b=pcbnew.LoadBoard(sys.argv[1])
for z in b.Zones():
    ls=[b.GetLayerName(l) for l in z.GetLayerSet().Seq()]
    print('zone',repr(z.GetNetname()),ls,z.GetZoneName(),'filled',z.IsFilled(),'area mm2',round(z.GetFilledArea()/1e12,1) if z.IsFilled() else None, 'keepout' if z.GetIsRuleArea() else '')
for net in sys.argv[2:]:
    print('==',net)
    segs=collections.Counter()
    for t in b.GetTracks():
        if t.GetNetname()!=net: continue
        if t.GetClass()=='PCB_VIA':
            segs[('via',b.GetLayerName(t.TopLayer()),b.GetLayerName(t.BottomLayer()))]+=1
        else:
            segs[(b.GetLayerName(t.GetLayer()),pcbnew.ToMM(t.GetWidth()))]+=round(pcbnew.ToMM(t.GetLength()),1)
    for k,v in sorted(segs.items(),key=str): print('  ',k,round(v,1))
