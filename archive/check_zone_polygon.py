try:
    from kiutils.board import ZonePolygon
    print("Found in board")
except ImportError:
    print("Not in board")
