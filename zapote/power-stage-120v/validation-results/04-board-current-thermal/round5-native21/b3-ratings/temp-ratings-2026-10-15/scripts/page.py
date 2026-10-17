import sys
pages=open(sys.argv[1],errors='replace').read().split('\f')
for n in sys.argv[2:]:
    print(f"===== PDF page {n}"); print(pages[int(n)-1])
