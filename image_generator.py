import httpx
import os
import base64

IMAGE_WORKER_URL = os.environ["IMAGE_WORKER_URL"]


async def generate_image(prompt: str, size: str = "1024x1024", quality: str = "medium", style: str = "natural") -> str | None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "generate_image",
            "arguments": {
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "style": style,
            }
        }
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{IMAGE_WORKER_URL}/mcp",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                }
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "image":
                    return item["data"]
    except Exception as e:
        print(f"Image generation failed: {e}")
    return None


def base64_to_data_url(b64: str, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{b64}"
