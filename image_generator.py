import httpx
import json
import os

IMAGE_WORKER_URL = os.environ["IMAGE_WORKER_URL"]


def _parse_mcp_response(resp: httpx.Response) -> dict:
    """Parse MCP response — either plain JSON or SSE (data: {...})."""
    ct = resp.headers.get("content-type", "")
    if "text/event-stream" in ct or not resp.text.strip().startswith("{"):
        # SSE: extract JSON from lines starting with "data: "
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload and payload != "[DONE]":
                    return json.loads(payload)
        return {}
    return resp.json()


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
) -> str | None:
    """Returns a public R2 URL (https://...) or base64 string as fallback, or None on error."""
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

            data = _parse_mcp_response(resp)
            print(f"[image_generator] Content-Type: {resp.headers.get('content-type')} | keys: {list(data.keys())}")

            content = data.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text.startswith("https://"):
                        return text
                    if text.startswith("data:image"):
                        return text.split(",", 1)[-1]
                if item.get("type") == "image":
                    return item.get("data", "")

            print(f"[image_generator] Unexpected response: {str(data)[:500]}")
    except Exception as e:
        print(f"[image_generator] Image generation failed: {e}")
    return None


def base64_to_data_url(b64: str, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{b64}"
