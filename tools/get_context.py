import sys
import json
import urllib.request
import urllib.error
import subprocess
import os

BASE_URL = "https://eco.bennetleff.workers.dev"
USER_ID = "temper-agent"

def get_issue(issue_id):
    # Use bd CLI to get issue details
    try:
        # Check if bd is in path, otherwise assume it's accessible or use relative path if known
        # We will use 'bd show <id> --json'
        # Assuming 'bd' is in PATH or we use the local script if available
        # The user seems to use 'bd' command.
        
        cmd = ["bd", "show", issue_id, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return None, f"Error calling bd: {result.stderr}"
            
        return json.loads(result.stdout), None
    except Exception as e:
        return None, str(e)

def search_memories(query):
    payload = {
        "query": query,
        "userId": USER_ID,
        "limit": 5,
        "minScore": 0.7
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{BASE_URL}/memories/search", 
            data=data, 
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                return json.load(response).get("results", []), None
            else:
                return [], f"Eco error: {response.status}"
    except Exception as e:
        return [], str(e)

def format_context(issue, memories):
    output = []
    
    # 1. Task Context (from Beads)
    output.append(f"# TASK: {issue['id']} - {issue['title']}")
    output.append(f"Status: {issue['status'].upper()} | Priority: {issue['priority']}")
    output.append(f"Type: {issue['issue_type']}")
    output.append("-" * 40)
    output.append(issue.get('description', '(No description)'))
    output.append("-" * 40)
    
    # 2. Memory Context (from Eco)
    output.append("\n# RELEVANT MEMORIES (Eco)")
    if not memories:
        output.append("(No high-relevance memories found)")
    else:
        for i, item in enumerate(memories):
            mem = item['memory']
            score = item['score']
            output.append(f"\n[{i+1}] (Score: {score:.2f}) {mem['content'][:200]}...")
            output.append(f"    Full content: {mem['content']}")
            
    return "\n".join(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 tools/get_context.py <issue_id>")
        sys.exit(1)
        
    issue_id = sys.argv[1]
    
    print(f"Fetching context for {issue_id}...")
    
    # Parallel fetch could be better, but sequential is safer for a simple script
    issue, err = get_issue(issue_id)
    if err:
        print(f"Failed to fetch issue: {err}")
        sys.exit(1)
    if not issue: # bd show might return empty list or null if not found
        print("Issue not found")
        sys.exit(1)
        
    # If issue is a list (bd show can return list), take first
    if isinstance(issue, list):
        if not issue:
            print("Issue not found")
            sys.exit(1)
        issue = issue[0]
        
    print(f"Found task: {issue['title']}")
    
    # Construct search query from title + keywords
    query = f"{issue['title']} {issue.get('issue_type', '')}"
    print(f"Searching Eco for: '{query}'...")
    
    memories, mem_err = search_memories(query)
    if mem_err:
        print(f"Warning: Failed to search memories: {mem_err}")
    
    print("\n" + "="*60)
    print(format_context(issue, memories))
    print("="*60)
