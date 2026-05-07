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
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ issue_title }}</title>
</head>
<body style="margin:0;padding:0;background:#f4f1ec;font-family:Georgia,serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f1ec;">
    <tr><td align="center" style="padding:40px 16px 0;">

      <!-- HEADER -->
      <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;">
        <tr>
          <td style="background:#111;padding:28px 40px;">
            <p style="margin:0;font-family:Arial,sans-serif;font-size:10px;letter-spacing:4px;
                      text-transform:uppercase;color:#888;">AI &amp; MARKETING INTELLIGENCE</p>
            <h1 style="margin:8px 0 0;font-family:Georgia,serif;font-size:22px;
                       font-weight:normal;color:#fff;line-height:1.3;">{{ issue_title }}</h1>
            <p style="margin:10px 0 0;font-family:Arial,sans-serif;font-size:11px;
                      color:#666;letter-spacing:1px;">{{ issue_date }}</p>
          </td>
        </tr>
      </table>

      <!-- BLOCKS -->
      {% for block in blocks %}
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;margin-top:3px;">
        <tr>
          <td style="background:#fff;padding:0;">

            {% if block.image_url %}
            <img src="{{ block.image_url }}" alt="{{ block.name }}" width="600"
                 style="display:block;width:100%;max-width:600px;height:auto;border:0;">
            {% endif %}

            <div style="padding:28px 36px 32px;">
              <p style="margin:0 0 6px;font-family:Arial,sans-serif;font-size:9px;
                        letter-spacing:3px;text-transform:uppercase;color:#aaa;">{{ block.label }}</p>
              <h2 style="margin:0 0 18px;font-family:Georgia,serif;font-size:19px;
                         font-weight:normal;color:#111;line-height:1.4;">{{ block.name }}</h2>
              <div style="font-family:Georgia,serif;font-size:14px;line-height:1.9;color:#333;">
                {{ block.content_html | safe }}
              </div>
            </div>

          </td>
        </tr>
      </table>
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;margin-top:2px;">
        <tr><td style="height:2px;background:#f4f1ec;font-size:0;">&nbsp;</td></tr>
      </table>
      {% endfor %}

      <!-- FOOTER -->
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;margin-top:3px;">
        <tr>
          <td style="background:#111;padding:28px 40px;text-align:center;">
            <p style="margin:0;font-family:Arial,sans-serif;font-size:11px;
                      color:#555;line-height:1.7;">
              Recibes esto porque estás suscrito.<br>
              © {{ year }} — AI-Powered Luxury Marketing
            </p>
          </td>
        </tr>
      </table>

      <p style="font-family:Arial,sans-serif;font-size:10px;color:#bbb;
                text-align:center;padding:20px 0 40px;">
        Para darte de baja responde con BAJA.
      </p>

    </td></tr>
  </table>
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
        issue_title=issue_title,
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
