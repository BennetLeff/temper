
from kiutils.footprint import Footprint
try:
    print("Checking Pad via Footprint...")
    # Attempt to see what class imports are available or where Pad is
    # Just printing dir(kiutils.footprint) might help
    import kiutils.footprint
    print(dir(kiutils.footprint))
except Exception as e:
    print(e)
