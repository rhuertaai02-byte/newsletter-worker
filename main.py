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
    find_root_page,
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
        root_id = find_root_page(os.environ.get("NOTION_ROOT_PAGE", "Newsletter"))
        new_issues = get_new_issues(root_id, processed_issues)
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
  <title>Review — {{ title }}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Georgia, serif; background: #f0ede8; min-height: 100vh; padding: 40px 20px; }
    .header { max-width: 740px; margin: 0 auto 36px; }
    .label { font-size: 11px; letter-spacing: 3px; text-transform: uppercase; color: #999; font-family: Arial, sans-serif; margin-bottom: 10px; }
    .header h2 { font-size: 28px; font-weight: normal; color: #111; border-bottom: 1px solid #ccc; padding-bottom: 16px; }
    .card { max-width: 740px; margin: 0 auto 20px; background: white; border-radius: 4px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.07); }
    .card-header { display: flex; align-items: center; gap: 16px; padding: 18px 24px; }
    .card-header input[type=checkbox] { width: 20px; height: 20px; cursor: pointer; accent-color: #111; flex-shrink: 0; }
    .card-meta { flex: 1; }
    .card-num { font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: #bbb; font-family: Arial; }
    .card-name { font-size: 18px; color: #111; margin-top: 2px; }
    .weak { background: #fff0f0; color: #c0392b; font-size: 11px; font-family: Arial; padding: 4px 12px; border-radius: 20px; white-space: nowrap; }
    .card-image { width: 100%; max-height: 360px; object-fit: cover; display: block; border-top: 1px solid #f0ede8; }
    .no-image { padding: 12px 24px 0; font-size: 12px; color: #bbb; font-family: Arial; font-style: italic; }
    .card-body { padding: 16px 24px 24px; font-size: 14px; line-height: 1.75; color: #444; max-height: 200px; overflow: hidden; position: relative; }
    .card-body::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 60px; background: linear-gradient(transparent, white); }
    .footer { max-width: 740px; margin: 32px auto 60px; }
    .send-btn { display: block; width: 100%; padding: 18px; background: #111; color: white; border: none; font-size: 13px; letter-spacing: 2px; text-transform: uppercase; font-family: Arial; cursor: pointer; border-radius: 4px; }
    .send-btn:hover { background: #333; }
    .note { text-align: center; font-size: 12px; color: #aaa; margin-top: 12px; font-family: Arial; }
  </style>
</head>
<body>
  <div class="header">
    <p class="label">DODO Newsletter — Review</p>
    <h2>{{ title }}</h2>
  </div>

  <form method="POST" action="/send/{{ token }}">
    {% for block in blocks %}
    <div class="card">
      <div class="card-header">
        <input type="checkbox" name="blocks" value="{{ loop.index0 }}" checked>
        <div class="card-meta">
          <div class="card-num">Block {{ loop.index }}</div>
          <div class="card-name">{{ block.name }}</div>
        </div>
        {% if block.flag == "WEAK" %}<span class="weak">⚠ Flagged weak</span>{% endif %}
      </div>
      {% if block.image_b64 %}
        <img class="card-image" src="data:image/png;base64,{{ block.image_b64 }}" alt="{{ block.name }}">
      {% else %}
        <p class="no-image">No image generated</p>
      {% endif %}
      <div class="card-body">{{ block.content_html | safe }}</div>
    </div>
    {% endfor %}

    <div class="footer">
      <button type="submit" class="send-btn">Send Newsletter to Subscribers</button>
      <p class="note">This cannot be undone. Subscribers will receive the selected blocks immediately.</p>
    </div>
  </form>
</body>
</html>
"""

SENT_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Sent!</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: Georgia, serif; display: flex; align-items: center;
         justify-content: center; height: 100vh; background: #f0ede8; }
  .box { text-align: center; background: white; padding: 60px 48px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,.07); }
  .label { font-size: 11px; letter-spacing: 3px; text-transform: uppercase; color: #999; font-family: Arial; margin-bottom: 16px; }
  h1 { font-size: 28px; font-weight: normal; color: #111; margin-bottom: 12px; }
  p { color: #888; font-family: Arial; font-size: 14px; }
</style>
</head>
<body>
<div class="box">
  <p class="label">DODO Newsletter</p>
  <h1>Newsletter Sent</h1>
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

    html = Template(APPROVAL_PAGE).render(
        title=data["title"],
        token=token,
        blocks=data["blocks"],
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
