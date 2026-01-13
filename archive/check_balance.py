
import sys

def check_balance(file_path):
    print(f"Checking {file_path}")
    with open(file_path, 'r') as f:
        content = f.read()
    
    stack = []
    line = 1
    col = 1
    
    for i, char in enumerate(content):
        if char == '\n':
            line += 1
            col = 1
        else:
            col += 1
            
        if char == '(':
            stack.append((line, col))
        elif char == ')':
            if not stack:
                print(f"Error: Unexpected closing parenthesis at line {line}, col {col}")
                return False
            stack.pop()
            
    if stack:
        first = stack[0]
        print(f"Error: Unclosed parenthesis starting at line {first[0]}, col {first[1]} (Count: {len(stack)})")
        return False
        
    print("Success: Parentheses are balanced.")
    return True

if __name__ == "__main__":
    check_balance(sys.argv[1])
