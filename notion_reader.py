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
        blocks[title] = {"id": page_id, "content": content}
    return blocks


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
    children = notio
