from kiutils.items.brditems import Via
import inspect

with open("via_inspect.txt", "w") as f:
    f.write(f"Via __init__ varnames: {Via.__init__.__code__.co_varnames}\n")
    try:
        sig = inspect.signature(Via.__init__)
        f.write(f"Via __init__ signature: {sig}\n")
    except Exception as e:
        f.write(f"Could not get signature: {e}\n")

    f.write("\nDir of Via:\n")
    f.write("\n".join(dir(Via)))

    # Try to create a dummy via to see what attributes it has
    try:
        v = Via()
        f.write("\n\nAttributes of empty Via:\n")
        f.write(str(v.__dict__))
    except Exception as e:
        f.write(f"\n\nCould not create empty Via: {e}")
