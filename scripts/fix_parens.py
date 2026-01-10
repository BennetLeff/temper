
import sys

def balance_parens(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    open_count = content.count('(')
    close_count = content.count(')')
    
    print(f"Original: (={open_count}, )={close_count}")
    
    if open_count == close_count:
        print("Already balanced.")
        return
    
    if close_count > open_count:
        # Too many closing. Let's find where they are.
        # Usually they are at the very end.
        diff = close_count - open_count
        print(f"Removing {diff} trailing closing parens...")
        content = content.rstrip()
        # Remove trailing parens precisely
        for _ in range(diff):
            if content.endswith(')'):
                content = content[:-1]
            else:
                print("Warning: Hit non-paren while balancing!")
                break
        content = content.rstrip()
    else:
        # Too few closing.
        diff = open_count - close_count
        print(f"Adding {diff} closing parens...")
        content = content.rstrip() + ("\n" + ")" * diff) + "\n"
        
    with open(filepath, 'w') as f:
        f.write(content)
        
    # Re-verify
    with open(filepath, 'r') as f:
        new_content = f.read()
    print(f"New: (={new_content.count('(')}, )={new_content.count(')')}")

if __name__ == "__main__":
    balance_parens(sys.argv[1])
