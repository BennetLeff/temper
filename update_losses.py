import os
import re

directory = "/Users/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/losses"
pattern = re.compile(r"def __call__\((.*?)\) -> LossResult:", re.DOTALL)

updated_files = []

for root, dirs, files in os.walk(directory):
    for file in files:
        if file.endswith(".py") and file != "base.py" and file != "types.py" and file != "manufacturing.py":
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            
            def replace_call(match):
                args = match.group(1)
                if "**kwargs" in args:
                    return match.group(0)
                
                # Add **kwargs: Any before the closing parenthesis
                args_clean = args.rstrip()
                if args_clean.endswith(","):
                    new_args = f"{args_clean} **kwargs: Any"
                else:
                    new_args = f"{args_clean}, **kwargs: Any"
                return f"def __call__({new_args}) -> LossResult:"

            new_content = pattern.sub(replace_call, content)
            if new_content != content:
                # Ensure 'Any' is imported
                if "from typing import" in new_content and "Any" not in new_content:
                    new_content = new_content.replace("from typing import ", "from typing import Any, ")
                elif "import Any" not in new_content and "from typing import" not in new_content:
                    # Find a good place for import
                    if "import jax" in new_content:
                        new_content = new_content.replace("import jax", "from typing import Any\nimport jax")
                
                with open(path, "w") as f:
                    f.write(new_content)
                updated_files.append(file)

print(f"Updated {len(updated_files)} files: {', '.join(updated_files)}")
