import json,subprocess,sys,time
def curl(a): return subprocess.run(["curl","-s","-m","40","-A","parts-check"]+a,capture_output=True).stdout
for code in sys.argv[1:]:
    s=json.loads(curl(["-X","POST","https://pro.easyeda.com/api/v2/devices/searchByCodes","--data-urlencode",f"codes[]={code}"]))
    if not s.get("result"): print(code,'no record'); continue
    dev=s["result"][0]; fp=dev["footprint"]["uuid"]
    c=json.loads(curl([f"https://pro.easyeda.com/api/components/{fp}"]))
    open(code+'.txt','w').write(c["result"]["dataStr"])
    print(code,dev["footprint"].get("display_title"),dev["attributes"].get("Manufacturer Part"),len(c["result"]["dataStr"]))
    time.sleep(0.5)
