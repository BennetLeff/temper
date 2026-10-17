import sys, urllib.request
url, out = sys.argv[1], sys.argv[2]
req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36","Accept":"application/pdf,*/*","Accept-Language":"en-US,en;q=0.9"})
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read(); print(r.status, len(data), r.headers.get("content-type"))
        open(out,"wb").write(data)
except Exception as e:
    print("ERR", e)
