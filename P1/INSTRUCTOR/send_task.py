import requests
import json

def send_task():
    markdown_content = """# Sample Markdown
This is a **bold** statement.

```python
print("Hello from code block!")
```

"""

    # The payload matches the IITM project JSON structure
    payload = {
        "email": "student@example.com",
        "secret": "angel_on_earth_2027",
        "task": "markdown-to-html-001",
        "round": 1,
        "nonce": "xyz123",
        "brief": (
            "Publish a static page that converts input.md from attachments to HTML "
            "with marked.js, renders it inside #markdown-output, "
            "and loads highlight.js for code blocks."
        ),
        "checks": [
            "document.querySelector('script[src*=\"marked\"]') !== null",
            "document.querySelector('script[src*=\"highlight.js\"]') !== null",
            "document.querySelector('#markdown-output').innerHTML.includes('<h') === true"
        ],
        "evaluation_url": "http://example.com/notify",
        "attachments": [
            {
                "name": "input.md",
                # ✅ No base64 here — just send as plain text
                "url": f"data:text/markdown,{markdown_content}"
            }
        ]
    }

    # ✅ Replace localhost with your Hugging Face API endpoint
    SPACE_URL = "https://roshan0510-22f1000684-llm-project.hf.space/handle_task"

    # Send JSON POST to Hugging Face API
    response = requests.post(SPACE_URL, json=payload)
    # Try parsing the JSON output
    try:
        data = response.json()
        print("\n✅ Full JSON Response from Hugging Face:\n")
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"⚠️ Non-JSON response received: {response.text}")



if __name__ == "__main__":
    send_task()


