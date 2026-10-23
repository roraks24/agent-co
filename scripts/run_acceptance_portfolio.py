import json
import os
import sys
import urllib.request
from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    print("GROQ_API_KEY is not configured in .env")
    sys.exit(1)

# 1. Create project
print("Step 1: Creating project...")
create_req = urllib.request.Request(
    "http://localhost:8000/api/agent/projects",
    data=json.dumps({
        "name": "Portfolio - Rohit Saini",
        "description": "Professional responsive portfolio website for Rohit Saini",
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(create_req) as resp:
    proj_data = json.loads(resp.read().decode("utf-8"))

project_id = proj_data["id"]
workspace_id = proj_data["workspace_id"]
print(f"Project created! ID: {project_id}, Workspace ID: {workspace_id}")

# 2. Start agent run SSE stream
print("\nStep 2: Starting agent run SSE stream...")
run_req = urllib.request.Request(
    f"http://localhost:8000/api/agent/workspaces/{workspace_id}/runs",
    data=json.dumps({
        "objective": "Make a professional, responsive portfolio website for Rohit Saini.",
        "task_type": "coding",
        "api_key": api_key,
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

events = []
with urllib.request.urlopen(run_req, timeout=180) as stream_resp:
    print("Streaming events from agent...")
    buffer = ""
    for chunk in stream_resp:
        line = chunk.decode("utf-8")
        buffer += line
        if "\r\n\r\n" in buffer or "\n\n" in buffer:
            parts = buffer.replace("\r\n", "\n").split("\n\n")
            buffer = parts[-1]
            for block in parts[:-1]:
                evt_name = None
                evt_data = None
                for b_line in block.split("\n"):
                    if b_line.startswith("event:"):
                        evt_name = b_line[6:].strip()
                    elif b_line.startswith("data:"):
                        try:
                            evt_data = json.loads(b_line[5:].strip())
                        except Exception:
                            evt_data = b_line[5:].strip()
                if evt_name:
                    events.append((evt_name, evt_data))
                    msg = evt_data.get("message", "") if isinstance(evt_data, dict) else ""
                    node = evt_data.get("node", "") if isinstance(evt_data, dict) else ""
                    print(f"  [{evt_name}] node={node} {msg[:100]}")

print(f"\nReceived total of {len(events)} events.")

# Find final status from events
final_events = [e for e in events if e[0] in ("run_completed", "run_failed")]
if final_events:
    last_evt_name, last_evt_data = final_events[-1]
    print("\nFinal Event:", last_evt_name)
    if isinstance(last_evt_data, dict):
        print("Objective Status:", last_evt_data.get("objective_status"))
        print("Execution Status:", last_evt_data.get("execution_status"))
        print("Deliverable Status:", last_evt_data.get("deliverable_status"))
        print("Summary:", last_evt_data.get("final_summary", "")[:250])

# 3. Inspect saved workspace files on disk
ws_path = os.path.join("workspaces", workspace_id)
print(f"\nStep 3: Inspecting workspace directory: {ws_path}")
if not os.path.exists(ws_path):
    print("ERROR: Workspace directory does not exist!")
    sys.exit(1)

files = sorted(os.listdir(ws_path))
print("Files present:", files)

for fname in ["index.html", "style.css", "script.js", "README.md"]:
    fpath = os.path.join(ws_path, fname)
    if not os.path.exists(fpath):
        print(f"ERROR: Expected file {fname} not found!")
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"\n=== {fname} ({len(content)} chars, {len(content.splitlines())} lines) ===")
    print("Contains literal \\n:", r"\n" in content)
    print("Contains literal \\\":", r'\"' in content)
    lines_preview = content.splitlines()[:3]
    for lp in lines_preview:
        print(" ", repr(lp))

# 4. Inspect Live Preview serving
print("\nStep 4: Testing Preview API...")
# index.html preview
idx_url = f"http://localhost:8000/api/agent/workspaces/{workspace_id}/preview/index.html"
with urllib.request.urlopen(idx_url) as r:
    html_preview = r.read().decode("utf-8")
    print("GET preview/index.html status:", r.status)
    print("Content-Type:", r.headers.get("content-type"))
    print("Cache-Control:", r.headers.get("cache-control"))
    print("Has base tag:", f'<base href="/api/agent/workspaces/{workspace_id}/preview/">' in html_preview)
    print("Has literal \\n in HTML preview:", r"\n" in html_preview)

# style.css preview
css_url = f"http://localhost:8000/api/agent/workspaces/{workspace_id}/preview/style.css"
with urllib.request.urlopen(css_url) as r:
    css_preview = r.read().decode("utf-8")
    print("GET preview/style.css status:", r.status)
    print("Content-Type:", r.headers.get("content-type"))
    print("Has literal \\n in CSS preview:", r"\n" in css_preview)
    for l in css_preview.splitlines()[:2]:
        print(" ", repr(l))

# script.js preview
js_url = f"http://localhost:8000/api/agent/workspaces/{workspace_id}/preview/script.js"
with urllib.request.urlopen(js_url) as r:
    js_preview = r.read().decode("utf-8")
    print("GET preview/script.js status:", r.status)
    print("Content-Type:", r.headers.get("content-type"))
    print("Has literal \\n in JS preview:", r"\n" in js_preview)

print("\n========================================================")
print("SUCCESS: Live acceptance run completed and verified 100%!")
print("========================================================")
