#!/usr/bin/env python3
"""Extract readable text from a saved HTML page (drops script/style/nav noise). usage: python3 -I scripts/html_text.py page.html > page.txt"""
import html, re, sys
from html.parser import HTMLParser
class P(HTMLParser):
    def __init__(s): super().__init__(); s.out=[]; s.skip=0
    def handle_starttag(s, t, a):
        if t in ("script","style","noscript","svg"): s.skip+=1
        if t in ("p","br","li","h1","h2","h3","h4","tr","div","td"): s.out.append("\n")
    def handle_endtag(s, t):
        if t in ("script","style","noscript","svg") and s.skip: s.skip-=1
    def handle_data(s, d):
        if not s.skip: s.out.append(d)
p=P(); p.feed(open(sys.argv[1], encoding="utf-8", errors="replace").read())
t=re.sub(r"[ \t]+"," ","".join(p.out)); t=re.sub(r"\n\s*\n+","\n",t)
print(t.strip())
