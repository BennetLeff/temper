
from kiutils.board import Board
import sys

# Create a dummy board or just inspect class
try:
    print("Checking kiutils structure...")
    # we can't easily instantiate a full board without a file, 
    # but we can inspect the types if we import them
    from kiutils.footprint import Footprint, Position
    from kiutils.items.common import Position
    
    p = Position()
    print(f"Position attributes: {dir(p)}")
    
    f = Footprint()
    print(f"Footprint attributes: {dir(f)}")
    
    if hasattr(f, 'position'):
        print(f"Footprint.position type: {type(f.position)}")
        
except ImportError:
    print("kiutils not installed or path issue")
except Exception as e:
    print(f"Error: {e}")
