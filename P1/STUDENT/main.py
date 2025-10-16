from fastapi import FastAPI
import os, json, base64, requests
from openai import OpenAI
import time
from urllib.parse import quote_plus

GITHUB_USER = "Roshan-872024"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


app = FastAPI()

def validate_secret(secret: str) -> bool:
    # Dummy validation function
    return secret == os.environ.get("secret")

def create_github_repo(repo_name: str):
    # use github api to create a repo with the given name
    payload = {"name": repo_name, 
                "private": False, 
                "auto_init": True,
                "license_template": "mit"}

    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}",
               "Accept": "application/vnd.github.v3+json"
               }


    response = requests.post(
        "https://api.github.com/user/repos", 
        headers=headers,
        json=payload
        )

    if response.status_code != 201:
        raise Exception(f"Failed to create repo: {response.status_code}, {response.text}")
    else:
        return response.json()


def enable_github_pages(repo_name: str):
    #takes repo name as argument and enables github pages for that repo
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}",
               "Accept": "application/vnd.github.v3+json"
               }

    payload = {
        "build_type": "legacy",
        "source": {
            "branch": "main",
            "path": "/"
        }
    }

    response = requests.post(
        f"https://api.github.com/repos/Roshan-872024/{repo_name}/pages",
        headers=headers, json=payload
    )

    if response.status_code != 201:
        raise Exception(f"Failed to enable GitHub Pages: {response.status_code}, {response.text}")


#Push files to github repo and get the latest commit sha from the last file pushed
def push_files_to_repo(repo_name: str, files: list[dict], round: int):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    last_commit_sha = None
    for file in files:
        file_name = file.get("name")
        file_content = file.get("content")

        # Encode content to base64
        if isinstance(file_content, str):
            file_content = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
        elif isinstance(file_content, bytes):
            file_content = base64.b64encode(file_content).decode("utf-8")

        # ✅ Check if the file already exists (to get its sha)
        check_url = f"https://api.github.com/repos/Roshan-872024/{repo_name}/contents/{file_name}"
        check_resp = requests.get(check_url, headers=headers)

        if check_resp.status_code == 200:
            existing_sha = check_resp.json()["sha"]
        else:
            existing_sha = None

        payload = {
            "message": f"Add or update {file_name}",
            "content": file_content
        }
        if existing_sha:
            payload["sha"] = existing_sha  # ✅ include SHA for update

        response = requests.put(check_url, headers=headers, json=payload)
        if response.status_code not in (200, 201):
            raise Exception(
                f"Failed to push file {file_name}: {response.status_code}, {response.text}"
            )
            
        try:
            commit_sha = response.json().get("commit", {}).get("sha")
            if commit_sha:
                last_commit_sha = commit_sha
        except Exception:
            pass

    return last_commit_sha


