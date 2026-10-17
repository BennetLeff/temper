import json,sys,urllib.request,time
S="https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"
for kw in sys.argv[1:]:
    body={"keyword":kw,"currentPage":1,"pageSize":15}
    req=urllib.request.Request(S,data=json.dumps(body).encode(),headers={"Content-Type":"application/json","User-Agent":"Mozilla/5.0"})
    try: d=json.load(urllib.request.urlopen(req,timeout=30))
    except Exception as e: print(kw,"ERR",e); continue
    open("raw/"+kw.replace(" ","_").replace("/","_")+".json","w").write(json.dumps(d))
    print("##",kw)
    for c in (d.get("data") or {}).get("componentPageInfo",{}).get("list",[]) or []:
        pr=[(p["startNumber"],p["productPrice"]) for p in c.get("componentPrices") or []][:3]
        print(c.get("componentCode"),c.get("componentLibraryType"),c.get("stockCount"),c.get("componentModelEn"),c.get("componentBrandEn"),(c.get("describe") or "")[:100],pr)
