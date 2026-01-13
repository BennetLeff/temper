def check():
    with open("pcb/temper_fixed.kicad_pcb", "r") as f:
        content = f.read()

    stack = []
    for i, char in enumerate(content):
        if char == "(":
            stack.append(i)
        elif char == ")":
            if not stack:
                print(f"Error: Unexpected closing paren at index {i}")
                print(content[i - 50 : i + 50])
                return
            stack.pop()

    if stack:
        print(f"Error: Unclosed parens at indices: {stack[:5]}...")
        idx = stack[-1]
        print(f"Last unclosed paren at {idx}:")
        print(content[idx : idx + 100])


if __name__ == "__main__":
    check()
