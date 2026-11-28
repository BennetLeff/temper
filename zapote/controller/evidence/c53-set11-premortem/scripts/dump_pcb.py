import pcbnew, json, sys
b=pcbnew.LoadBoard(sys.argv[1])
out=[]
for f in b.GetFootprints():
    p=f.GetPosition()
    d={'ref':f.GetReference(),'val':f.GetValue(),'fpid':f.GetFPID().GetUniStringLibId(),
       'x':pcbnew.ToMM(p.x),'y':pcbnew.ToMM(p.y),'rot':f.GetOrientationDegrees(),
       'layer':f.GetLayerName(),'attr':f.GetAttributes(),'dnp':f.IsDNP() if hasattr(f,'IsDNP') else None,
       'pads':[]}
    try:
        d['fields']={fl.GetName():fl.GetText() for fl in f.GetFields()}
    except Exception as e: d['fields']=str(e)
    for pad in f.Pads():
        pp=pad.GetPosition(); sz=pad.GetSize()
        d['pads'].append({'n':pad.GetNumber(),'net':pad.GetNetname(),'x':pcbnew.ToMM(pp.x),'y':pcbnew.ToMM(pp.y),
                          'sx':pcbnew.ToMM(sz.x),'sy':pcbnew.ToMM(sz.y),'attr':pad.GetAttribute(),'drill':pcbnew.ToMM(pad.GetDrillSize().x),
                          'shape':pad.GetShape() if hasattr(pad,'GetShape') else None})
    out.append(d)
json.dump(out,open(sys.argv[2],'w'))
bb=b.GetBoardEdgesBoundingBox()
print(len(out),'footprints; edges',pcbnew.ToMM(bb.GetX()),pcbnew.ToMM(bb.GetY()),pcbnew.ToMM(bb.GetWidth()),pcbnew.ToMM(bb.GetHeight()), 'layers',b.GetCopperLayerCount())
