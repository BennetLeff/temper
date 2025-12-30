
from kiutils.board import Board
import sys

b = Board.from_file(sys.argv[1])
if b.footprints:
    fp = b.footprints[0]
    print(f"Dir: {dir(fp)}")
    print(f"Props: {fp.__dict__}")
