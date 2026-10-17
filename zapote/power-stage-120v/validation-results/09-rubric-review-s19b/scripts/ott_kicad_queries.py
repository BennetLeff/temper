"""OTT-EMC review: pcbnew queries (run with KiCad python). Usage: KP -I ott_kicad_queries.py section.kicad_pcb"""
import sys,pcbnew,collections
b=pcbnew.LoadBoard(sys.argv[1]); c=collections.Counter()
for z in b.Zones(): c[(z.GetNetname()=='',z.GetIsRuleArea(),z.GetIslandRemovalMode())]+=1
print('OTT-10 zones (netless,rule_area,island_mode):count',dict(c))
for f in b.GetFootprints():
    if f.GetReference() in('C5','C6','C38','C39','C40','C41','Q2','Q3','Q5','Q6','BR1','L1','J1','D3','D17'):
        print('OTT-15 %s (%.1f, %.1f)'%(f.GetReference(),f.GetPosition().x/1e6,f.GetPosition().y/1e6))
    if f.GetReference()=='J4':
        for p in sorted([q for q in f.Pads() if q.GetNumber().isdigit()],key=lambda p:int(p.GetNumber())):
            print('OTT-25 J4.%s %s (%.1f, %.1f)'%(p.GetNumber(),p.GetNetname(),p.GetPosition().x/1e6,p.GetPosition().y/1e6))
