import asyncio
import os
import secrets
import textwrap
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

load_dotenv()

from notion_reader import (
    extract_image_prompt,
    extract_image_settings,
    extract_main_content,
    get_issue_blocks,
    get_new_issues,
    mark_issue_processed,
)
from image_generator import generate_image, base64_to_data_url
from email_sender import send_preview_email, send_newsletter

processed_issues: set[str] = set()
pending_approvals: dict[str, dict] = {}

BLOCK_ORDER = [
    "01 — AI News Roundup",
    "02 — Image Gen Spotlight",
    "03 — Prompt of the Week",
    "04 — Fun Fact",
    "05 — Marketing Psychology",
    "06 — Tool Review",
]

BLOCK_LABELS = {
    "01 — AI News Roundup": "AI News",
    "02 — Image Gen Spotlight": "Image Generation",
    "03 — Prompt of the Week": "Prompt of the Week",
    "04 — Fun Fact": "Fun Fact",
    "05 — Marketing Psychology": "Marketing Psychology",
    "06 — Tool Review": "Tool Review",
}


async def process_issue(issue: dict):
    issue_id = issue["id"]
    issue_title = issue["title"]
    print(f"\nProcessing: {issue_title}")

    raw_blocks = get_issue_blocks(issue_id)
    prepared_blocks = []
    sendable_blocks = []

    for block_key in BLOCK_ORDER:
        if block_key not in raw_blocks:
            continue

        block_data = raw_blocks[block_key]
        content = block_data["content"]
        main_content = extract_main_content(content)
        prompt = extract_image_prompt(content)
        settings = extract_image_settings(content)

        flag = "WEAK" if "WEAK" in content.upper() else "GOOD"

        image_b64 = None
        if prompt:
            print(f"  Generating image for {block_key}...")
            image_b64 = await generate_image(
                prompt=prompt,
                size=settings["size"],
                quality=settings["quality"],
                style=settings["style"],
            )

        summary = next((l.strip() for l in main_content.split("\n") if l.strip()), "—")
        summary = textwrap.shorten(summary, width=100, placeholder="...")

        prepared_blocks.append({
            "name": BLOCK_LABELS.get(block_key, block_key),
            "summary": summary,
            "flag": flag,
        })

        sendable_blocks.append({
            "name": BLOCK_LABELS.get(block_key, block_key),
            "label": BLOCK_LABELS.get(block_key, block_key).upper(),
            "content_html": main_content.replace("\n", "<br>"),
            "image_b64": image_b64 or "",
            "flag": flag,
        })

    if not sendable_blocks:
        print(f"  No content blocks found for '{issue_title}' — will retry next poll.")
        return

    token = secrets.token_urlsafe(32)
    pending_approvals[token] = {
        "title": issue_title,
        "blocks": sendable_blocks,
        "date": datetime.now().strftime("%B %d, %Y"),
    }

    send_preview_email(
        issue_title=issue_title,
        blocks=prepared_blocks,
        token=token,
    )

    mark_issue_processed(issue_id)
    processed_issues.add(issue_id)
    print(f"Done: {issue_title} — approval token: {token}")


async def poll_notion():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Polling Notion...")
    try:
        new_issues = get_new_issues(processed_issues)
        print(f"  Found {len(new_issues)} issue(s) to process.")
        for issue in new_issues:
            await process_issue(issue)
    except Exception as e:
        import traceback
        print(f"Poll error: {e}\n{traceback.format_exc()}")


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(poll_notion, "interval", minutes=10, id="notion_poll")
    scheduler.start()
    asyncio.create_task(poll_notion())
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


