import os
from notion_client import Client

notion = Client(auth=os.environ["NOTION_TOKEN"])


def find_root_page(name: str) -> str:
    results = notion.search(query=name, filter={"property": "object", "value": "page"}).get("results", [])
    for page in results:
        title_parts = page.get("properties", {}).get("title", {}).get("title", [])
        title = "".join(t["plain_text"] for t in title_parts)
        if title.strip() == name:
            return page["id"]
    raise ValueError(f"Notion page '{name}' not found.")


def is_issue_processed_in_notion(issue_page_id: str) -> bool:
    children = notion.blocks.children.list(block_id=issue_page_id).get("results", [])
    for block in children:
        if block["type"] != "child_page":
            continue
        if "Summary" not in block["child_page"]["title"]:
            continue
        summary_blocks = notion.blocks.children.list(block_id=block["id"]).get("results", [])
        for sb in summary_blocks:
            btype = sb["type"]
            rich = sb.get(btype, {}).get("rich_text", [])
            text = "".join(r["plain_text"] for r in rich)
            if "IMAGES GENERATED" in text or "PENDING APPROVAL" in text:
                return True
    return False


def get_new_issues(root_page_id: str, already_processed: set) -> list[dict]:
    children = notion.blocks.children.list(block_id=root_page_id).get("results", [])
    print(f"  Root page has {len(children)} total blocks")
    issues = []
    for block in children:
        if block["type"] != "child_page":
            continue
        page_id = block["id"]
        title = block["child_page"]["title"]
        print(f"  Found child_page: {repr(title)} id={page_id}")
        if page_id in already_processed:
            print(f"    -> skipping (already processed)")
            continue
        if not title.startswith("Newsletter —"):
            print(f"    -> skipping (title doesn't match)")
            continue
        if is_issue_processed_in_notion(page_id):
            print(f"    -> skipping (marked done in Notion)")
            already_processed.add(page_id)
            continue
        print(f"    -> QUEUING for processing")
        issues.append({"id": page_id, "title": title})
    return issues


def get_issue_blocks(issue_page_id: str) -> dict:
    children = notion.blocks.children.list(block_id=issue_page_id).get("results", [])
    print(f"  get_issue_blocks: {len(children)} blocks inside issue {issue_page_id}")
    for block in children:
        print(f"    type={block['type']} | title={repr(block.get('child_page', {}).get('title', 'N/A'))}")
    blocks = {}
    for block in children:
        if block["type"] != "child_page":
            continue
        title = block["child_page"]["title"]
        page_id = block["id"]
        content = extract_page_text(page_id)
        content_html = extract_page_html(page_id)
        blocks[title] = {"id": page_id, "content": content, "html": content_html}
    return blocks


