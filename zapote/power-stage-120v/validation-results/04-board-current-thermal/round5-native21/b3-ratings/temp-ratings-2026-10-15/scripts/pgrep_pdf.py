import sys, subprocess, re
pdf, pat = sys.argv[1], sys.argv[2]
n = int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout).group(1))
rx = re.compile(pat, re.I)
for p in range(1, n + 1):
    t = subprocess.run(['/opt/homebrew/bin/pdftotext', '-layout', '-f', str(p), '-l', str(p), pdf, '-'], capture_output=True, text=True).stdout
    for line in t.splitlines():
        if rx.search(line):
            print(f"p{p}: {line.strip()[:220]}")
