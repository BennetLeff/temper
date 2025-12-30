import sys

with open("routed_v3_clean.kicad_pcb", "r+b") as f:
    f.seek(44365)
    print("Found zone, truncating...")
    f.truncate()
    f.write(b")\n")
print("Done.")