APPROVAL_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Review Newsletter — {{ title }}</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 24px; }
    .container { max-width: 680px; margin: 0 auto; background: white;
                 padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
    h1 { font-size: 22px; margin: 0 0 6px; }
    .subtitle { color: #888; font-size: 14px; margin-bottom: 32px; }
    .block { display: flex; align-items: flex-start; gap: 14px;
             padding: 16px 0; border-bottom: 1px solid #eee; }
    .block:last-of-type { border-bottom: none; }
    input[type=checkbox] { width: 20px; height: 20px; margin-top: 3px; cursor: pointer; flex-shrink: 0; }
    .block-info { flex: 1; }
    .block-name { font-weight: bold; font-size: 15px; }
    .block-summary { color: #555; font-size: 13px; margin-top: 4px; }
    .weak { color: #c0392b; font-size: 12px; margin-top: 2px; }
    .send-btn { display: block; width: 100%; margin-top: 32px; padding: 16px;
                background: #111; color: white; border: none; border-radius: 4px;
                font-size: 17px; cursor: pointer; }
    .send-btn:hover { background: #333; }
    .note { font-size: 12px; color: #aaa; text-align: center; margin-top: 12px; }
  </style>
</head>
<body>
<div class="container">
  <h1>Review Newsletter</h1>
  <p class="subtitle">{{ title }} — Select the blocks to include and click Send.</p>

  <form method="POST" action="/send/{{ token }}">
    {% for block in blocks %}
    <div class="block">
      <input type="checkbox" name="blocks" value="{{ loop.index0 }}" checked>
      <div class="block-info">
        <div class="block-name">{{ block.name }}</div>
        <div class="block-summary">{{ block.summary }}</div>
        {% if block.flag == "WEAK" %}<div class="weak">⚠️ Flagged as weak by Claude</div>{% endif %}
      </div>
    </div>
    {% endfor %}

    <button type="submit" class="send-btn">Send Newsletter to Subscribers</button>
    <p class="note">This action cannot be undone. Subscribers will receive the selected blocks immediately.</p>
  </form>
</div>
</body>
</html>
"""

SENT_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Sent!</title>
<style>
  body { font-family: Arial, sans-serif; display: flex; align-items: center;
         justify-content: center; height: 100vh; background: #f5f5f5; margin: 0; }
  .box { text-align: center; background: white; padding: 48px; border-radius: 8px; }
  h1 { font-size: 28px; margin: 0 0 12px; }
  p { color: #666; }
</style>
</head>
<body>
<div class="box">
  <h1>✓ Newsletter Sent</h1>
  <p>{{ count }} block(s) delivered to {{ subscribers }} subscriber(s).</p>
</div>
</body>
</html>
"""


@app.get("/approve/{token}", response_class=HTMLResponse)
async def approval_page(token: str):
    if token not in pending_approvals:
        raise HTTPException(status_code=404, detail="Invalid or expired approval link.")

    data = pending_approvals[token]
    from jinja2 import Template

    blocks_with_summary = []
    for b in data["blocks"]:
        summary = b["content_html"].replace("<br>", " ")[:120].strip() + "..."
        blocks_with_summary.append({**b, "summary": summary})

    html = Template(APPROVAL_PAGE).render(
        title=data["title"],
        token=token,
        blocks=blocks_with_summary,
    )
    return HTMLResponse(content=html)


@app.post("/send/{token}")
async def send_approved_form(token: str, request: Request):
    from jinja2 import Template

    if token not in pending_approvals:
        raise HTTPException(status_code=404, detail="Invalid or expired approval link.")

    form = await request.form()
    selected_indices = [int(i) for i in form.getlist("blocks")]

    data = pending_approvals[token]
    selected_blocks = [data["blocks"][i] for i in selected_indices if i < len(data["blocks"])]

    if not selected_blocks:
        raise HTTPException(status_code=400, detail="No blocks selected.")

    send_newsletter(
        issue_title=data["title"],
        blocks=selected_blocks,
        issue_date=data["date"],
        year=str(datetime.now().year),
    )

    del pending_approvals[token]

    html = Template(SENT_PAGE).render(
        count=len(selected_blocks),
        subscribers=len([s for s in os.environ.get("SUBSCRIBERS", "").split(",") if s.strip()]),
    )
    return HTMLResponse(content=html)


@app.get("/")
async def health():
    return {
        "status": "running",
        "pending_approvals": len(pending_approvals),
        "processed_issues": len(processed_issues),
    }
