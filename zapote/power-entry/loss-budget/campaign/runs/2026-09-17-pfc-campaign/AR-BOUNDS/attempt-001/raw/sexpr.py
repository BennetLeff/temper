def parse(text):
    toks=[]; i=0; n=len(text)
    while i<n:
        c=text[i]
        if c in ' \t\r\n': i+=1; continue
        if c=='(' or c==')': toks.append(c); i+=1; continue
        if c=='"':
            j=i+1; buf=[]
            while j<n:
                if text[j]=='\\': buf.append(text[j+1]); j+=2; continue
                if text[j]=='"': break
                buf.append(text[j]); j+=1
            toks.append(('STR',''.join(buf))); i=j+1; continue
        j=i
        while j<n and text[j] not in ' \t\r\n()"': j+=1
        toks.append(('ATOM',text[i:j])); i=j
    pos=[0]
    def rd():
        t=toks[pos[0]]; pos[0]+=1
        if t=='(':
            lst=[]
            while toks[pos[0]]!=')': lst.append(rd())
            pos[0]+=1
            return lst
        return t
    out=[]
    while pos[0]<len(toks): out.append(rd())
    return out
