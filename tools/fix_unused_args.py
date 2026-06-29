"""Auto-fix ARG001/ARG002 ruff errors by prefixing unused args with `_`.

Reads ruff JSON on stdin, modifies source files in place.
Usage: uv run ruff check packages/ --output-format=json | uv run python tools/fix_unused_args.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    data = json.load(sys.stdin)
    arg_errors = [d for d in data if d["code"] in ("ARG001", "ARG002")]

    if not arg_errors:
        print("No ARG errors found.")
        return

    # Group by (filename, lineno, message)
    by_file: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))

    for err in arg_errors:
        lineno = err["location"]["row"]
        # Extract arg name from message like "Unused method argument: `epoch`"
        msg = err["message"]
        name_start = msg.rfind("`") 
        if name_start == -1:
            continue
        name_end = msg.rfind("'")
        # Actually the message format is: "Unused ... argument: `name`"
        import re
        m = re.search(r"`(\w+)`", msg)
        if not m:
            continue
        arg_name = m.group(1)
        if arg_name.startswith("_"):
            continue
        by_file[err["filename"]][lineno].append(arg_name)

    fixed_count = 0
    for filename, line_args in sorted(by_file.items()):
        path = Path(filename)
        if not path.exists():
            print(f"SKIP: {filename} (not found)")
            continue

        content = path.read_text()
        lines = content.splitlines(keepends=True)
        changed = False

        for lineno, arg_names in sorted(line_args.items(), reverse=True):
            idx = lineno - 1
            if idx >= len(lines):
                continue
            line = lines[idx]
            # Don't touch lines with noqa for ARG
            if "# noqa:" in line and "ARG" in line:
                continue
            for arg_name in arg_names:
                # Replace the FIRST occurrence of the arg name on its own
                # (as a word boundary), but only if it's not already prefixed
                if f"_{arg_name}" in line:
                    continue
                # Replace arg_name with _arg_name, matching word boundaries
                import re
                pat = rf"\b{re.escape(arg_name)}\b"
                new_line, count = re.subn(pat, f"_{arg_name}", line, count=1)
                if count > 0 and new_line != line:
                    line = new_line
                    changed = True
                    fixed_count += 1
            if changed:
                lines[idx] = line

        if changed:
            path.write_text("".join(lines))
            print(f"FIXED: {filename}")

    print(f"\nFixed {fixed_count} ARG errors across {len(by_file)} files.")


if __name__ == "__main__":
    main()
