import json
import os
import hashlib
import urllib.request
import urllib.error
import time

ISSUES_FILE = ".beads/issues.jsonl"
STATE_FILE = ".beads/eco_sync_state.json"
BASE_URL = "https://eco.bennetleff.workers.dev"
USER_ID = "temper-agent"

def load_issues():
    if not os.path.exists(ISSUES_FILE):
        return {}
    
    issues = {}
    with open(ISSUES_FILE, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    issue = json.loads(line)
                    issues[issue['id']] = issue
                except json.JSONDecodeError:
                    continue
    return issues

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def compute_hash(issue):
    # Compute hash of fields we care about for sync
    content = f"{issue.get('title')}|{issue.get('description')}|{issue.get('status')}|{issue.get('priority')}"
    return hashlib.sha256(content.encode()).hexdigest()

def post_memory(content, tags, metadata):
    payload = {
        "content": content,
        "userId": USER_ID,
        "tags": tags,
        "primary_sector": "episodic", # Updates are episodic events
        "metadata": metadata
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{BASE_URL}/memories", 
            data=data, 
            headers={'Content-Type': 'application/json', 'User-Agent': 'TemperAgent/Sync'},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status in [200, 201]
    except Exception as e:
        print(f"Error posting memory: {e}")
        return False

def sync():
    print("Syncing Beads issues to Eco...")
    issues = load_issues()
    state = load_state()
    
    updates = 0
    errors = 0
    
    for issue_id, issue in issues.items():
        current_hash = compute_hash(issue)
        last_hash = state.get(issue_id)
        
        if current_hash != last_hash:
            # Determine what changed (simple heuristic)
            is_new = last_hash is None
            
            if is_new:
                action = "CREATED"
                desc = f"New Issue {issue_id}: {issue['title']}"
            else:
                action = "UPDATED"
                desc = f"Update on {issue_id} ({issue['status']}): {issue['title']}"
            
            # Construct memory content
            memory_content = f"BEADS {action}: {desc}\n\nStatus: {issue.get('status')}\nPriority: {issue.get('priority')}\n\n{issue.get('description', '')}"
            
            # Truncate if needed
            if len(memory_content) > 5000:
                memory_content = memory_content[:5000] + "... (truncated)"
            
            tags = ["beads", "sync", action.lower(), issue.get("issue_type", "task")]
            metadata = {
                "issueId": issue_id,
                "syncHash": current_hash,
                "timestamp": time.time()
            }
            
            print(f"Syncing {issue_id} ({action})...")
            if post_memory(memory_content, tags, metadata):
                state[issue_id] = current_hash
                updates += 1
                # Small delay to avoid rate limits
                time.sleep(0.5)
            else:
                errors += 1
    
    save_state(state)
    print(f"Sync complete. {updates} updates, {errors} errors.")

if __name__ == "__main__":
    sync()
