import os
from notion_client import Client

notion = Client(auth=os.environ["NOTION_TOKEN"])


def find_root_page(name: str) -> str:
    """Find the root Newsletter page by name."""
    results = notion.search(query=name, filter={"property": "object", "value": "page"}).get("results", [])
    for page in results:
        title_parts = page.get("properties", {}).get("title", {}).get("title", [])
        title = "".join(t["plain_text"] for t in title_parts)
        if title.strip() == name:
            return page["id"]
    raise ValueError(f"Notion page '{name}' not found. Make sure the newsletter-worker integration has access to it.")


def get_new_issues(root_page_id: str, already_processed: set) -> list[dict]:
    """Return child pages of root that haven't been processed yet."""
    children = notion.blocks.children.list(block_id=root_page_id).get("results", [])
    issues = []
    for block in children:
        if block["type"] != "child_page":
            continue
        page_id = block["id"]
        if page_id in already_processed:
            continue
        title = block["child_page"]["title"]
        if title.startswith("Newsletter —"):
            issues.append({"id": page_id, "title": title})
    return issues


def get_issue_blocks(issue_page_id: str) -> dict:
    """Read all sub-pages of an issue and return their content."""
    children = notion.blocks.children.list(block_id=issue_page_id).get("results", [])
    blocks = {}
    for block in children:
        if block["type"] != "child_page":
            continue
        title = block["child_page"]["title"]
        page_id = block["id"]
        content = extract_page_text(page_id)
        blocks[title] = {"id": page_id, "content": content}
    return blocks


def extract_page_text(page_id: str) -> str:
    """Extract all text content from a Notion page."""
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
    """Pull the image prompt from a block's content text."""
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
    """Pull size and quality settings from block content."""
    settings = {"size": "1024x1024", "quality": "medium", "style": "natural"}
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
    """Extract just the Content section from a block page."""
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
    """Update the Summary page status to IMAGES ADDED."""
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
            return
