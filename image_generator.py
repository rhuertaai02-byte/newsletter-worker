import httpx
import os

IMAGE_WORKER_URL = os.environ["IMAGE_WORKER_URL"]


async def _mcp_session(client: httpx.AsyncClient) -> str | None:
    """Send MCP initialize handshake and return session ID."""
    payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "newsletter-worker", "version": "1.0"},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = await client.post(f"{IMAGE_WORKER_URL}/mcp", json=payload, headers=headers)
    resp.raise_for_status()
    session_id = resp.headers.get("Mcp-Session-Id")
    print(f"[image_generator] MCP session: {session_id}")
    return session_id


async def generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "medium",
    style: str = "natural",
) -> str | None:
    """Call the Cloudflare MCP Worker and return base64 image data."""
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            session_id = await _mcp_session(client)
            if not session_id:
                print("[image_generator] No session ID returned from initialize")
                return None

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
                    },
                },
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Mcp-Session-Id": session_id,
            }
            resp = await client.post(
                f"{IMAGE_WORKER_URL}/mcp", json=payload, headers=headers
            )
            resp.raise_for_status()

            data = resp.json()
            print(f"[image_generator] Response keys: {list(data.keys())}")

            content = data.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "image":
                    return item["data"]
                if item.get("type") == "text" and item.get("text", "").startswith("data:image"):
                    return item["text"].split(",", 1)[-1]

            print(f"[image_generator] Unexpected response: {str(data)[:500]}")
    except Exception as e:
        print(f"[image_generator] Image generation failed: {e}")
    return None


def base64_to_data_url(b64: str, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{b64}"