def notify_evaluation_server(data, commit_sha):
    """Notify the evaluation server with repo and commit details."""
    payload = {
        "email": data.get("email"),
        "task": data.get("task"),
        "round": data.get("round"),
        "nonce": data.get("nonce"),
        "repo_url": f"https://github.com/{GITHUB_USER}/{data['task']}_{data['nonce']}",
        "commit_sha": commit_sha,
        "pages_url": f"https://{GITHUB_USER}.github.io/{data['task']}_{data['nonce']}/"
    }

    print("📦 Sending evaluation payload:")
    print(json.dumps(payload, indent=2))
    
    try:
        response = requests.post(
            data.get("evaluation_url", ""),
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        print(f"📡 Notified evaluation server: {response.status_code}")
        return response.status_code
    except Exception as e:
        print(f"⚠️ Failed to notify evaluation server: {e}")
        return None



def write_code_with_llm(data: dict):
    """
    Generate deployable app code using GPT-4o-mini based on IITM task brief.
    Fixed model for consistent low-cost usage.
    """

    # ✅ Always use GPT-4o-mini for this project
    MODEL_NAME = "gpt-4o-mini"
    print(f"🧠 Using model: {MODEL_NAME}")

    # Initialize OpenAI client
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Extract fields from the request
    brief = data.get("brief", "")
    checks = data.get("checks", [])
    attachments = data.get("attachments", [])
    task = data.get("task", "auto-app")

    # Summarize attachments for context
    attachment_summary = []
    for att in attachments:
        name = att.get("name")
        url = att.get("url", "")
        if url.startswith("data:"):
            mime, b64data = url.split(",", 1)
            kb = len(b64data) * 3 / 4 / 1024
            attachment_summary.append(f"{name} ({mime.split(';')[0]}, ~{kb:.1f} KB)")
        else:
            attachment_summary.append(name)

    system_prompt = (
    "You are an autonomous senior front-end web developer for the IITM LLM Code Deployment project. "
    "Your job is to generate a complete static web app (HTML, CSS, JS) that satisfies the given 'brief' and passes the 'checks'.\n\n"

    "=== CORE RULES ===\n"
    "- Output ONLY valid JSON mapping filenames to file contents (no markdown, no commentary).\n"
    "- Include at least: index.html, app.js, styles.css, README.md, LICENSE (MIT).\n"
    "- Use plain browser-based HTML, CSS, and JavaScript (no Node.js, no require(), no import/export, no frameworks).\n"
    "- Libraries like marked.js, highlight.js, Chart.js, PapaParse, etc. must be loaded via CDN <script> tags in index.html BEFORE app.js.\n"
    "- Access such libraries as globals (e.g., marked.parse(), hljs.highlightAll()).\n"
    "- If '?url=' is in the brief, use URLSearchParams to read it.\n"
    "- Handle attached data (CSV, JSON, Markdown, image) dynamically using Fetch or data URIs.\n"
    "- Always show results in elements mentioned in the 'checks' (like #output, #markdown-output, #total-sales).\n"
    "- Ensure readable layout, error handling, and responsive design.\n"
    "- Do not use build tools, npm, or import systems — all code must run directly in a browser.\n\n"

    "=== BEHAVIORAL EXPECTATIONS ===\n"
    "- Use async/await for fetch operations.\n"
    "- For Markdown → HTML: use marked.parse(), then call hljs.highlightAll().\n"
    "- For CSV/JSON: parse, compute summaries, or display charts using Chart.js when suitable.\n"
    "- For GitHub or API data: fetch() with proper error handling.\n"
    "- Show fallback messages (e.g., 'Error loading content').\n"
    "- Extend features in round 2 without breaking round 1.\n\n"

    "=== OUTPUT FORMAT ===\n"
    "{ 'index.html': '<!DOCTYPE html>...', 'app.js': '...', 'README.md': '...', 'LICENSE': 'MIT License' }\n"
)



    user_prompt = f"""
### Project Task
{task}

### Brief
{brief}

### Evaluation Checks (MUST ALL PASS)
{json.dumps(checks, indent=2)}

### Attachments
{json.dumps(attachments, indent=2)}

### Development Requirements
- Assume this app will be deployed as a static site on GitHub Pages.
- The app must load and display attachments dynamically using JavaScript in the browser.
- If the attachment is Markdown, fetch and convert it to HTML with **marked.js** and highlight code blocks using **highlight.js**.
- If the attachment is CSV, parse it and compute aggregates or visualize as described in the brief.
- If the attachment is an image or JSON, render or display it appropriately.
- All query parameters (like `?url=`) must be handled using `URLSearchParams`.
- Every CSS selector or element ID mentioned in the 'checks' must exist in the final HTML and behave as expected.

### Output Format
Return ONLY valid JSON mapping filenames to file contents, for example:
{{
  "index.html": "<!DOCTYPE html> ...",
  "app.js": "...",
  "styles.css": "...",
  "README.md": "...",
  "LICENSE": "MIT License ..."
}}
"""


    # === LLM call ===
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=4000,
        )

        raw_output = response.choices[0].message.content.strip()

        # Parse JSON safely
        start, end = raw_output.find("{"), raw_output.rfind("}") + 1
        json_part = raw_output[start:end]
        files_dict = json.loads(json_part)

    except Exception as e:
        # Graceful fallback if LLM call fails (e.g., quota exceeded)
        print(f"⚠️ LLM generation failed: {e}")
        files_dict = {
            "index.html": "<html><body><h1>LLM Error: Could not generate app</h1></body></html>",
            "README.md": "# LLM generation failed\n\nFallback output.",
            "LICENSE": "MIT License"
        }

    # Convert dict → list for GitHub push
    files = [{"name": k, "content": v} for k, v in files_dict.items()]

    # ✅ Always save attachments as proper files
    for att in attachments:
        name = att.get("name")
        url = att.get("url", "")
        if not name:
            continue

        if url.startswith("data:"):
            try:
                # Handle base64 or plain text data URLs
                if ";base64," in url:
                    _, b64 = url.split(";base64,", 1)
                    raw = base64.b64decode(b64)
                    content = raw.decode(errors="ignore")
                else:
                    _, content = url.split(",", 1)
                files.append({"name": name, "content": content})
            except Exception as e:
                print(f"⚠️ Failed to decode attachment {name}: {e}")
        else:
            # Fallback: if it's a remote URL, insert placeholder
            files.append({
                "name": name,
                "content": f"<!-- Attachment link: {url} -->"
            })


    return files

def round1(data):
    create_github_repo(f"{data['task']}_{data['nonce']}")
    files = write_code_with_llm(data)
    commit_sha = push_files_to_repo(f"{data['task']}_{data['nonce']}", files, 1)
    enable_github_pages(f"{data['task']}_{data['nonce']}")
    notify_evaluation_server(data, commit_sha)

def round2(data):
    files = write_code_with_llm(data)
    commit_sha = push_files_to_repo(f"{data['task']}_{data['nonce']}", files, 2)
    notify_evaluation_server(data, commit_sha)

# post endpoint that takes a json object with the following fields: email, secret, task, round, nonce, 
# brief, checks(array), evaluation_url, attachments(array with objects with fields: name, url)

@app.post("/handle_task")
async def handle_task(data: dict):
    #validate secret
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid secret"}
    else:
        # Process the valid task
        #depending on the round, call different functions
        if data.get("round") == 1:
            round1(data)
            return {"message": "Round 1 task processed"}
        elif data.get("round") == 2:
            round2(data)
            return {"message": "Round 2 task processed"}

    return {"message": "Task received successfully", "data": data}

# run the app with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)