import requests

def send_task_round2():
    payload = {
        "email": "student@example.com",
        "secret": "angel_on_earth_2027",
        "task": "markdown-to-html-001",
        "round": 2,
        "nonce": "xyz123",
        "brief": (
            "Upgrade the previous markdown-to-HTML converter to be interactive. "
            "Keep support for attached input.md but also allow users to type Markdown "
            "in a textarea with id='markdown-input'. Convert and preview live using "
            "marked.parse() and hljs.highlightAll(). Include #status to show messages "
            "and a Clear button. "
            "Ensure that marked.js and highlight.js are loaded via CDN BEFORE app.js. "
            "Use Bootstrap for layout and responsiveness. "
            "Display both the rendered HTML and syntax-highlighted code preview dynamically."
        ),
        "checks": [
            "document.querySelector('#markdown-input') !== null",
            "document.querySelector('#status') !== null",
            "document.querySelector('#markdown-output').innerHTML.length > 0"
        ],
        "evaluation_url": "http://example.com/notify",
        "attachments": []
    }

    print("🚀 Sending Round 2 Task to FastAPI...")
    response = requests.post("http://localhost:8000/handle_task", json=payload)

    try:
        print("✅ Response from FastAPI:", response.json())
    except Exception:
        print("⚠️ Non-JSON response received:", response.text)


if __name__ == "__main__":
    send_task_round2()
