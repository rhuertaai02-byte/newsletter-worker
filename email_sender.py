import os
import resend
from jinja2 import Template

resend.api_key = os.environ["RESEND_API_KEY"]

RESEND_FROM = os.environ.get("RESEND_FROM", "onboarding@resend.dev")
APPROVAL_EMAIL = os.environ["APPROVAL_EMAIL"]
SUBSCRIBERS = [s.strip() for s in os.environ.get("SUBSCRIBERS", "").split(",") if s.strip()]
RAILWAY_PUBLIC_URL = os.environ["RAILWAY_PUBLIC_URL"].rstrip("/")

PREVIEW_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: Georgia, serif; background: #f5f5f5; margin: 0; padding: 20px; }
    .container { max-width: 700px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; }
    h1 { font-size: 22px; color: #111; border-bottom: 2px solid #111; padding-bottom: 12px; }
    .cta { display: block; text-align: center; margin: 32px 0; }
    .btn { background: #111; color: white; padding: 14px 32px; text-decoration: none;
           border-radius: 4px; font-size: 16px; font-family: Arial, sans-serif; }
    .summary { background: #f9f9f9; border-left: 3px solid #111; padding: 16px; margin: 20px 0; }
    .block-item { margin: 8px 0; font-size: 15px; }
    .flag { color: #c0392b; font-size: 13px; }
    p { color: #444; line-height: 1.6; }
  </style>
</head>
<body>
  <div class="container">
    <h1>📬 Newsletter Batch Ready — {{ title }}</h1>
    <p>The routine ran and generated all 6 blocks. Images have been generated and embedded.</p>

    <div class="summary">
      {% for block in blocks %}
      <div class="block-item">
        <strong>{{ loop.index }}. {{ block.name }}</strong> — {{ block.summary }}
        {% if block.flag == "WEAK" %}<span class="flag"> ⚠️ Flagged as weak</span>{% endif %}
      </div>
      {% endfor %}
    </div>

    <p>Click below to review all blocks, select which ones to include, and send the newsletter.</p>

    <div class="cta">
      <a href="{{ approval_url }}" class="btn">Review &amp; Approve →</a>
    </div>

    <p style="font-size:13px;color:#999;">This preview is only visible to you. Nothing has been sent to subscribers yet.</p>
  </div>
</body>
</html>
"""

NEWSLETTER_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { font-family: Georgia, serif; background: #fff; margin: 0; padding: 0; color: #111; }
    .wrapper { max-width: 640px; margin: 0 auto; padding: 40px 20px; }
    .header { border-bottom: 2px solid #111; padding-bottom: 20px; margin-bottom: 32px; }
    .header h1 { font-size: 13px; letter-spacing: 3px; text-transform: uppercase; margin: 0 0 6px; color: #888; }
    .header h2 { font-size: 26px; margin: 0; }
    .block { margin-bottom: 48px; padding-bottom: 48px; border-bottom: 1px solid #e5e5e5; }
    .block:last-child { border-bottom: none; }
    .block-label { font-size: 11px; letter-spacing: 2px; text-transform: uppercase; color: #888; margin-bottom: 8px; }
    .block h3 { font-size: 20px; margin: 0 0 16px; }
    .block p { font-size: 15px; line-height: 1.8; color: #333; }
    .block img { width: 100%; border-radius: 4px; margin: 20px 0; }
    .footer { margin-top: 48px; padding-top: 20px; border-top: 1px solid #e5e5e5;
              font-size: 12px; color: #999; text-align: center; line-height: 1.6; }
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>Newsletter</h1>
      <h2>{{ issue_date }}</h2>
    </div>

    {% for block in blocks %}
    <div class="block">
      <div class="block-label">{{ block.label }}</div>
      <h3>{{ block.name }}</h3>
      {% if block.image_b64 %}
      <img src="data:image/png;base64,{{ block.image_b64 }}" alt="{{ block.name }}">
      {% endif %}
      <div>{{ block.content_html | safe }}</div>
    </div>
    {% endfor %}

    <div class="footer">
      <p>You're receiving this because you subscribed to our newsletter.<br>
      © {{ year }} — AI-Powered Luxury Marketing</p>
    </div>
  </div>
</body>
</html>
"""


def send_preview_email(issue_title: str, blocks: list[dict], token: str):
    approval_url = f"{RAILWAY_PUBLIC_URL}/approve/{token}"
    html = Template(PREVIEW_TEMPLATE).render(
        title=issue_title,
        blocks=blocks,
        approval_url=approval_url,
    )
    resend.Emails.send({
        "from": RESEND_FROM,
        "to": [APPROVAL_EMAIL],
        "subject": f"Newsletter Ready for Review — {issue_title}",
        "html": html,
    })
    print(f"Preview email sent to {APPROVAL_EMAIL}")


def send_newsletter(issue_title: str, blocks: list[dict], issue_date: str, year: str):
    import datetime
    html = Template(NEWSLETTER_TEMPLATE).render(
        issue_date=issue_date,
        blocks=blocks,
        year=datetime.datetime.now().year,
    )
    resend.Emails.send({
        "from": RESEND_FROM,
        "to": SUBSCRIBERS,
        "subject": f"Newsletter — {issue_title}",
        "html": html,
    })
    print(f"Newsletter sent to {len(SUBSCRIBERS)} subscriber(s)")
