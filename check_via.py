
from kiutils.items.brditems import Via
v = Via()
print(f"Via net type default: {type(v.net)}")
# It seems kiutils initializes net as None or int?
# In a loaded board, it might be int.
# We can't load a board easily without a file, but we can assume based on kiutils docs/history.
# Most parsers store net code (int) in .net attribute for items.
print("Finished check.")
