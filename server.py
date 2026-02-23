import json
import urllib.request
import urllib.parse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

CREDS_FILE = Path(__file__).parent / "credentials.json"
MAX_RESPONSE_CHARS = 40000

mcp = FastMCP("slacc")


def _load_creds() -> dict:
    if not CREDS_FILE.exists():
        from main import main as extract
        extract()
    if not CREDS_FILE.exists():
        raise RuntimeError("Token extraction failed. Run manually: uv run main.py")
    return json.loads(CREDS_FILE.read_text())


def _call_slack(method: str, params: dict | None = None) -> dict:
    creds = _load_creds()
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {creds['token']}",
            "Cookie": f"d={creds['cookie']}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def _trim_message(msg: dict) -> dict:
    """Keep only useful fields from a message to reduce payload size."""
    keep = {"user", "text", "ts", "thread_ts", "reply_count", "channel", "username", "bot_id", "type", "subtype"}
    trimmed = {k: v for k, v in msg.items() if k in keep}
    # Trim attachments/blocks to just text content
    if "attachments" in msg:
        trimmed["attachments"] = [
            {"text": a.get("text", ""), "title": a.get("title", "")}
            for a in msg["attachments"]
            if a.get("text") or a.get("title")
        ]
    return trimmed


def _trim_search_match(match: dict) -> dict:
    """Keep only useful fields from a search result."""
    return {
        "text": match.get("text", ""),
        "username": match.get("username", ""),
        "ts": match.get("ts", ""),
        "channel": {"id": match.get("channel", {}).get("id", ""), "name": match.get("channel", {}).get("name", "")},
        "permalink": match.get("permalink", ""),
    }


def _compact(result: dict, method: str) -> dict:
    """Reduce response size by trimming verbose fields."""
    if not result.get("ok"):
        return result

    if "messages" in result:
        msgs = result["messages"]
        # search.messages wraps in {"matches": [...]}
        if isinstance(msgs, dict) and "matches" in msgs:
            result["messages"] = {
                "total": msgs.get("total", 0),
                "matches": [_trim_search_match(m) for m in msgs["matches"]],
            }
        # conversations.history / replies returns a list
        elif isinstance(msgs, list):
            result["messages"] = [_trim_message(m) for m in msgs]

    # Drop response_metadata, warning, etc.
    for key in ["response_metadata", "warning", "req_method"]:
        result.pop(key, None)

    return result


@mcp.tool()
def slack_api(method: str, params: str = "{}") -> str:
    """Call any Slack API method.

    method: The Slack API method (e.g. "search.messages", "conversations.history", "chat.postMessage")
    params: JSON string of parameters to pass (e.g. '{"channel": "C04GP9KGU3T", "limit": 10}')

    See https://api.slack.com/methods for all available methods.

    IMPORTANT: Do NOT use conversations.list, users.list, or users.conversations — they are
    blocked on enterprise workspaces. Instead:
    - To find messages/channels: use "search.messages" with a query
    - To read a channel: use "conversations.history" with a channel ID
    - To find a channel ID: search for a message in it first
    - Keep count/limit low (10-20) to avoid oversized responses
    """
    try:
        parsed_params = json.loads(params)
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "error": f"Invalid params JSON: {e}"})

    result = _call_slack(method, parsed_params)
    result = _compact(result, method)
    output = json.dumps(result, indent=2)

    if len(output) > MAX_RESPONSE_CHARS:
        output = output[:MAX_RESPONSE_CHARS] + "\n... (truncated, use smaller count/limit)"

    return output


if __name__ == "__main__":
    mcp.run()