def _rich_text_to_html(rich_text: list) -> str:
    html = ""
    for r in rich_text:
        text = r["plain_text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        ann = r.get("annotations", {})
        href = r.get("href")
        if ann.get("code"):
            text = f"<code>{text}</code>"
        if ann.get("bold"):
            text = f"<strong>{text}</strong>"
        if ann.get("italic"):
            text = f"<em>{text}</em>"
        if href:
            text = f'<a href="{href}" style="color:#111;">{text}</a>'
        html += text
    return html


def extract_page_html(page_id: str) -> str:
    all_blocks = notion.blocks.children.list(block_id=page_id).get("results", [])
    parts = []
    in_section = False
    pending_list: list = []
    pending_list_type: str | None = None

    def flush_list():
        if pending_list:
            items = "".join(f"<li>{item}</li>" for item in pending_list)
            parts.append(f"<{pending_list_type}>{items}</{pending_list_type}>")
            pending_list.clear()

    for block in all_blocks:
        btype = block["type"]
        rich = block.get(btype, {}).get("rich_text", [])
        plain = "".join(r["plain_text"] for r in rich).strip()
        html_content = _rich_text_to_html(rich)

        if plain == "Content":
            in_section = True
            continue
        if in_section and plain in ("Sources", "Image Prompt", "Image Settings", "Quality Flag"):
            break
        if not in_section:
            continue

        if btype == "bulleted_list_item":
            if pending_list_type != "ul":
                flush_list()
                pending_list_type = "ul"
            pending_list.append(html_content)
        elif btype == "numbered_list_item":
            if pending_list_type != "ol":
                flush_list()
                pending_list_type = "ol"
            pending_list.append(html_content)
        else:
            flush_list()
            pending_list_type = None
            if btype == "heading_1":
                parts.append(f"<h1>{html_content}</h1>")
            elif btype == "heading_2":
                parts.append(f"<h2>{html_content}</h2>")
            elif btype == "heading_3":
                parts.append(f"<h3>{html_content}</h3>")
            elif btype == "paragraph":
                if html_content:
                    parts.append(f"<p>{html_content}</p>")
            elif btype == "code":
                parts.append(f"<pre><code>{plain}</code></pre>")

    flush_list()
    return "\n".join(parts)


def extract_page_text(page_id: str) -> str:
    all_blocks = notion.blocks.children.list(block_id=page_id).get("results", [])
    lines = []
    for block in all_blocks:
        btype = block["type"]
        rich = block.get(btype, {}).get("rich_text", [])
        text = "".join(r["plain_text"] for r in rich)
        if text:
            lines.append(text)
    return "\n".join(lines)


def extract_image_prompt(content: str) -> str | None:
    lines = content.split("\n")
    in_prompt = False
    prompt_lines = []
    for line in lines:
        if "Image Prompt" in line:
            in_prompt = True
            continue
        if in_prompt:
            if line.startswith("Image Settings") or line.startswith("Quality Flag"):
                break
            if line.strip():
                prompt_lines.append(line.strip())
    return " ".join(prompt_lines) if prompt_lines else None


def extract_image_settings(content: str) -> dict:
    settings = {"size": "1024x1024", "quality": "medium"}
    for line in content.split("\n"):
        if "Size:" in line:
            for opt in ["1024x1024", "1024x1536", "1536x1024"]:
                if opt in line:
                    settings["size"] = opt
        if "Quality:" in line:
            if "high" in line.lower():
                settings["quality"] = "high"
            elif "low" in line.lower():
                settings["quality"] = "low"
    return settings


def extract_main_content(content: str) -> str:
    lines = content.split("\n")
    in_content = False
    result = []
    for line in lines:
        if line.strip() == "Content":
            in_content = True
            continue
        if in_content and line.startswith("Sources"):
            break
        if in_content:
            result.append(line)
    return "\n".join(result).strip() if result else content


def mark_issue_processed(issue_page_id: str):
    children = notion.blocks.children.list(block_id=issue_page_id).get("results", [])
    for block in children:
        if block["type"] == "child_page" and "Summary" in block["child_page"]["title"]:
            summary_id = block["id"]
            notion.blocks.children.append(
                block_id=summary_id,
                children=[{
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": "Status: IMAGES GENERATED — PENDING APPROVAL"}}]
                    }
                }]
            )
            print(f"  Marked '{issue_page_id}' as processed in Notion.")
            return
    print(f"  Warning: no Summary page found for '{issue_page_id}', could not mark processed.")


def move_issue_to_archive(issue_page_id: str):
    root_page_id = find_root_page(os.environ.get("NOTION_ROOT_PAGE", "Newsletter"))
    children = notion.blocks.children.list(block_id=root_page_id).get("results", [])
    archive_id = None
    for block in children:
        if block["type"] == "child_page" and block["child_page"]["title"] == "Archive":
            archive_id = block["id"]
            break
    if not archive_id:
        response = notion.pages.create(
            parent={"page_id": root_page_id},
            properties={"title": {"title": [{"text": {"content": "Archive"}}]}}
        )
        archive_id = response["id"]
    notion.pages.update(
        page_id=issue_page_id,
        parent={"page_id": archive_id}
    )
    print(f"  Moved '{issue_page_id}' to Archive.")
