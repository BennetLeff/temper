#!/usr/bin/env python3
"""Find a regex in a datasheet PDF, page by page (pdftotext -layout), and print 'page: line'.

    python3 -I ds_find.py FILE.pdf REGEX [REGEX ...]

Used to put the PDF page index (1-based) on every datasheet value this desk pass cites. The PDFs are untrusted
downloads kept outside the repo (worktrees/runs-native21/...); this script only reads text out of them.
"""
import re
import subprocess
import sys


def pages(path):
    out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    return out.split("\f")


def main():
    path, pats = sys.argv[1], [re.compile(p, re.I) for p in sys.argv[2:]]
    for i, txt in enumerate(pages(path), 1):
        for line in txt.splitlines():
            if any(p.search(line) for p in pats):
                print(f"p.{i}: {' '.join(line.split())[:220]}")


if __name__ == "__main__":
    main()
