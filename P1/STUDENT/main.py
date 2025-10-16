from fastapi import FastAPI
import os, json, base64, requests, sys
from openai import OpenAI
import time

GITHUB_USER = "Roshan-872024"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

app = FastAPI()


def validate_secret(secret: str) -> bool:
    return secret == os.environ.get("secret")


def create_github_repo(repo_name: str):
    payload = {"name": repo_name, "private": False, "auto_init": True, "license_template": "mit"}
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    response = requests.post("https://api.github.com/user/repos", headers=headers, json=payload)

    if response.status_code != 201:
        if "name already exists" in response.text:
            print(f"⚠️ Repo {repo_name} already exists. Skipping creation.", flush=True)
            return None
        raise Exception(f"Failed to create repo: {response.status_code}, {response.text}")
    return response.json()


def enable_github_pages(repo_name: str):
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"build_type": "legacy", "source": {"branch": "main", "path": "/"}}

    response = requests.post(f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/pages", headers=headers, json=payload)
    if response.status_code not in (201, 409):
        raise Exception(f"Failed to enable GitHub Pages: {response.status_code}, {response.text}")
    print(f"✅ GitHub Pages enabled (or already active) for {repo_name}", flush=True)


def push_files_to_repo(repo_name: str, files: list[dict], round: int):
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    last_commit_sha = None

    for file in files:
        file_name, file_content = file.get("name"), file.get("content")

        # Encode file to base64
        if isinstance(file_content, str):
            file_content = base64.b64encode(file_content.encode()).decode()
        elif isinstance(file_content, bytes):
            file_content = base64.b64encode(file_content).decode()

        url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/contents/{file_name}"
        existing = requests.get(url, headers=headers)
        payload = {"message": f"Update {file_name}", "content": file_content}

        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]

        res = requests.put(url, headers=headers, json=payload)
        if res.status_code not in (200, 201):
            raise Exception(f"Failed to push {file_name}: {res.status_code}, {res.text}")

        last_commit_sha = res.json().get("commit", {}).get("sha")

    print(f"📤 All files pushed successfully to {repo_name}.", flush=True)
    return last_commit_sha


def notify_evaluation_server(data, commit_sha):
    payload = {
        "email": data.get("email"),
        "task": data.get("task"),
        "round": data.get("round"),
        "nonce": data.get("nonce"),
        "repo_url": f"https://github.com/{GITHUB_USER}/{data['task']}_{data['nonce']}",
        "commit_sha": commit_sha,
        "pages_url": f"https://{GITHUB_USER}.github.io/{data['task']}_{data['nonce']}/"
    }

    print(f"📦 Sending evaluation payload:\n{json.dumps(payload, indent=2)}", flush=True)

    try:
        resp = requests.post(data.get("evaluation_url", ""), headers={"Content-Type": "application/json"}, json=payload, timeout=10)
        print(f"📡 Notified evaluation server: {resp.status_code}", flush=True)
        return payload
    except Exception as e:
        print(f"⚠️ Failed to notify evaluation server: {e}", flush=True)
        return payload


def write_code_with_llm(data: dict):
    MODEL_NAME = "gpt-4o-mini"
    print(f"🧠 Using model: {MODEL_NAME}", flush=True)

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    brief, checks, attachments, task = data.get("brief", ""), data.get("checks", []), data.get("attachments", []), data.get("task", "auto-app")

    system_prompt = (
        "You are an autonomous senior front-end web developer for the IITM LLM Code Deployment project. "
        "Generate a complete static web app that passes all checks.\n\n"
        "Output ONLY valid JSON mapping filenames to file contents.\n"
    )

    user_prompt = f"""
### Task
{task}
### Brief
{brief}
### Checks
{json.dumps(checks, indent=2)}
### Attachments
{json.dumps(attachments, indent=2)}
"""

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.4,
            max_tokens=4000,
        )
        raw = resp.choices[0].message.content.strip()
        files = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception as e:
        print(f"⚠️ LLM generation failed: {e}", flush=True)
        files = {"index.html": "<h1>LLM Error</h1>", "README.md": "Error", "LICENSE": "MIT"}

    return [{"name": k, "content": v} for k, v in files.items()]


def round1(data):
    repo_name = f"{data['task']}_{data['nonce']}"
    print(f"🚀 Starting Round 1 for repo: {repo_name}", flush=True)

    try:
        create_github_repo(repo_name)
    except Exception as e:
        print(f"⚠️ {e}", flush=True)

    files = write_code_with_llm(data)
    commit_sha = push_files_to_repo(repo_name, files, 1)
    enable_github_pages(repo_name)
    payload = notify_evaluation_server(data, commit_sha)

    # ✅ Return full info for send_task.py
    return payload


def round2(data):
    repo_name = f"{data['task']}_{data['nonce']}"
    print(f"🔁 Starting Round 2 for repo: {repo_name}", flush=True)

    files = write_code_with_llm(data)
    commit_sha = push_files_to_repo(repo_name, files, 2)
    enable_github_pages(repo_name)
    payload = notify_evaluation_server(data, commit_sha)

    return payload


@app.get("/")
def root():
    return {"message": "LLM deployment API is running. Use POST /handle_task"}


@app.post("/handle_task")
async def handle_task(data: dict):
    if not validate_secret(data.get("secret", "")):
        return {"error": "Invalid secret"}

    try:
        if data.get("round") == 1:
            result = round1(data)
        elif data.get("round") == 2:
            result = round2(data)
        else:
            return {"error": "Invalid round"}

        return {"message": "Task processed successfully", **result}
    except Exception as e:
        print(f"❌ Error in handle_task: {e}", flush=True)
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
